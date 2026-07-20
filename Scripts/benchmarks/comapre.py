#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt


SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Competitor:
    name: str
    answers_path: str

    def resolved_answers_path(self, query_kind: str) -> Path:
        path = Path(self.answers_path.format(query_kind=query_kind))
        if path.is_absolute():
            return path
        return (SCRIPT_DIR / path).resolve()


# Add new competitors here.
COMPETITORS = [
    Competitor(
        name="pathrex",
        answers_path="../../Answers/pathrex/{query_kind}/answers.txt",
    ),
    Competitor(
        name="rpq-matrix",
        answers_path="../../Answers/rpqmatrix/{query_kind}/answers.txt",
    ),
    Competitor(
        name="rpq-matrix_GB",
        answers_path="../../benchmark_result/{query_kind}/answers.txt"
    )
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a table comparing RPQ competitors.",
    )
    parser.add_argument("queries_file", type=Path, help="File with benchmark queries.")
    parser.add_argument("query_kind", help="Query kind, for example: any-any, con-any, any-con.")
    return parser.parse_args()


def read_queries(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as file:
        return [line.strip() for line in file if line.strip()]


def parse_time_ns(line: str) -> int | None:
    stripped = line.strip()
    if not stripped:
        return None

    numbers = re.findall(r"-?\d+", stripped)
    if not numbers:
        return None

    return int(numbers[-1])


def read_times(path: Path, expected_count: int) -> list[int | None]:
    if not path.exists():
        return [None] * expected_count

    values: list[int | None] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            value = parse_time_ns(line)
            if value is not None:
                values.append(value)

    if len(values) < expected_count:
        values.extend([None] * (expected_count - len(values)))
    return values[:expected_count]


def time_to_color(value: int | None, row_values: list[int | None]) -> str:
    if value is None:
        return "#dddddd"

    present_values = [item for item in row_values if item is not None]
    if len(present_values) <= 1:
        return "#9be29b"

    fastest = min(present_values)
    slowest = max(present_values)
    if fastest == slowest:
        return "#fff2a8"

    ratio = (value - fastest) / (slowest - fastest)
    red = int(80 + 175 * ratio)
    green = int(80 + 175 * (1 - ratio))
    blue = 80
    return f"#{red:02x}{green:02x}{blue:02x}"


def format_time(value: int | None) -> str:
    if value is None:
        return "missing"
    return f"{value:,}".replace(",", " ")


def shorten_query(query: str, limit: int = 90) -> str:
    if len(query) <= limit:
        return query
    return f"{query[: limit - 3]}..."


def build_table(queries: list[str], query_kind: str) -> Path:
    results = [
        (competitor, read_times(competitor.resolved_answers_path(query_kind), len(queries)))
        for competitor in COMPETITORS
    ]

    header = ["query", *[competitor.name for competitor, _ in results]]
    rows = []
    cell_colors = []

    for index, query in enumerate(queries):
        row_values = [times[index] for _, times in results]
        rows.append([shorten_query(query), *[format_time(value) for value in row_values]])
        cell_colors.append(["#f4f4f4", *[time_to_color(value, row_values) for value in row_values]])

    fig_width = max(10, 4 + 2.2 * len(COMPETITORS))
    fig_height = max(3, 0.45 * (len(rows) + 1))
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.axis("off")

    table = ax.table(
        cellText=rows,
        colLabels=header,
        cellColours=cell_colors,
        colColours=["#222222"] * len(header),
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.4)

    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#ffffff")
        if row == 0:
            cell.set_text_props(color="white", weight="bold")
        elif col == 0:
            cell.set_text_props(ha="left")

    output_dir = SCRIPT_DIR / "benchmark_results" / query_kind
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "res.png"
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)

    return output_path


def main() -> int:
    args = parse_args()
    queries = read_queries(args.queries_file)
    if not queries:
        raise SystemExit(f"No queries found in {args.queries_file}")

    output_path = build_table(queries, args.query_kind)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
