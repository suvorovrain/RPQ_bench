"""Check the prepared dataset inputs required by a competitor."""
import argparse
from pathlib import Path

from Scripts.runners.config import ENGINES, ROOT

CSV = ("csv/nodes.csv", "csv/edges.csv")
RDF = ("rdf/graph.nt",)
INPUTS = {
    "pathrex": (),
    "larpq": ("matrix/graph.dat",),
    "rpqmatrix": ("matrix/graph.dat", "matrix/graph.dat.P", "matrix/graph.dat.SO"),
    "rpqmatrixGB": ("matrix-gb/graph.dat.P", "matrix-gb/graph.dat.SO", "matrix-gb/graph.dat.baseline-64"),
    "ring": ("matrix/graph.dat", "matrix/graph.dat.P", "matrix/graph.dat.SO"),
    "duckdb": ("csv/edges.csv",),
    "postgres": ("csv/edges.csv",),
    "kuzu": CSV,
    "neo4j": CSV,
    "memgraph": CSV,
    "falkordb": CSV,
    "jena": RDF,
    "millenniumdb": RDF,
    "blazegraph": RDF,
    "virtuoso": RDF,
}


def validate(engine, prepared, graph, manifest):
    inputs = [prepared / name for name in INPUTS[engine]]
    if engine in {"pathrex", "jena", "millenniumdb", "blazegraph", "virtuoso"}:
        inputs.append(graph / "vertices.txt")
    if engine == "pathrex":
        inputs.extend([graph / "edges.txt", *(graph / f"{pid}.txt" for pid in manifest["labels"])])
    if engine in {"kuzu", "neo4j", "memgraph", "falkordb"}:
        inputs.extend(prepared / f"csv/edges_{label}.csv" for label in manifest["labels"].values())
    if engine == "rpqmatrixGB":
        inputs.extend(prepared / f"matrix-gb/graph.dat.baseline-64/{int(pid):04d}.mat"
                      for pid in manifest["labels"])
    missing = [str(path) for path in inputs if not path.exists()]
    if missing:
        raise FileNotFoundError(f"{engine}: missing prepared files: {', '.join(missing[:8])}")
    return inputs


def main():
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("engine", choices=ENGINES)
    parser.add_argument("--dataset", default="rpq_250k")
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--graph", type=Path)
    args = parser.parse_args()
    dataset = ROOT / "Datasets" / args.dataset
    data = args.prepared or dataset / "prepared"
    graph = args.graph or dataset / "pathrex"
    manifest = json.loads((data / "manifest.json").read_text())
    for item in validate(args.engine, data, graph, manifest):
        print(item)


if __name__ == "__main__":
    main()
