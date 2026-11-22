"""Prepare a GraphBLAS benchmark from existing MatrixMarket label files."""
import argparse
import json
from pathlib import Path

from Scripts.converters.general.queries import mapping
from Scripts.converters.rpqmatrixGB.matrix_market import convert


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", type=Path)
    parser.add_argument("prepared", type=Path)
    parser.add_argument("--base-iri", required=True)
    parser.add_argument("--copy", action="store_true", help="Copy matrices for a relocatable prepared directory")
    args = parser.parse_args()
    if args.prepared.exists():
        parser.error(f"Output already exists: {args.prepared}")
    labels = mapping(args.graph / "edges.txt")
    count = 0
    for pid in labels.values():
        with (args.graph / f"{pid}.txt").open() as stream:
            shape = next(line for line in stream if line.strip() and not line.startswith("%"))
            count += int(shape.split()[2])
    vertices, _, _ = convert(args.graph, args.prepared / "matrix-gb/graph.dat", args.copy)
    manifest = {"base_iri": args.base_iri, "vertices": vertices, "edges": count,
                "labels": {pid: name for name, pid in labels.items()}, "queries": []}
    (args.prepared / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(args.prepared)


if __name__ == "__main__":
    main()
