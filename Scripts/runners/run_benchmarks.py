#!/usr/bin/env python3
"""Run configured benchmark competitors for one or more query sets."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import tempfile
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any, Iterator, Mapping

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from benchmark_config import (  # noqa: E402
    ConfigError,
    build_context,
    discover_query_sets,
    format_template,
    load_config,
    natural_key,
    parse_overrides,
    repository_root,
    selected_competitors,
    semantic_names,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run competitors declared in Scripts/benchmark_config.json."
    )
    parser.add_argument("legacy", nargs="*", metavar="SELECTOR", help=argparse.SUPPRESS)
    parser.add_argument("--config", help="Path to another benchmark JSON config.")
    parser.add_argument("--root", help="Repository root (normally detected automatically).")
    parser.add_argument("--dataset", help="Dataset name from the config.")
    parser.add_argument(
        "--competitor", action="append", default=[],
        help="Competitor name, comma-separated names, or all. May be repeated.",
    )
    parser.add_argument("--semantic", default=None, help="Semantic name/alias or all.")
    parser.add_argument("--query-set", default=None, help="Query-set name or all.")
    parser.add_argument("--runs", type=int, help="Override the configured measured run count.")
    parser.add_argument("--warmup-runs", type=int, help="Override the configured warm-up count.")
    parser.add_argument(
        "--set", dest="overrides", action="append", default=[], metavar="NAME=VALUE",
        help="Override any template variable. May be repeated.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    parser.add_argument(
        "--no-validate-paths", action="store_true",
        help="Do not require binaries, datasets, or query files (useful with --dry-run).",
    )
    parser.add_argument(
        "--keep-going", action="store_true",
        help="Continue with other query sets and competitors after a failure.",
    )
    parser.add_argument("--list", action="store_true", help="List configured datasets and competitors.")
    args = parser.parse_args()

    if len(args.legacy) > 2:
        parser.error("legacy positional form accepts only [semantic] [query-set]")
    if args.legacy:
        if args.semantic is not None:
            parser.error("do not combine positional semantic with --semantic")
        args.semantic = args.legacy[0]
    if len(args.legacy) == 2:
        if args.query_set is not None:
            parser.error("do not combine positional query-set with --query-set")
        args.query_set = args.legacy[1]
    args.semantic = args.semantic or "all"
    args.query_set = args.query_set or "all"
    return args


def list_config(config: Mapping[str, Any]) -> None:
    print("Datasets:")
    for name, dataset in config["datasets"].items():
        print(f"  {name}: {dataset.get('description', '')}")
    print("Competitors:")
    for name, competitor in config["competitors"].items():
        print(f"  {name}: {competitor.get('label', name)}")


def query_sets_for(
    selector: str, semantic: str, context: Mapping[str, Any], validate_paths: bool
) -> list[str]:
    catalog_template = format_template(
        context["query_catalog"], {**context, "semantic": semantic}, strict=False
    )
    if selector not in ("", "all"):
        catalog = Path(format_template(catalog_template, {**context, "query_set": selector}))
        if validate_paths and not catalog.is_file():
            raise ConfigError(f"query catalog does not exist: {catalog}")
        return [selector]

    query_sets = discover_query_sets(catalog_template)
    if not query_sets:
        raise ConfigError(f"no query sets match catalog template: {catalog_template}")
    return query_sets


def require_inputs(
    binary: Path, run_config: Mapping[str, Any], context: Mapping[str, Any], query_path: Path
) -> None:
    if not binary.is_file() or not os.access(binary, os.X_OK):
        hint = format_template(run_config.get("build_hint", ""), context)
        message = f"executable does not exist or is not executable: {binary}"
        if hint:
            message += f"\n{hint}"
        raise ConfigError(message)
    if not query_path.exists():
        raise ConfigError(f"query path does not exist: {query_path}")
    for template in run_config.get("required_paths", []):
        path = Path(format_template(template, context))
        if not path.exists():
            raise ConfigError(f"required dataset path does not exist: {path}")


def run_command(
    command: list[str], output_path: Path, stdout_include_regex: str | None, dry_run: bool
) -> None:
    printable = shlex.join(command)
    if stdout_include_regex:
        printable += f" | keep-lines {shlex.quote(stdout_include_regex)} > {shlex.quote(str(output_path))}"
    print(f"+ {printable}")
    if dry_run:
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not stdout_include_regex:
        subprocess.run(command, check=True)
        return

    pattern = re.compile(stdout_include_regex)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output_path.parent,
            prefix=f".{output_path.name}.", suffix=".tmp", delete=False,
        ) as output:
            temp_name = output.name
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=None, text=True,
                encoding="utf-8", errors="replace",
            )
            assert process.stdout is not None
            for line in process.stdout:
                if pattern.search(line):
                    output.write(line)
            return_code = process.wait()
            if return_code != 0:
                raise subprocess.CalledProcessError(return_code, command)
        Path(temp_name).replace(output_path)
        temp_name = None
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


@contextmanager
def repeated_query_file(query_path: Path, repetitions: int) -> Iterator[Path]:
    try:
        queries = [
            line.rstrip("\r\n")
            for line in query_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except OSError as error:
        raise ConfigError(f"cannot read query file {query_path}: {error}") from error

    unique_queries = list(dict.fromkeys(queries))
    if len(unique_queries) != 1:
        raise ConfigError(
            f"query file must contain one repeated non-empty query: {query_path}"
        )

    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix="rpqbench-query-",
            suffix=query_path.suffix, delete=False,
        ) as output:
            temp_name = output.name
            for _ in range(repetitions):
                output.write(unique_queries[0])
                output.write("\n")
        yield Path(temp_name)
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def run_one_query_set(
    competitor_name: str,
    competitor: Mapping[str, Any],
    semantic: str,
    query_set: str,
    base_context: Mapping[str, Any],
    *,
    dry_run: bool,
    validate_paths: bool,
) -> None:
    run_config = competitor.get("run")
    if not isinstance(run_config, dict):
        raise ConfigError(f"competitor {competitor_name!r} has no run configuration")

    context = {**base_context, "semantic": semantic, "query_set": query_set}
    binary = Path(format_template(run_config["binary"], context))
    query_set_path = Path(format_template(run_config["query_path"], {**context, "binary": str(binary)}))
    context.update(binary=str(binary), query_set_path=str(query_set_path), query_path=str(query_set_path))
    if validate_paths:
        require_inputs(binary, run_config, context, query_set_path)

    query_glob = run_config.get("query_files_glob")
    if query_glob:
        query_paths = sorted(query_set_path.glob(str(query_glob)), key=lambda path: natural_key(path.name))
        if validate_paths and not query_paths:
            raise ConfigError(f"no query files match {query_set_path / str(query_glob)}")
    else:
        query_paths = [query_set_path]

    for index, query_path in enumerate(query_paths, start=1):
        repetitions_template = run_config.get("query_file_repetitions")
        repetitions = (
            int(format_template(repetitions_template, context))
            if repetitions_template is not None else None
        )
        if repetitions is not None and repetitions < 1:
            raise ConfigError("query_file_repetitions must be a positive integer")

        query_context = (
            repeated_query_file(query_path, repetitions)
            if repetitions is not None else nullcontext(query_path)
        )
        with query_context as command_query_path:
            item_context = {
                **context, "query_path": str(command_query_path),
                "query_source_path": str(query_path), "query_name": query_path.name,
                "query_stem": query_path.stem, "query_index": index,
            }
            output_path = Path(format_template(run_config["output_path"], item_context))
            item_context["output_path"] = str(output_path)
            command = [format_template(argument, item_context) for argument in run_config["command"]]
            detail = f" query {query_path.name}" if query_glob else ""
            print(f"[{competitor_name}] {semantic}/{query_set}{detail}")
            run_command(command, output_path, run_config.get("stdout_include_regex"), dry_run)


def main() -> int:
    args = parse_args()
    try:
        config, config_path = load_config(args.config)
        if args.list:
            list_config(config)
            return 0

        dataset_name = args.dataset or os.environ.get(
            "RPQBENCH_DATASET", config["defaults"]["dataset"]
        )
        root = repository_root(config_path, args.root)
        context, dataset = build_context(
            config, dataset_name, root, runs=args.runs, warmup_runs=args.warmup_runs,
            overrides=parse_overrides(args.overrides),
        )
        competitors = selected_competitors(config, dataset, args.competitor)
        semantics = semantic_names(config, args.semantic)
        dry_run = args.dry_run or os.environ.get("RPQBENCH_DRY_RUN") == "1"
        validate_paths = not args.no_validate_paths

        failures: list[str] = []
        for competitor_name, competitor in competitors:
            for semantic in semantics:
                try:
                    query_sets = query_sets_for(args.query_set, semantic, context, validate_paths)
                except (ConfigError, OSError) as error:
                    failures.append(f"{competitor_name} {semantic}: {error}")
                    if not args.keep_going:
                        raise
                    print(f"ERROR: {failures[-1]}", file=sys.stderr)
                    continue

                for query_set in query_sets:
                    try:
                        run_one_query_set(
                            competitor_name, competitor, semantic, query_set, context,
                            dry_run=dry_run, validate_paths=validate_paths,
                        )
                    except (ConfigError, OSError, subprocess.CalledProcessError) as error:
                        failures.append(f"{competitor_name} {semantic}/{query_set}: {error}")
                        print(f"ERROR: {failures[-1]}", file=sys.stderr)
                        if not args.keep_going:
                            return 1

        if failures:
            print(f"Completed with {len(failures)} failure(s).", file=sys.stderr)
            return 1
        return 0
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
