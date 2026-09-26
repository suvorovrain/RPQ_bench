#!/usr/bin/env python3
"""Convert PathRex queries to RPQ-matrix format and repeat every query N times."""

from __future__ import annotations

import argparse
from pathlib import Path


def denormalize_endpoint(token: str, *, is_subject: bool) -> str:
    """Map PathRex's internal endpoint names to the RPQ-matrix names."""
    if is_subject and token in {"?sub", "?x1", "?x2"}:
        return "?x"
    if not is_subject and token in {"?obj", "?x1", "?x2"}:
        return "?y"
    return token


def convert_line(raw_line: str, line_number: int, source: Path) -> str | None:
    """Convert '<id>,<subject> <path> <object>' to an RPQ-matrix query."""
    line = raw_line.strip()
    if not line:
        return None
    if "," not in line:
        raise ValueError(
            f"{source}:{line_number}: expected '<number>,<subject> <path> <object>', "
            f"got {raw_line.rstrip()!r}"
        )

    _, query = line.split(",", 1)
    parts = query.strip().split()
    if len(parts) < 3:
        raise ValueError(
            f"{source}:{line_number}: expected '<subject> <path> <object>', "
            f"got {raw_line.rstrip()!r}"
        )

    subject = denormalize_endpoint(parts[0], is_subject=True)
    obj = denormalize_endpoint(parts[-1], is_subject=False)
    path_expr = " ".join(parts[1:-1])
    return f"{subject} {path_expr} {obj}#"


def default_output_path(input_path: Path, repetitions: int) -> Path:
    return input_path.with_name(f"{input_path.stem}_rpqmatrix_x{repetitions}.txt")


def convert_and_extend(input_path: Path, output_path: Path, repetitions: int) -> int:
    """Write every converted non-empty input query ``repetitions`` times in order."""
    query_count = 0
    with input_path.open("r", encoding="utf-8") as source_file, output_path.open(
        "w", encoding="utf-8"
    ) as target_file:
        for line_number, raw_line in enumerate(source_file, start=1):
            converted = convert_line(raw_line, line_number, input_path)
            if converted is None:
                continue
            query_count += 1
            for _ in range(repetitions):
                target_file.write(converted)
                target_file.write("\n")
    return query_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a PathRex query file to RPQ-matrix format and repeat each "
            "converted query N times consecutively."
        )
    )
    parser.add_argument("input", type=Path, help="PathRex input query file.")
    parser.add_argument("repetitions", type=int, help="Number of consecutive copies per query.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output file. Defaults to '<input_stem>_rpqmatrix_xN.txt' next to the input.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.repetitions < 1:
        raise SystemExit("repetitions must be a positive integer.")
    if not args.input.is_file():
        raise SystemExit(f"input file does not exist: {args.input}")

    output_path = args.output or default_output_path(args.input, args.repetitions)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    query_count = convert_and_extend(args.input, output_path, args.repetitions)
    print(
        f"Wrote {query_count * args.repetitions} queries "
        f"({query_count} source queries × {args.repetitions}) to {output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
