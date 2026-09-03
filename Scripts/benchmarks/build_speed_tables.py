#!/usr/bin/env python3
"""Render configured benchmark tables and histograms, including partial runs."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Any, Mapping

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from benchmark_config import (  # noqa: E402
    ConfigError,
    build_context,
    discover_query_sets,
    format_template,
    load_config,
    parse_overrides,
    repository_root,
    selected_competitors,
    semantic_names,
)


WARNED: set[str] = set()


def warn(message: str) -> None:
    if message not in WARNED:
        WARNED.add(message)
        print(f"WARNING: {message}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render benchmark reports from Scripts/benchmark_config.json."
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
    parser.add_argument("--runs", type=int, help="Override configured measured run count.")
    parser.add_argument("--warmup-runs", type=int, help="Override configured warm-up count.")
    parser.add_argument(
        "--set", dest="overrides", action="append", default=[], metavar="NAME=VALUE",
        help="Override any template variable. May be repeated.",
    )
    parser.add_argument("--output-dir", help="Override the configured report directory.")
    parser.add_argument(
        "--hide-empty-competitors", action="store_true",
        help="Omit table columns for competitors with no result in a query set.",
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
        analysis = competitor.get("analysis", {})
        print(f"  {name}: {competitor.get('label', name)} [{analysis.get('reader', 'no reader')}]")


def query_set_stem(value: str) -> str:
    for suffix in (".tsv_split", ".tsv", ".txt"):
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def catalog_template(context: Mapping[str, Any], semantic: str) -> str:
    return format_template(context["query_catalog"], {**context, "semantic": semantic}, strict=False)


def selected_query_sets(context: Mapping[str, Any], semantic: str, selector: str) -> list[str]:
    if selector not in ("", "all"):
        return [query_set_stem(selector)]
    values = discover_query_sets(catalog_template(context, semantic))
    if not values:
        raise ConfigError(f"no query sets found for semantic {semantic!r}")
    return values


def read_queries(context: Mapping[str, Any], semantic: str, query_set: str) -> list[str]:
    path = Path(
        format_template(
            context["query_catalog"],
            {**context, "semantic": semantic, "query_set": query_set},
        )
    )
    try:
        with path.open("r", encoding="utf-8") as file:
            queries = [line.strip() for line in file if line.strip()]
    except OSError as error:
        raise ConfigError(f"cannot read query catalog {path}: {error}") from error
    if not queries:
        raise ConfigError(f"query catalog is empty: {path}")
    return queries


def extract_path_expression(query: str) -> str:
    query = query.strip().rstrip("#").strip()
    if "," in query:
        query = query.split(",", 1)[1].strip()
    parts = query.split()
    return " ".join(parts[1:-1]) if len(parts) >= 3 else query


def compact_query(query: str) -> str:
    expression = extract_path_expression(query)
    labels: dict[str, str] = {}

    def replace_label(match: re.Match[str]) -> str:
        label = match.group(0)
        if label not in labels:
            index = len(labels)
            labels[label] = chr(ord("A") + index) if index < 26 else f"L{index + 1}"
        return labels[label]

    return re.sub(r"<[^>]+>", replace_label, expression)


def read_pathrex_metric(
    analysis: Mapping[str, Any],
    metric: Mapping[str, Any],
    context: Mapping[str, Any],
    expected_count: int,
) -> list[float | None]:
    path = Path(format_template(analysis["path"], context))
    values: list[float | None] = [None] * expected_count
    if not path.is_file():
        return values
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        warn(f"ignoring unreadable/incomplete result {path}: {error}")
        return values

    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        warn(f"ignoring result with unexpected JSON structure: {path}")
        return values

    algorithm = analysis.get("algorithm", "rpqmatrix")
    field = metric.get("field", analysis.get("table_metric", "total"))
    mean_key = metric.get("mean_key", "mean_ns")
    scale_to_ns = float(metric.get("scale_to_ns", 1.0))
    index_base = int(analysis.get("query_index_base", 0))
    for item in data["results"]:
        if not isinstance(item, dict):
            continue
        raw_index = item.get("query_index")
        if not isinstance(raw_index, int):
            continue
        index = raw_index - index_base
        if not 0 <= index < expected_count:
            continue
        algorithms = item.get("algorithms")
        algorithm_result = algorithms.get(algorithm) if isinstance(algorithms, dict) else None
        timing_root = algorithm_result.get("timing") if isinstance(algorithm_result, dict) else None
        timing = timing_root.get(field) if isinstance(timing_root, dict) else None
        mean = timing.get(mean_key) if isinstance(timing, dict) else None
        if isinstance(mean, (int, float)) and math.isfinite(mean):
            values[index] = float(mean) * scale_to_ns
    return values


def read_semicolon_value(
    path: Path,
    delimiter: str,
    value_column: int,
    warmup_runs: int,
    measured_runs: int,
    scale_to_ns: float,
) -> float | None:
    if not path.is_file():
        return None
    samples: list[float] = []
    try:
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                parts = line.strip().split(delimiter)
                if len(parts) <= value_column:
                    continue
                try:
                    value = float(parts[value_column]) * scale_to_ns
                except ValueError:
                    continue
                if math.isfinite(value):
                    samples.append(value)
    except OSError as error:
        warn(f"cannot read result {path}: {error}")
        return None
    required_samples = warmup_runs + measured_runs
    if len(samples) < required_samples:
        warn(
            f"incomplete result {path}: expected at least {required_samples} samples "
            f"({warmup_runs} warm-up + {measured_runs} measured), found {len(samples)}"
        )
        return None
    measured = samples[warmup_runs:required_samples]
    return sum(measured) / measured_runs


def read_semicolon_metric(
    analysis: Mapping[str, Any],
    context: Mapping[str, Any],
    expected_count: int,
) -> list[float | None]:
    delimiter = str(analysis.get("delimiter", ";"))
    value_column = int(analysis.get("value_column", 2))
    warmup_runs = int(format_template(analysis.get("warmup_runs", 0), context))
    measured_runs = int(format_template(analysis.get("runs", "{runs}"), context))
    scale_to_ns = float(format_template(analysis.get("scale_to_ns", 1.0), context))
    values = []
    for query_index in range(1, expected_count + 1):
        path = Path(format_template(analysis["path"], {**context, "query_index": query_index}))
        values.append(
            read_semicolon_value(
                path, delimiter, value_column, warmup_runs, measured_runs, scale_to_ns
            )
        )
    return values


def read_competitor_metrics(
    competitor_name: str,
    competitor: Mapping[str, Any],
    context: Mapping[str, Any],
    expected_count: int,
) -> dict[str, list[float | None]]:
    analysis = competitor.get("analysis")
    if not isinstance(analysis, dict):
        warn(f"competitor {competitor_name!r} has no analysis configuration")
        return {}
    metrics = analysis.get("metrics", {})
    reader = analysis.get("reader")
    if reader == "json_timing":
        return {
            metric_name: read_pathrex_metric(analysis, metric, context, expected_count)
            for metric_name, metric in metrics.items()
        }
    if reader == "semicolon_files":
        values = read_semicolon_metric(analysis, context, expected_count)
        return {metric_name: values for metric_name in metrics}
    warn(f"competitor {competitor_name!r} uses unknown reader {reader!r}")
    return {}


def format_time_ns(value: float | None) -> str:
    return "missing" if value is None else f"{value / 1_000_000:.3f} ms"


def color_for(value: float | None, row_values: list[float | None]) -> str:
    if value is None:
        return "#e5e7eb"
    present = [item for item in row_values if item is not None]
    if len(present) <= 1:
        return "#b7e4a5"
    fastest, slowest = min(present), max(present)
    if fastest == slowest:
        return "#d8f3c8"
    ratio = (value - fastest) / (slowest - fastest)
    red = round(183 + 56 * ratio)
    green = round(228 - 92 * ratio)
    blue = round(165 - 41 * ratio)
    return f"#{red:02x}{green:02x}{blue:02x}"


def wrap_query_label(value: str) -> str:
    if len(value) <= 22:
        return value
    return "\n".join(
        textwrap.wrap(value, width=22, break_long_words=False, break_on_hyphens=False)
    )


def table_series(
    selected: list[tuple[str, Mapping[str, Any]]],
    metric_values: Mapping[str, Mapping[str, list[float | None]]],
    hide_empty: bool,
) -> list[tuple[str, str, list[float | None]]]:
    series = []
    for name, competitor in selected:
        analysis = competitor.get("analysis", {})
        metric_name = analysis.get("table_metric")
        values = metric_values.get(name, {}).get(metric_name, [])
        if hide_empty and not any(value is not None for value in values):
            continue
        series.append((name, competitor.get("label", name), values))
    return series


def render_table(
    dataset_name: str,
    semantic: str,
    query_set: str,
    queries: list[str],
    series: list[tuple[str, str, list[float | None]]],
    output_path: Path,
) -> None:
    headers = ["query"] + [label for _, label, _ in series]
    rows: list[list[str]] = []
    colors: list[list[str]] = []
    bold: list[list[bool]] = []
    for index, query in enumerate(queries):
        values = [items[index] if index < len(items) else None for _, _, items in series]
        present = [value for value in values if value is not None]
        fastest = min(present) if present else None
        rows.append([wrap_query_label(compact_query(query))] + [format_time_ns(value) for value in values])
        colors.append(["#f7f7f7"] + [color_for(value, values) for value in values])
        bold.append(
            [False] + [
                value is not None and fastest is not None and value == fastest for value in values
            ]
        )

    competitor_count = max(1, len(series))
    fig_width = max(9.0, 3.2 + 2.0 * competitor_count)
    fig_height = max(4.0, 0.52 * len(rows) + 1.5)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=180)
    fig.patch.set_facecolor("white")
    ax.axis("off")

    first_width = 0.28 if series else 1.0
    other_width = (1.0 - first_width) / competitor_count
    widths = [first_width] + [other_width] * len(series)
    table = ax.table(
        cellText=rows, colLabels=headers, cellColours=colors,
        colColours=["#2f3437"] * len(headers), colWidths=widths,
        cellLoc="center", loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.55)
    for (row, column), cell in table.get_celld().items():
        cell.set_edgecolor("#ffffff")
        cell.set_linewidth(1.2)
        if row == 0:
            cell.set_text_props(color="white", weight="bold", fontsize=10)
        elif column == 0:
            cell.set_text_props(ha="left", fontsize=8.5)
        elif bold[row - 1][column]:
            cell.set_text_props(weight="bold")

    ax.set_title(
        f"Speed comparison: {dataset_name}/{semantic}/{query_set}",
        fontsize=15, weight="bold", pad=16,
    )
    fig.text(
        0.01, 0.015,
        "Mean total time. Missing or incomplete results are shown as missing; colors are relative within each row.",
        fontsize=8, color="#555555",
    )
    fig.tight_layout(rect=(0, 0.035, 1, 0.965))
    fig.savefig(output_path, bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


def histogram_series(
    selected: list[tuple[str, Mapping[str, Any]]],
    metric_values: Mapping[str, Mapping[str, list[float | None]]],
) -> list[tuple[str, list[float | None], str]]:
    series = []
    for name, competitor in selected:
        analysis = competitor.get("analysis", {})
        for metric_name, metric in analysis.get("metrics", {}).items():
            if not metric.get("histogram", True):
                continue
            values = metric_values.get(name, {}).get(metric_name, [])
            if any(value is not None and value > 0 for value in values):
                series.append(
                    (metric.get("label", f"{competitor.get('label', name)} {metric_name}"), values, metric.get("color", "#777777"))
                )
    return series


def render_histogram(
    dataset_name: str,
    semantic: str,
    query_set: str,
    queries: list[str],
    series: list[tuple[str, list[float | None], str]],
    output_path: Path,
) -> None:
    labels = [compact_query(query) for query in queries]
    x_positions = list(range(len(labels)))
    fig_width = max(12.0, 0.62 * len(labels) + 5.5)
    fig, ax = plt.subplots(figsize=(fig_width, 7.2), dpi=180)
    fig.patch.set_facecolor("white")

    if series:
        bar_width = min(0.18, 0.82 / len(series))
        center = (len(series) - 1) / 2
        for index, (title, values, color) in enumerate(series):
            offset = (index - center) * bar_width
            y_values = [
                value / 1_000_000 if value is not None and value > 0 else float("nan")
                for value in values
            ]
            ax.bar(
                [x + offset for x in x_positions], y_values, width=bar_width,
                label=title, color=color, edgecolor="white", linewidth=0.5,
            )
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
        present_ms = [
            value / 1_000_000
            for _, values, _ in series
            for value in values
            if value is not None and value > 0
        ]
        ax.set_ylim(min(present_ms) * 0.65, max(present_ms) * 1.5)
        ax.legend(
            ncol=min(3, len(series)), frameon=False, loc="upper center",
            bbox_to_anchor=(0.5, 1.0), fontsize=9,
        )
    else:
        ax.text(
            0.5, 0.5, "No benchmark results found",
            ha="center", va="center", transform=ax.transAxes,
        )

    ax.set_title(
        f"Execution time: {dataset_name}/{semantic}/{query_set}",
        fontsize=15, weight="bold", pad=14,
    )
    ax.set_ylabel("mean time, ms (log scale)" if series else "mean time, ms")
    ax.set_xticks(x_positions)
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=8)
    ax.grid(axis="y", color="#dddddd", linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    fig.text(
        0.01, 0.015,
        "Only available measurements are plotted. Missing competitors and individual missing queries are allowed.",
        fontsize=8, color="#555555",
    )
    fig.tight_layout(rect=(0, 0.08, 1, 0.94))
    fig.savefig(output_path, bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)


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
        selected = selected_competitors(config, dataset, args.competitor)
        semantics = semantic_names(config, args.semantic)
        output_root = Path(
            args.output_dir or format_template(context["analysis_output"], context)
        )

        for semantic in semantics:
            for query_set in selected_query_sets(context, semantic, args.query_set):
                item_context = {**context, "semantic": semantic, "query_set": query_set}
                queries = read_queries(context, semantic, query_set)
                metric_values = {
                    name: read_competitor_metrics(name, competitor, item_context, len(queries))
                    for name, competitor in selected
                }
                table_data = table_series(
                    selected, metric_values, args.hide_empty_competitors
                )
                hist_data = histogram_series(selected, metric_values)
                output_dir = output_root / semantic
                output_dir.mkdir(parents=True, exist_ok=True)
                table_path = output_dir / f"{query_set}_table.png"
                histogram_path = output_dir / f"{query_set}_hist.png"
                render_table(
                    dataset_name, semantic, query_set, queries, table_data, table_path
                )
                render_histogram(
                    dataset_name, semantic, query_set, queries, hist_data, histogram_path
                )

                coverage = []
                for name, competitor in selected:
                    analysis = competitor.get("analysis", {})
                    values = metric_values.get(name, {}).get(
                        analysis.get("table_metric"), []
                    )
                    present = sum(value is not None for value in values)
                    coverage.append(f"{name}={present}/{len(queries)}")
                print(f"{semantic}/{query_set}: " + ", ".join(coverage))
                print(table_path)
                print(histogram_path)
        return 0
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
