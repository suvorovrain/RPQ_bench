#!/usr/bin/env python3
"""Convert a MatrixMarket directory into rpq-matrix_GB dataset layout."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


DEFAULT_BASE_NAME = "rpqbench_250k_orig.nt.dat"


def numbered_matrix_paths(mm_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for path in mm_dir.iterdir():
        if path.is_file() and path.suffix == ".txt" and path.stem.isdigit():
            paths.append(path)
    return sorted(paths, key=lambda path: int(path.stem))


def convert_mapping(input_path: Path, output_path: Path) -> int:
    count = 0
    with input_path.open("r", encoding="utf-8") as source, output_path.open("w", encoding="utf-8") as target:
        for line_number, raw_line in enumerate(source, start=1):
            line = raw_line.strip()
            if not line:
                continue

            parts = line.rsplit(maxsplit=1)
            if len(parts) != 2:
                raise ValueError(f"{input_path}:{line_number}: expected '<name> <id>', got {raw_line!r}")

            name, idx = parts
            if not idx.isdigit():
                raise ValueError(f"{input_path}:{line_number}: id is not a positive integer: {idx!r}")

            target.write(f"{idx} {name}\n")
            count += 1
    return count


def remove_existing_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()


def place_matrix(source: Path, target: Path, copy_files: bool) -> None:
    remove_existing_path(target)
    if copy_files:
        shutil.copy2(source, target)
    else:
        target.symlink_to(source.resolve())


def convert(mm_dir: Path, base_path: Path, copy_files: bool) -> tuple[int, int, int]:
    vertices = mm_dir / "vertices.txt"
    edges = mm_dir / "edges.txt"
    if not vertices.is_file():
        raise FileNotFoundError(f"missing vertices mapping: {vertices}")
    if not edges.is_file():
        raise FileNotFoundError(f"missing edges mapping: {edges}")

    matrices = numbered_matrix_paths(mm_dir)
    if not matrices:
        raise FileNotFoundError(f"no numbered MatrixMarket files found in {mm_dir}")

    base_path.parent.mkdir(parents=True, exist_ok=True)
    base_path.touch(exist_ok=True)
    matrix_dir = Path(f"{base_path}.baseline-64")
    matrix_dir.mkdir(parents=True, exist_ok=True)

    vertices_count = convert_mapping(vertices, Path(f"{base_path}.SO"))
    edges_count = convert_mapping(edges, Path(f"{base_path}.P"))

    for matrix_path in matrices:
        target_name = f"{int(matrix_path.stem):04d}.mat"
        place_matrix(matrix_path, matrix_dir / target_name, copy_files)

    return vertices_count, edges_count, len(matrices)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a MatrixMarket directory with vertices.txt, edges.txt, and N.txt files "
            "to the layout expected by rpq-matrix_GB."
        ),
    )
    parser.add_argument("mm_dir", type=Path, help="Input MatrixMarket directory.")
    parser.add_argument(
        "base_name_arg",
        nargs="?",
        help=f"Output dataset base filename inside mm_dir. Default: {DEFAULT_BASE_NAME}",
    )
    parser.add_argument(
        "-b",
        "--base-name",
        help=(
            "Output dataset base filename inside mm_dir. "
            "Overrides the positional base name when both are provided."
        ),
    )
    parser.add_argument(
        "-o",
        "--output-base",
        type=Path,
        help=(
            "Full output dataset base path. Overrides --base-name. "
            "Example: /path/to/dataset/rpqbench_250k_orig.nt.dat"
        ),
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy matrix files instead of creating symlinks.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mm_dir = args.mm_dir.resolve()
    if not mm_dir.is_dir():
        raise SystemExit(f"input directory does not exist: {mm_dir}")

    base_name = args.base_name or args.base_name_arg or DEFAULT_BASE_NAME
    base_path = args.output_base.resolve() if args.output_base else mm_dir / base_name

    try:
        vertices_count, edges_count, matrix_count = convert(mm_dir, base_path, args.copy)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    mode = "copied" if args.copy else "linked"
    print(f"Dataset base: {base_path}")
    print(f"Wrote {vertices_count} vertices to {base_path}.SO")
    print(f"Wrote {edges_count} edges to {base_path}.P")
    print(f"{mode.capitalize()} {matrix_count} matrices to {base_path}.baseline-64")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
