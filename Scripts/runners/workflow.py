"""Run selected competitors sequentially and retain the complete run context."""
import argparse
import importlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess

from Scripts.converters.general.inputs import validate

from .config import DEFAULT_CONFIG, ENGINES, ROOT, TOKEN, load, repo_path
from .runtime import Benchmark, now

QUERY_FILES = {
    "pathrex": ("pathrex.txt", ","),
    "rpqmatrix": ("matrix.tsv", " "),
    "rpqmatrixGB": ("matrix.tsv", " "),
    "larpq": ("larpq.tsv", " "),
    "ring": ("ring.tsv", None),
}


def stage_queries(selection, target):
    target.mkdir()
    (target / "manifest.json").write_text(json.dumps({"queries": selection.queries}, indent=2) + "\n")
    engine = selection.engine
    if engine in QUERY_FILES:
        name, separator = QUERY_FILES[engine]
        rows = (selection.directory / name).read_text().splitlines()
        if separator is None:
            catalog = json.loads((selection.directory / "manifest.json").read_text())["queries"]
            if len(rows) != len(catalog):
                raise ValueError("Ring catalog and query file have different lengths")
            records = {str(q["id"]): line for q, line in zip(catalog, rows)}
        else:
            records = {line.split(separator, 1)[0]: line for line in rows if line}
        chosen = [records[q["id"]] for q in selection.queries]
        (target / name).write_text("\n".join(chosen) + ("\n" if separator else ""))
    elif engine in {"duckdb", "postgres"}:
        for q in selection.queries:
            name = f'q{q["id"]}.sql'
            (target / name).write_bytes((selection.directory / name).read_bytes())


def git_output(*args):
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def main(default_engine=None, default_dataset="rpq_250k"):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--dataset", default=default_dataset)
    parser.add_argument("--engines", nargs="+", choices=ENGINES)
    parser.add_argument("--queries", nargs="+", metavar="ID")
    parser.add_argument("--query-set")
    parser.add_argument("--name", default="benchmark")
    parser.add_argument("--runs", type=int)
    parser.add_argument("--warmups", type=int)
    parser.add_argument("--threads", help="CPU budget, or all")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not TOKEN.fullmatch(args.name):
        parser.error("Invalid run name")
    if default_engine and args.engines and args.engines != [default_engine]:
        parser.error(f"This entry point runs {default_engine}")
    try:
        config, dataset, selections = load(args.config, args.dataset,
                                           args.engines or ([default_engine] if default_engine else None),
                                           args.queries, args.query_set)
        defaults = config["defaults"]
        args.runs = defaults["runs"] if args.runs is None else args.runs
        args.warmups = defaults["warmups"] if args.warmups is None else args.warmups
        requested = args.threads or defaults["threads"]
        cpus = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else list(range(os.cpu_count() or 1))
        args.all_cpus = requested == "all"
        args.threads = len(cpus) if args.all_cpus else int(requested)
        args.timeout_s = defaults["timeout_s"]
        args.docker_memory = defaults.get("docker_memory")
        if args.runs < 1 or args.warmups < 0 or not 1 <= args.threads <= len(cpus):
            raise ValueError("Invalid run, warmup or thread count")
        data, graph = repo_path(dataset["prepared"]), repo_path(dataset["graph"])
        runtime = repo_path(defaults["runtime"])
        manifest = json.loads((data / "manifest.json").read_text())
    except (OSError, KeyError, ValueError) as error:
        parser.error(str(error))
    selected = {s.engine: {"directory": str(s.directory), "ids": [q["id"] for q in s.queries],
                           "options": s.options} for s in selections}
    if args.dry_run:
        print(json.dumps(selected, indent=2))
        return
    started = now()
    stamp = started.replace(":", "").replace("+0000", "Z")
    folder = ROOT / "Results" / args.dataset / f"{stamp}-{args.name}"
    folder.mkdir(parents=True)
    lock = json.loads((ROOT / "Databases/guides/runtime-lock.json").read_text())
    metadata = {
        "started": started, "dataset": args.dataset, "prepared": str(data), "graph": str(graph),
        "manifest": str(data / "manifest.json"), "source_sha256": manifest.get("source_sha256"),
        "config": str(args.config.resolve()), "runs": args.runs, "warmups": args.warmups,
        "threads_requested": args.threads, "cpu_affinity": cpus, "docker_cpu_quota": None if args.all_cpus else args.threads,
        "docker_memory": args.docker_memory, "host": platform.node(), "platform": platform.platform(),
        "commit": git_output("rev-parse", "HEAD"), "submodules": git_output("submodule", "status", "--recursive"),
        "working_tree": git_output("status", "--short"), "competitors": selected,
    }
    (folder / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (folder / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    info = folder / "info.txt"
    info.write_text(f"Started {started}\nDataset {args.dataset}\nHost {metadata['host']}\n"
                    f"Runs {args.runs}, warmups {args.warmups}, requested threads {args.threads}\n"
                    "Engine-specific timing boundaries are recorded in result.json.\n")
    failures = []
    for selection in selections:
        out = folder / selection.engine
        (out / "build").mkdir(parents=True)
        print(f"{selection.engine} started", flush=True)
        benchmark = Benchmark(selection, data, graph, manifest, out, args, runtime, lock)
        try:
            validate(selection.engine, data, graph, manifest)
            stage_queries(selection, benchmark.query_dir)
            adapter = importlib.import_module(f".{selection.engine}.run", __package__)
            adapter.run(benchmark)
            missing = {q["id"] for q in selection.queries} - benchmark.result["measurements"].keys()
            if missing:
                raise ValueError(f"Missing measurements for {sorted(missing)}")
            if any(check["status"] != "pass" for check in benchmark.result["checks"]):
                raise ValueError(f"Answer checks failed: {benchmark.result['checks']}")
            benchmark.result["status"] = "completed"
        except Exception as error:
            benchmark.result.update(status="failed", error=str(error))
            failures.append(selection.engine)
        finally:
            benchmark.finish()
        result = benchmark.result
        with info.open("a") as stream:
            print(f"\n{selection.engine} {result['status']} from {result['started']} to {result['finished']}", file=stream)
            print(f"  Input queries {selection.directory}, IDs {', '.join(result['query_ids'])}", file=stream)
            print(f"  Timing scopes {', '.join(sorted({m['scope'] for m in result['measurements'].values()}))}", file=stream)
            if "error" in result:
                print(f"  Error {result['error']}", file=stream)
            for command in result["commands"]:
                print("  " + shlex.join(command["argv"]), file=stream)
        print(f"{selection.engine} {result['status']}", flush=True)
    with info.open("a") as stream:
        print(f"\nFinished {now()}", file=stream)
    print(folder)
    if failures:
        raise SystemExit("Failed competitors: " + ", ".join(failures))
