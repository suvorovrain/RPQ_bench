#!/usr/bin/env python3
"""Split a query file into one repeated-query file per input line."""

from __future__ import annotations

import argparse
from pathlib import Path


def default_output_dir(input_path: Path) -> Path:
    return input_path.parent / f"{input_path.stem}_split"


def write_repeated_query(output_path: Path, query: str, repetitions: int) -> None:
    with output_path.open("w", encoding="utf-8") as output_file:
        for _ in range(repetitions):
            output_file.write(query)
            output_file.write("\n")


def split_and_extend(input_path: Path, repetitions: int, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    with input_path.open("r", encoding="utf-8") as input_file:
        for count, line in enumerate(input_file, start=1):
            query = line.rstrip("\r\n")
            write_repeated_query(output_dir / f"{count}.txt", query, repetitions)

    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create one file per query line, repeating that query N times in each file.",
    )
    parser.add_argument("input", type=Path, help="Input file with one query per line.")
    parser.add_argument("repetitions", type=int, help="How many times to repeat each query.")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        help="Output directory. Defaults to '<input_stem>_split' next to the input file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.repetitions < 1:
        raise SystemExit("repetitions must be a positive integer.")

    input_path = args.input
    if not input_path.is_file():
        raise SystemExit(f"input file does not exist: {input_path}")

    output_dir = args.output_dir if args.output_dir is not None else default_output_dir(input_path)
    written = split_and_extend(input_path, args.repetitions, output_dir)
    print(f"Wrote {written} files to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
