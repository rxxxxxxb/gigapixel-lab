"""Cache the public CAMELYON17 metadata without downloading slide images.

Run from the repository root with:
    uv run --locked python src/fetch_camelyon17_metadata.py
"""

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "raw" / "camelyon17"
BUCKET = "camelyon-dataset"
PREFIX = "CAMELYON17/"
REGION = "us-west-2"
METADATA_FILES = ("README.md", "stages.csv", "checksums.md5")
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_OBJECTS = 20_000


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def fetch_metadata():
    """Fetch once; later runs verify and reuse the saved snapshot offline."""
    provenance_path = DATA_DIR / "provenance.json"
    if provenance_path.exists():
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        for name in (*METADATA_FILES, "objects.csv"):
            content = (DATA_DIR / name).read_bytes()
            if sha256(content) != provenance["files"][name]["sha256"]:
                raise ValueError(f"Cached metadata changed: {name}")
        print("Using the verified local metadata snapshot.")
        return DATA_DIR

    # These public reads use no AWS credentials and request no TIFF/XML contents.
    s3 = boto3.client(
        "s3",
        region_name=REGION,
        config=Config(
            signature_version=UNSIGNED,
            connect_timeout=10,
            read_timeout=30,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )
    payloads = {}
    provenance = {
        "dataset": "CAMELYON17",
        "bucket": BUCKET,
        "prefix": PREFIX,
        "region": REGION,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "registry": "https://registry.opendata.aws/camelyon/",
        "files": {},
    }
    for name in METADATA_FILES:
        response = s3.get_object(Bucket=BUCKET, Key=PREFIX + name)
        with response["Body"] as stream:
            if response["ContentLength"] > MAX_FILE_BYTES:
                raise ValueError(f"Metadata exceeds the download limit: {name}")
            content = stream.read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES or len(content) != response["ContentLength"]:
            raise ValueError(f"Unexpected metadata size: {name}")
        content.decode("utf-8-sig")  # Fail on unexpected binary content.
        payloads[name] = content
        provenance["files"][name] = {
            "source": f"s3://{BUCKET}/{PREFIX}{name}",
            "bytes": len(content),
            "sha256": sha256(content),
            "etag": response["ETag"],
            "last_modified_utc": response["LastModified"].isoformat(),
        }

    objects = []
    pages = 0
    for page in s3.get_paginator("list_objects_v2").paginate(
        Bucket=BUCKET, Prefix=PREFIX, PaginationConfig={"PageSize": 1000}
    ):
        pages += 1
        for item in page.get("Contents", []):
            objects.append({
                "key": item["Key"],
                "size_bytes": item["Size"],
                "etag": item["ETag"],
                "last_modified_utc": item["LastModified"].isoformat(),
            })
        if len(objects) > MAX_OBJECTS or pages > 100:
            raise ValueError("Object listing exceeded the audit limit; no truncated snapshot saved.")

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=["key", "size_bytes", "etag", "last_modified_utc"]
    )
    writer.writeheader()
    writer.writerows(sorted(objects, key=lambda item: item["key"]))
    inventory = buffer.getvalue().encode("utf-8")
    payloads["objects.csv"] = inventory
    provenance["files"]["objects.csv"] = {
        "source": f"s3://{BUCKET}/{PREFIX}",
        "operation": "ListObjectsV2; all pages under the prefix",
        "objects": len(objects),
        "pages": pages,
        "complete": True,
        "bytes": len(inventory),
        "sha256": sha256(inventory),
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Refuse to overwrite an incomplete/older snapshot without its provenance.
    if any((DATA_DIR / name).exists() for name in payloads):
        raise FileExistsError("Metadata already exists without provenance; inspect it before retrying.")
    for name, content in payloads.items():
        (DATA_DIR / name).write_bytes(content)
    provenance_path.write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(f"Saved three metadata files and a complete listing of {len(objects):,} objects.")
    print(f"Saved metadata: {sum(map(len, payloads.values())) / 1024:.1f} KiB; no slide images downloaded.")
    return DATA_DIR


if __name__ == "__main__":
    fetch_metadata()
