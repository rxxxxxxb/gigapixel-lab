"""Download one annotated slide for the first image-inspection notebook.

Run with: uv run --locked python src/fetch_camelyon17_sample.py
"""

import csv
import hashlib
import json
from pathlib import Path
import shutil

import boto3
from botocore import UNSIGNED
from botocore.config import Config

from fetch_camelyon17_metadata import BUCKET, PREFIX, REGION, fetch_metadata


SLIDE_ID = "patient_092_node_1.tif"
MAX_DOWNLOAD_BYTES = 1024**3


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


def fetch_sample():
    """Fetch the fixed TIFF/XML pair, or verify and reuse the local copies."""
    raw = fetch_metadata()
    with (raw / "objects.csv").open(newline="", encoding="utf-8") as stream:
        objects = {row["key"]: row for row in csv.DictReader(stream)}
    with (raw / "stages.csv").open(newline="", encoding="utf-8-sig") as stream:
        label = next(row for row in csv.DictReader(stream) if row["patient"] == SLIDE_ID)
    checksums = {}
    for line in (raw / "checksums.md5").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            checksums[name.lstrip("*")] = digest.lower()

    snapshot = json.loads((raw / "provenance.json").read_text(encoding="utf-8"))
    sample = {
        "slide_id": SLIDE_ID,
        "label": label["stage"],
        "hospital": int(label["center"]),
        "metadata_retrieved_at_utc": snapshot["retrieved_at_utc"],
        "files": {},
    }
    s3 = None
    for kind, relative_path in (
        ("annotation", f"annotations/{Path(SLIDE_ID).stem}.xml"),
        ("image", f"images/{SLIDE_ID}"),
    ):
        key = PREFIX + relative_path
        size = int(objects[key]["size_bytes"])
        expected_md5 = checksums[relative_path]
        path = raw / relative_path
        if path.exists():
            verify_file(path, size, expected_md5)
            print(f"Verified local {path.name}.", flush=True)
        else:
            if not 0 < size <= MAX_DOWNLOAD_BYTES:
                raise ValueError("This first inspection is limited to files up to 1 GiB.")
            if shutil.disk_usage(raw).free < size + 1024**3:
                raise OSError("Not enough space for the download plus 1 GiB of free space.")
            if s3 is None:
                s3 = boto3.client(
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
                    received, next_report = 0, 128 * 1024**2
                    with partial.open("wb") as output:
                        while chunk := body.read(8 * 1024**2):
                            received += len(chunk)
                            if received > size:
                                raise ValueError("Download exceeded the expected file size.")
                            output.write(chunk)
                            if received >= next_report:
                                print(f"  {received / size:.0%} downloaded", flush=True)
                                next_report += 128 * 1024**2
                verify_file(partial, size, expected_md5)
                partial.replace(path)
            finally:
                partial.unlink(missing_ok=True)
            print(f"Verified downloaded {path.name}.", flush=True)
        sample["files"][kind] = {
            "path": path, "s3_key": key, "bytes": size, "md5": expected_md5,
        }
    return sample


if __name__ == "__main__":
    fetch_sample()
