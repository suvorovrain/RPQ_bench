"""Acquire a dataset source and the pinned upstream query catalog."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit

from Scripts.runners.config import ROOT

DATASETS = {
    "rpq_250k": ("rpqbench_250k.n3", "RPQBench/sparql-queries-templates.txt"),
    "wiki": ("wikidata.nt", "Wikidata/sparql-queries.txt"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=DATASETS)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--url", help="Direct HTTP(S) source file URL")
    source.add_argument("--local", type=Path, help="Copy the original NT/N3 from disk")
    source.add_argument("--generator", type=Path, help="Path to upstream rpqbench_gen")
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    directory = args.directory or ROOT / "Datasets" / args.dataset
    directory.mkdir(parents=True, exist_ok=True)
    filename, catalog = DATASETS[args.dataset]
    target = directory / filename
    if target.exists() and (args.url or args.local or args.generator):
        parser.error(f"Source already exists: {target}")
    if args.url and urlsplit(args.url).scheme not in {"http", "https"}:
        parser.error("Expected HTTP(S) URL")
    if args.generator and args.dataset != "rpq_250k":
        parser.error("The generator is only for rpq_250k")
    if not target.exists():
        if not (args.url or args.local or args.generator):
            parser.error("Supply --url, --local, or --generator for the missing dataset")
        with tempfile.TemporaryDirectory(prefix=".acquire-", dir=directory) as temporary:
            temp = Path(temporary) / filename
            if args.url:
                subprocess.run(["curl", "--fail", "--location", "--retry", "3", "--output", temp, args.url], check=True)
            elif args.local:
                shutil.copyfile(args.local, temp)
            else:
                generator = args.generator.resolve()
                # The upstream generator reads assets relative to its own directory.
                generated = generator.parent / "rpqbench.n3"
                if generated.exists():
                    parser.error(f"{generated} already exists; pass it as --local")
                subprocess.run([generator, "-t", "250000"], cwd=generator.parent, check=True)
                shutil.copyfile(generated, temp)
            with temp.open("rb") as stream:
                if not stream.read(1):
                    parser.error("Empty dataset file")
            temp.rename(target)
    queries = directory / "upstream-queries.txt"
    if not queries.exists():
        shutil.copyfile(ROOT / "vendor/larpq/Datasets" / catalog, queries)
    print(f"Graph {target}\nUpstream query catalog {queries}")


if __name__ == "__main__":
    main()
