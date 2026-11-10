"""Download the first annotated slide or the ten-slide inspection set.

Run with: uv run --locked python src/fetch_camelyon17_sample.py
Add --inspection-set to download the files in manifests/inspection_slides.csv.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
from pathlib import Path
import shutil

import boto3
from botocore import UNSIGNED
from botocore.config import Config

from fetch_camelyon17_metadata import BUCKET, PREFIX, REGION, ROOT, fetch_metadata


SLIDE_ID = "patient_092_node_1.tif"
MAX_DOWNLOAD_BYTES = 1024**3
INSPECTION_MANIFEST = ROOT / "manifests" / "inspection_slides.csv"


def verify_file(path, size, expected_md5):
    """Check the complete file against the saved inventory and publisher's MD5."""
    if path.stat().st_size != size:
        raise ValueError(f"Unexpected file size: {path}")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(
            stream, lambda: hashlib.md5(usedforsecurity=False)
        ).hexdigest()
    if digest != expected_md5:
        raise ValueError(f"Checksum mismatch: {path}")


def fetch_sample(slide_id=SLIDE_ID, *, expected=None, max_download_bytes=MAX_DOWNLOAD_BYTES):
    """Fetch one labeled slide and its available XML, verifying local copies too.

    An expected manifest row pins the label, hospital, file sizes, and MD5s.
    The original no-argument call still downloads only the first example.
    """
    raw = fetch_metadata()
    with (raw / "objects.csv").open(newline="", encoding="utf-8") as stream:
        objects = {row["key"]: row for row in csv.DictReader(stream)}
    with (raw / "stages.csv").open(newline="", encoding="utf-8-sig") as stream:
        label = next((row for row in csv.DictReader(stream) if row["patient"] == slide_id), None)
    if label is None or not slide_id.endswith(".tif"):
        raise ValueError(f"No slide label in the saved metadata: {slide_id}")
    checksums = {}
    for line in (raw / "checksums.md5").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            checksums[name.lstrip("*")] = digest.lower()

    snapshot = json.loads((raw / "provenance.json").read_text(encoding="utf-8"))
    sample = {
        "slide_id": slide_id,
        "label": label["stage"],
        "hospital": int(label["center"]),
        "metadata_retrieved_at_utc": snapshot["retrieved_at_utc"],
        "files": {},
    }
    files = []
    annotation_path = f"annotations/{Path(slide_id).stem}.xml"
    if PREFIX + annotation_path in objects:
        files.append(("annotation", annotation_path))
    files.append(("image", f"images/{slide_id}"))

    # Compare the whole planned record before starting either download.
    if expected is not None:
        if (expected["slide_id"] != slide_id or expected["label"] != sample["label"]
                or int(expected["hospital"]) != sample["hospital"]):
            raise ValueError(f"Manifest label or hospital differs from metadata: {slide_id}")
        if bool(expected["annotation_key"]) != (len(files) == 2):
            raise ValueError(f"Manifest annotation availability changed: {slide_id}")
        for kind, relative_path in files:
            key = PREFIX + relative_path
            if (expected[f"{kind}_key"] != key
                    or int(expected[f"{kind}_bytes"]) != int(objects[key]["size_bytes"])
                    or expected[f"{kind}_md5"] != checksums[relative_path]):
                raise ValueError(f"Manifest file details differ from metadata: {key}")

    s3 = None
    for kind, relative_path in files:
        key = PREFIX + relative_path
        size = int(objects[key]["size_bytes"])
        expected_md5 = checksums[relative_path]
        path = raw / relative_path
        if path.exists():
            verify_file(path, size, expected_md5)
            print(f"Verified local {path.name}.", flush=True)
        else:
            if not 0 < size <= max_download_bytes:
                raise ValueError(f"File exceeds the download limit: {path.name}")
            if shutil.disk_usage(raw).free < size + 1024**3:
                raise OSError("Not enough space for the download plus 1 GiB of free space.")
            if s3 is None:
                s3 = boto3.session.Session().client(
                    "s3", region_name=REGION,
                    config=Config(
                        signature_version=UNSIGNED, connect_timeout=10,
                        read_timeout=60, retries={"max_attempts": 3, "mode": "standard"},
                    ),
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_suffix(path.suffix + ".part")
            print(f"Downloading {path.name} ({size / 1e6:.2f} MB)...", flush=True)
            try:
                response = s3.get_object(Bucket=BUCKET, Key=key)
                with response["Body"] as body:
                    if response["ContentLength"] != size:
                        raise ValueError("Source size changed since the metadata snapshot.")
                    report_interval = max(128 * 1024**2, size // 4)
                    received, next_report = 0, report_interval
                    with partial.open("wb") as output:
                        while chunk := body.read(8 * 1024**2):
                            received += len(chunk)
                            if received > size:
                                raise ValueError("Download exceeded the expected file size.")
                            output.write(chunk)
                            if received >= next_report:
                                print(f"  {path.name}: {received / size:.0%} downloaded", flush=True)
                                next_report += report_interval
                verify_file(partial, size, expected_md5)
                partial.replace(path)
            finally:
                partial.unlink(missing_ok=True)
            print(f"Verified downloaded {path.name}.", flush=True)
        sample["files"][kind] = {
            "path": path, "s3_key": key, "bytes": size, "md5": expected_md5,
        }
    return sample


def load_inspection_manifest():
    """Read the fixed set and check that it has one negative and one macro per hospital."""
    with INSPECTION_MANIFEST.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    pairs = [(int(row["hospital"]), row["label"]) for row in rows]
    expected_pairs = [(hospital, label) for hospital in range(5) for label in ("negative", "macro")]
    if len(rows) != 10 or sorted(pairs) != sorted(expected_pairs):
        raise ValueError("Expected one negative and one macro slide per hospital.")
    if len({row["slide_id"] for row in rows}) != 10:
        raise ValueError("The inspection manifest contains duplicate slide IDs.")
    if any(row["label"] == "macro" and not row["annotation_key"] for row in rows):
        raise ValueError("Each selected macro slide must have an XML annotation.")
    total = sum(int(row[f"{kind}_bytes"]) for row in rows for kind in ("image", "annotation"))
    if total > 20 * 1024**3:
        raise ValueError("The inspection set exceeds its 20 GiB download budget.")
    return rows


def fetch_inspection_set():
    """Download the fixed ten-slide set; reruns reuse files that pass verification."""
    rows = load_inspection_manifest()
    raw = fetch_metadata()
    missing_bytes = sum(
        int(row[f"{kind}_bytes"])
        for row in rows for kind in ("image", "annotation")
        if row[f"{kind}_key"] and not (raw / row[f"{kind}_key"].removeprefix(PREFIX)).exists()
    )
    if shutil.disk_usage(raw).free < missing_bytes + 2 * 1024**3:
        raise OSError("Not enough space for the inspection set plus 2 GiB of free space.")
    print(f"Inspection set: {len(rows)} slides; {missing_bytes / 1e9:.2f} GB to download.", flush=True)
    def fetch_row(item):
        index, row = item
        print(f"[{index}/{len(rows)}] Hospital {row['hospital']}, {row['label']}: {row['slide_id']}", flush=True)
        return fetch_sample(row["slide_id"], expected=row, max_download_bytes=5 * 1024**3)

    # Each worker owns its S3 session and writes a different slide file.
    with ThreadPoolExecutor(max_workers=3) as executor:
        return list(executor.map(fetch_row, enumerate(rows, start=1)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspection-set", action="store_true", help="Fetch the fixed ten-slide set.")
    args = parser.parse_args()
    if args.inspection_set:
        fetch_inspection_set()
    else:
        fetch_sample()
