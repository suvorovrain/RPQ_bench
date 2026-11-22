#!/usr/bin/env python3
"""Fetch the exact binary distributions and Docker images used by the guides."""
import argparse
import hashlib
import json
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", action="store_true", help="Also pull all locked Docker images")
    args = parser.parse_args()
    lock = json.loads((ROOT / "Databases/guides/runtime-lock.json").read_text())
    tools = ROOT / ".rpq-runtime/tools"
    tools.mkdir(parents=True, exist_ok=True)
    for name, artifact in lock["artifacts"].items():
        path = tools / name
        if not path.exists():
            temporary = tools / (name+".download")
            with urllib.request.urlopen(artifact["url"], timeout=180) as src, temporary.open("wb") as dst:
                while chunk := src.read(1024*1024):
                    dst.write(chunk)
            temporary.rename(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ValueError(f"SHA256 mismatch: {path}")
        print("Verified", name, flush=True)
    if not (tools / "apache-jena-6.2.0").exists():
        with tarfile.open(tools / "jena.tar.gz") as archive:
            archive.extractall(tools, filter="data")
    if args.images:
        for image in lock["images"].values():
            subprocess.run(["docker", "pull", image], check=True)


if __name__ == "__main__":
    main()
