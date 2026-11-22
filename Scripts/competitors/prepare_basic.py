#!/usr/bin/env python3
"""Select four existing simple con-any queries for all 15 competitors."""
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "Datasets/rpqbench_250k/prepared"
IDS = {"1", "2", "3", "5"}


def prepare():
    manifest = json.loads((DATA / "manifest.json").read_text())
    queries = [q for q in manifest["queries"] if q["id"] in IDS]
    assert len(queries) == 4
    target = DATA / "basic"
    target.mkdir(exist_ok=True)
    for q in queries:
        for suffix in ("rq", "sql"):
            shutil.copyfile(DATA / f'queries/q{q["id"]}.{suffix}', target / f'q{q["id"]}.{suffix}')
    for name in ("pathrex.txt", "matrix.tsv", "larpq.tsv"):
        separator = "," if name == "pathrex.txt" else " "
        lines = (DATA / "queries" / name).read_text().splitlines()
        (target / name).write_text("".join(line+"\n" for line in lines if line.split(separator, 1)[0] in IDS))
    ring = (DATA / "queries/ring.tsv").read_text().splitlines()
    (target / "ring.tsv").write_text("\n".join(line for q,line in zip(manifest["queries"],ring) if q["id"] in IDS))
    (target / "manifest.json").write_text(json.dumps({"queries":queries},indent=2)+"\n")
    return queries


if __name__ == "__main__":
    print("Prepared", len(prepare()), "queries in", DATA / "basic")
