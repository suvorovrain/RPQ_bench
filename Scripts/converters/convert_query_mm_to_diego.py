#!/usr/bin/env python3
"""Convert numbered RPQ_bench query files to orig-nopt TSV-like format."""

from __future__ import annotations

import argparse
import glob
from pathlib import Path
from typing import Iterable


def denormalize_endpoint(token: str, *, is_subject: bool) -> str:
    if is_subject and token == "?sub":
        return "?x"
    if not is_subject and token == "?obj":
        return "?y"
    return token


def output_path_for(input_path: Path, output_dir: Path) -> Path:
    return output_dir / f"{input_path.stem}_mm.tsv"


def iter_input_paths(patterns: Iterable[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern)) if any(ch in pattern for ch in "*?[") else [pattern]
        paths.extend(path for match in matches if (path := Path(match)).is_file())
    return paths


def convert_line(raw_line: str, line_number: int, source: Path) -> str | None:
    line = raw_line.strip()
    if not line:
        return None
    if "," not in line:
        raise ValueError(f"{source}:{line_number}: expected '<number>,<subject> <path> <object>', got {raw_line!r}")

    _, query = line.split(",", 1)
    query = query.strip()

    parts = query.split()
    if len(parts) < 3:
        raise ValueError(f"{source}:{line_number}: expected '<subject> <path> <object>', got {raw_line!r}")

    subject = denormalize_endpoint(parts[0], is_subject=True)
    obj = denormalize_endpoint(parts[-1], is_subject=False)
    path_expr = " ".join(parts[1:-1])

    return f"{subject} {path_expr} {obj}#"


def convert_file(input_path: Path, output_dir: Path) -> Path:
    output_path = output_path_for(input_path, output_dir)

    converted: list[str] = []
    with input_path.open("r", encoding="utf-8") as source_file:
        for line_number, raw_line in enumerate(source_file, start=1):
            converted_line = convert_line(raw_line, line_number, input_path)
            if converted_line is not None:
                converted.append(converted_line)

    with output_path.open("w", encoding="utf-8") as target_file:
        target_file.write("\n".join(converted))
        if converted:
            target_file.write("\n")

    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert numbered RPQ_bench query files to orig-nopt TSV query format.",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help=(
            "Input file(s). Shell globs like 'RPQ_bench/Queries/*/queries.txt' are supported. "
            "If --output-dir is not used, the last positional argument is the output directory."
        ),
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        help="Directory where '*_mm.tsv' files will be written.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.output_dir is None:
        if len(args.inputs) < 2:
            raise SystemExit("Output directory is required: pass it as the last argument or use --output-dir.")
        args.output_dir = Path(args.inputs[-1])
        args.inputs = args.inputs[:-1]

    input_paths = iter_input_paths(args.inputs)
    if not input_paths:
        raise SystemExit("No input files matched.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for input_path in input_paths:
        output_path = convert_file(input_path, args.output_dir)
        print(f"{input_path} -> {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
