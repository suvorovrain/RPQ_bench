"""Prepare or validate the shared graph inputs for one or several competitors."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from Scripts.runners.config import ENGINES, ROOT, TOKEN

from .inputs import validate
from .prepare_250k import prepare


def main(default_engine=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="rpq_250k")
    parser.add_argument("--engine", choices=ENGINES, default=default_engine)
    parser.add_argument("--graph", type=Path, help="Override the Pathrex MatrixMarket input")
    parser.add_argument("--prepared", type=Path, help="Override the shared prepared graph directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--bootstrap-250k", action="store_true", help="Prepare the legacy RPQBench projection")
    mode.add_argument("--source", type=Path, help="Normalize a small RDF graph with full RDF term identity")
    parser.add_argument("--format", choices=("nt", "n3", "turtle"))
    args = parser.parse_args()
    if not TOKEN.fullmatch(args.dataset):
        parser.error("Invalid dataset name")
    if default_engine and args.engine != default_engine:
        parser.error(f"This converter prepares {default_engine}")
    dataset = ROOT / "Datasets" / args.dataset
    prepared = args.prepared or dataset / "prepared"
    graph = args.graph or dataset / "pathrex"
    if args.bootstrap_250k:
        if args.dataset != "rpq_250k" or args.prepared or args.graph:
            parser.error("--bootstrap-250k uses the standard rpq_250k directories")
        if not prepared.exists():
            prepare(dataset, bootstrap_mm=True)
    elif args.source:
        if not args.format or args.graph:
            parser.error("--source requires --format and creates MatrixMarket under the prepared directory")
        if not prepared.exists():
            subprocess.run([sys.executable, "-m", "Scripts.converters.general.prepare_rdf",
                            args.source, prepared, "--format", args.format], cwd=ROOT, check=True)
        graph = prepared / "pathrex"
    try:
        manifest = json.loads((prepared / "manifest.json").read_text())
        for engine in [args.engine] if args.engine else ENGINES:
            print(engine)
            for item in validate(engine, prepared, graph, manifest):
                print(f"  {item}")
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
