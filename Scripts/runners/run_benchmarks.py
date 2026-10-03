#!/usr/bin/env python3
"""Run three engines using Scripts/run_config.json; no command templates."""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
ENGINES = ("pathrex", "rpq-matrix", "rpq-matrix_gb")


def select(value, available):
    names = list(available) if value == "all" else list(dict.fromkeys(value.split(",")))
    if not names or any(name not in available for name in names):
        raise ValueError(f"unknown selection {value!r}; available: {', '.join(available)}")
    return names


def query_ids(path, converted=False):
    lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    ids = []
    for line in lines:
        number, separator, query = line.partition(" " if converted else ",")
        if not separator or not number.isdecimal() or not query.strip():
            raise ValueError(f"invalid numbered query in {path}: {line!r}")
        if converted and ("\t" in line or query.startswith(" ") or not query.endswith("#")):
            raise ValueError(f"expected '<ID> <query>#' with one space in {path}")
        ids.append(number)
    if not ids or len(ids) != len(set(ids)):
        raise ValueError(f"empty query file or duplicate query IDs: {path}")
    return ids


def run(command, output, metadata, dry_run):
    print("+ " + shlex.join(command), flush=True)
    if dry_run:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    if metadata is None:
        subprocess.run(command, check=True)
        return
    # Preserve baseline rows, including warm-ups, and only publish a successful batch.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
            for line in process.stdout:
                if re.match(r"^[0-9]+;", line):
                    stream.write(line)
            code = process.wait()
            if code:
                raise subprocess.CalledProcessError(code, command)
        temporary.replace(output)
        temporary = None
        output.with_name(output.name + ".meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "Scripts/run_config.json")
    parser.add_argument("--root", type=Path, default=ROOT, help="Root for relative config paths.")
    parser.add_argument("--engine", default="all", help="all or comma-separated engine names.")
    parser.add_argument("--optimizer", default="all", help="Pathrex optimizer filter.")
    parser.add_argument("--query-set", default="all", help="all or comma-separated query-set names.")
    parser.add_argument("--runs", type=int)
    parser.add_argument("--warmup-runs", type=int)
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and print commands.")
    parser.add_argument("--keep-going", action="store_true", help="Continue with the next process after a failure.")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if "competitors" in config:
        raise ValueError("this is a report config; use Scripts/run_config.json for launching")
    root = args.root.resolve()
    path = lambda value: (root / value).resolve()
    engines = select(args.engine, ENGINES)
    sets = select(args.query_set, config["queries"])
    runs = config["runs"] if args.runs is None else args.runs
    warmup = config["warmup_runs"] if args.warmup_runs is None else args.warmup_runs
    if type(runs) is not int or type(warmup) is not int or runs < 1 or warmup < 0:
        raise ValueError("runs must be a positive integer; warmup_runs a nonnegative integer")
    jobs = []
    for engine in engines:
        settings = config[engine]
        binary = (path(settings["source"]) / settings["binary"]).resolve()
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise ValueError(f"missing executable: {binary}; build {engine} first")
        output_root = path(settings["output"])
        if engine == "pathrex":
            optimizers = select(args.optimizer, settings["optimizers"])
            if len(settings["optimizers"]) != len(set(settings["optimizers"])):
                raise ValueError("duplicate Pathrex optimizer names")
            if any(not re.fullmatch(r"[a-z][a-z0-9-]*", name) for name in optimizers):
                raise ValueError("optimizer names must be plain CLI names")
            if not args.dry_run:
                help_text = subprocess.check_output([str(binary), "bench", "--help"], text=True)
                for optimizer in optimizers:
                    if not re.search(r"\b" + re.escape(optimizer) + r"\b", help_text):
                        raise ValueError(f"{binary} does not advertise {optimizer}; rebuild Pathrex")
            graph = path(settings["graph"])
            for required in [graph, graph / "vertices.txt", graph / "edges.txt"]:
                if not required.exists():
                    raise ValueError(f"missing graph input: {required}")
        else:
            optimizers = ["rpqmatrix" if engine == "rpq-matrix" else "rpqmatrix-gb"]
            dataset = path(settings["dataset"])
            for required in [Path(str(dataset) + suffix) for suffix in (".SO", ".P", ".baseline-64/0001.mat")]:
                if not required.exists():
                    raise ValueError(f"missing dataset input: {required}")
            for key in ("n_predicates", "n_triples"):
                if type(config[key]) is not int or config[key] < 1:
                    raise ValueError(f"{key} must be a positive integer")
        for name in optimizers:
            for query_set in sets:
                if Path(query_set).name != query_set or query_set in (".", ".."):
                    raise ValueError("query-set names must not contain path separators")
                queries = config["queries"][query_set]
                catalog = path(queries["pathrex"])
                ids = query_ids(catalog)
                query = catalog if engine == "pathrex" else path(queries["rpqmatrix"])
                output = output_root / query_set / name / ("res.json" if engine == "pathrex" else "res.txt")
                metadata = None
                if engine == "pathrex":
                    command = [str(binary), "bench", "--graph", str(graph), "--format", "mm", "--queries", str(query), "--algo", "rpqmatrix", "--rpqmatrix-optimizer", name, "--output", str(output), "--runs", str(runs), "--warm-up-runs", str(warmup)]
                    if settings.get("base_iri"):
                        command.append("--base-iri=" + settings["base_iri"])
                else:
                    if query_ids(query, converted=True) != ids:
                        raise ValueError(f"query IDs differ from {catalog}: regenerate {query}")
                    command = [str(binary), str(dataset), str(query), str(config["n_predicates"]), str(config["n_triples"]), str(runs), str(warmup)]
                    metadata = {"competitor": name, "query_set": query_set, "query_source_path": str(query), "query_ids": ids, "runs": runs, "warmup_runs": warmup, "total_runs": runs + warmup, "result_path": str(output)}
                jobs.append((engine, name, query_set, command, output, metadata))
    # Validate every selected input before loading even the first large graph.
    outputs = [job[4] for job in jobs]
    if len(outputs) != len(set(outputs)):
        raise ValueError("selected jobs have colliding output paths")
    failures = 0
    for engine, name, query_set, command, output, metadata in jobs:
        print(f"[{engine}/{name}] {query_set}; warmup={warmup}, runs={runs}", flush=True)
        try:
            run(command, output, metadata, args.dry_run)
        except (OSError, subprocess.CalledProcessError) as error:
            print(f"ERROR: {engine}/{name} {query_set}: {error}", flush=True)
            failures += 1
            if not args.keep_going:
                break
    return int(failures > 0)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Configuration/preflight error: {error}")
