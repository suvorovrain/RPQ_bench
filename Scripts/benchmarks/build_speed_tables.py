#!/usr/bin/env python3
"""Build speed comparison tables for RPQ_bench competitors."""

from __future__ import annotations

import json
import math
import os
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter


BENCH_ROOT = Path("/media/rpq/rpq/RPQ_bench")
RESULTS_ROOT = BENCH_ROOT / "Results" / "rpqbench_250k"
QUERIES_ROOT = BENCH_ROOT / "Queries"
OUTPUT_DIR = BENCH_ROOT / "Scripts" / "benchmarks" / "benchmark_results"
SEMANTICS = ("any-any", "any-con", "con-any")
WARMUP_RUNS = 5
HEADERS = ("запрос", "pathrex", "rpqmatrix", "rpqmatrix_GB", "pathrex_test")


@dataclass(frozen=True)
class Competitor:
    title: str
    kind: str
    path: Path


COMPETITORS = (
    Competitor("pathrex", "pathrex_json", RESULTS_ROOT / "pathrex"),
    Competitor("rpqmatrix", "matrix_dir", RESULTS_ROOT / "rpq-matrix"),
    Competitor("rpqmatrix_GB", "matrix_dir", RESULTS_ROOT / "rpq-matrix_GB"),
    Competitor("pathrex_test", "pathrex_json", RESULTS_ROOT / "pathrex-test"),
)

HISTOGRAM_SERIES = (
    ("pathrex ffi", RESULTS_ROOT / "pathrex", "pathrex_ffi", "#6baed6"),
    ("pathrex total", RESULTS_ROOT / "pathrex", "pathrex_total", "#2171b5"),
    ("rpqmatrix", RESULTS_ROOT / "rpq-matrix", "matrix", "#74c476"),
    ("rpqmatrix_GB", RESULTS_ROOT / "rpq-matrix_GB", "matrix", "#815394"),
    ("pathrex_test ffi", RESULTS_ROOT / "pathrex-test", "pathrex_ffi", "#fdae6b"),
    ("pathrex_test total", RESULTS_ROOT / "pathrex-test", "pathrex_total", "#e6550d"),
)


def query_file(semantic: str) -> Path:
    return QUERIES_ROOT / "rpqmatrix" / "rpqbench_250k" / semantic / "queries_mm.tsv"


def read_queries(semantic: str) -> list[str]:
    path = query_file(semantic)
    with path.open("r", encoding="utf-8") as file:
        return [line.strip() for line in file if line.strip()]


def extract_path_expression(query: str) -> str:
    query = query.strip().rstrip("#").strip()
    if "," in query:
        query = query.split(",", 1)[1].strip()

    parts = query.split()
    if len(parts) < 3:
        return query
    return " ".join(parts[1:-1])


def compact_query(query: str) -> str:
    expr = extract_path_expression(query)
    labels: dict[str, str] = {}

    def replace_label(match: re.Match[str]) -> str:
        label = match.group(0)
        if label not in labels:
            labels[label] = chr(ord("A") + len(labels)) if len(labels) < 26 else f"L{len(labels) + 1}"
        return labels[label]

    return re.sub(r"<[^>]+>", replace_label, expr)


def read_pathrex_means(base_dir: Path, semantic: str, expected_count: int, metric: str = "total") -> list[float | None]:
    path = base_dir / semantic / "res.json"
    if not path.is_file():
        return [None] * expected_count

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    values: list[float | None] = [None] * expected_count
    for item in data.get("results", []):
        index = item.get("query_index")
        if not isinstance(index, int) or not 0 <= index < expected_count:
            continue

        timing = (
            item.get("algorithms", {})
            .get("rpqmatrix", {})
            .get("timing", {})
            .get(metric, {})
        )
        mean = timing.get("mean_ns")
        if isinstance(mean, (int, float)) and math.isfinite(mean):
            values[index] = float(mean)

    return values


def read_matrix_mean(path: Path) -> float | None:
    if not path.is_file():
        return None

    times: list[float] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            parts = line.strip().split(";")
            if len(parts) < 3:
                continue
            try:
                times.append(float(parts[2]))
            except ValueError:
                continue

    measured = times[WARMUP_RUNS:]
    if not measured:
        return None
    return sum(measured) / len(measured)


def read_matrix_means(base_dir: Path, semantic: str, expected_count: int) -> list[float | None]:
    result_dir = base_dir / semantic
    return [read_matrix_mean(result_dir / f"{index}.txt") for index in range(1, expected_count + 1)]


def competitor_values(competitor: Competitor, semantic: str, expected_count: int) -> list[float | None]:
    if competitor.kind == "pathrex_json":
        return read_pathrex_means(competitor.path, semantic, expected_count)
    if competitor.kind == "matrix_dir":
        return read_matrix_means(competitor.path, semantic, expected_count)
    raise ValueError(f"unknown competitor kind: {competitor.kind}")


def histogram_values(kind: str, path: Path, semantic: str, expected_count: int) -> list[float | None]:
    if kind == "pathrex_ffi":
        return read_pathrex_means(path, semantic, expected_count, "ffi_only")
    if kind == "pathrex_total":
        return read_pathrex_means(path, semantic, expected_count, "total")
    if kind == "matrix":
        return read_matrix_means(path, semantic, expected_count)
    raise ValueError(f"unknown histogram series kind: {kind}")


def color_for(value: float | None, row_values: list[float | None]) -> str:
    if value is None:
        return "#e5e7eb"

    present = [item for item in row_values if item is not None]
    if len(present) <= 1:
        return "#b7e4a5"

    fastest = min(present)
    slowest = max(present)
    if fastest == slowest:
        return "#d8f3c8"

    ratio = (value - fastest) / (slowest - fastest)
    red = round(183 + 56 * ratio)
    green = round(228 - 92 * ratio)
    blue = round(165 - 41 * ratio)
    return f"#{red:02x}{green:02x}{blue:02x}"


def format_time_ns(value: float | None) -> str:
    if value is None:
        return "missing"
    return f"{value / 1_000_000:.3f} ms"


def format_cell_text(value: float | None, row_values: list[float | None]) -> str:
    present = [item for item in row_values if item is not None]
    is_fastest = value is not None and present and value == min(present)
    text = format_time_ns(value)
    if is_fastest:
        text = f"{text}"
    return text


def wrap_query_label(value: str) -> str:
    if len(value) <= 22:
        return value
    return "\n".join(textwrap.wrap(value, width=22, break_long_words=False, break_on_hyphens=False))


def build_table_data(semantic: str) -> tuple[list[list[str]], list[list[str]], list[list[bool]]]:
    queries = read_queries(semantic)
    all_values = [
        competitor_values(competitor, semantic, len(queries))
        for competitor in COMPETITORS
    ]

    cell_text: list[list[str]] = []
    cell_colors: list[list[str]] = []
    bold_cells: list[list[bool]] = []

    for index, query in enumerate(queries):
        row_values = [values[index] for values in all_values]
        present = [item for item in row_values if item is not None]
        fastest = min(present) if present else None

        cell_text.append(
            [wrap_query_label(compact_query(query))]
            + [format_cell_text(value, row_values) for value in row_values]
        )
        cell_colors.append(["#f7f7f7"] + [color_for(value, row_values) for value in row_values])
        bold_cells.append([False] + [value is not None and fastest is not None and value == fastest for value in row_values])

    return cell_text, cell_colors, bold_cells


def render_table(semantic: str, output_path: Path) -> None:
    rows, colors, bold_cells = build_table_data(semantic)
    row_count = len(rows)
    fig_width = 11.5
    fig_height = max(4.0, 0.52 * row_count + 1.5)

    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=180)
    fig.patch.set_facecolor("white")
    ax.axis("off")

    table = ax.table(
        cellText=rows,
        colLabels=HEADERS,
        cellColours=colors,
        colColours=["#2f3437"] * len(HEADERS),
        colWidths=[0.25, 0.18, 0.18, 0.205, 0.185],
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.55)

    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#ffffff")
        cell.set_linewidth(1.2)
        if row == 0:
            cell.set_height(0.07)
            cell.set_text_props(color="white", weight="bold", fontsize=10)
        else:
            cell.set_height(0.052)
            if col == 0:
                cell.set_text_props(ha="left", fontsize=8.5)
            elif bold_cells[row - 1][col]:
                cell.set_text_props(weight="bold")

    ax.set_title(f"Speed comparison: {semantic}", fontsize=15, weight="bold", pad=16)
    fig.text(
        0.01,
        0.015,
        "Mean total time, ms. rpq-matrix/rpq-matrix_GB: first 5 runs discarded as warm-up. Green is faster, red is slower per row.",
        fontsize=8,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.035, 1, 0.965))
    fig.savefig(output_path, bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def render_histogram(semantic: str, output_path: Path) -> None:
    queries = read_queries(semantic)
    labels = [compact_query(query) for query in queries]
    x_positions = list(range(len(labels)))
    series_values = [
        (title, histogram_values(kind, path, semantic, len(labels)), color)
        for title, path, kind, color in HISTOGRAM_SERIES
    ]

    fig_width = max(15.0, 0.62 * len(labels) + 6.5)
    fig_height = 7.2
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=180)
    fig.patch.set_facecolor("white")

    bar_width = 0.13
    offsets = [(-2.5 + index) * bar_width for index in range(len(series_values))]
    for offset, (title, values, color) in zip(offsets, series_values):
        y_values = [(value / 1_000_000) if value is not None else float("nan") for value in values]
        ax.bar(
            [x + offset for x in x_positions],
            y_values,
            width=bar_width,
            label=title,
            color=color,
            edgecolor="white",
            linewidth=0.5,
        )

    ax.set_title(f"Execution time histogram: {semantic}", fontsize=15, weight="bold", pad=14)
    ax.set_ylabel("mean time, ms (log scale)")
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
    ax.grid(axis="y", color="#dddddd", linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    ax.legend(ncol=3, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.0), fontsize=9)

    present_ms = [
        value / 1_000_000
        for _, values, _ in series_values
        for value in values
        if value is not None
    ]
    ax.set_ylim(min(present_ms) * 0.65, max(present_ms) * 1.5)

    fig.text(
        0.01,
        0.015,
        "Log-scale Y axis. Pathrex bars are split into ffi and total time. rpqmatrix/rpqmatrix_GB bars are means after discarding first 5 runs.",
        fontsize=8,
        color="#555555",
    )
    fig.tight_layout(rect=(0, 0.08, 1, 0.94))
    fig.savefig(output_path, bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for semantic in SEMANTICS:
        legacy_path = OUTPUT_DIR / f"{semantic}.png"
        if legacy_path.exists():
            legacy_path.unlink()

        table_path = OUTPUT_DIR / f"{semantic}_table.png"
        histogram_path = OUTPUT_DIR / f"{semantic}_hist.png"
        render_table(semantic, table_path)
        render_histogram(semantic, histogram_path)
        print(table_path)
        print(histogram_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
