"""Summarize a run with timing scopes, CSV tables and per-query timing charts."""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics

from Scripts.runners.config import TOKEN


# Each display category describes the primary timer's boundary.
TIMING_CATEGORIES = {
    "native_evaluator_prepare_execute": ("Подготовка + вычисление Pathrex", "#7565a1"),
    "native_nfa_execute_materialize": ("Нативное вычисление", "#477eaf"),
    "native_matrix_solver": ("Нативное вычисление", "#477eaf"),
    "native_ring_query": ("Нативное вычисление", "#477eaf"),
    "duckdb_profile_latency": ("Задержка профиля DuckDB", "#45836d"),
    "jena_tdb_read_transaction": ("Чтение внутри транзакции Jena", "#314a65"),
    "kuzu_execution": ("Исполнение по метрике СУБД", "#338d95"),
    "postgres_executor": ("Исполнение по метрике СУБД", "#338d95"),
    "millenniumdb_execution": ("Исполнение по метрике СУБД", "#338d95"),
    "memgraph_plan_execution": ("Исполнение по метрике СУБД", "#338d95"),
    "blazegraph_query_engine": ("Исполнение по метрике СУБД", "#338d95"),
    "falkordb_internal_execution": ("Внутреннее время GRAPH.QUERY", "#866642"),
    "neo4j_bolt_run_and_stream": ("Neo4j RUN + PULL", "#6c6673"),
    "virtuoso_query_log_elapsed": ("Задержка из журнала Virtuoso", "#947a26"),
    "client_roundtrip_execute_fetch": ("Клиент + сеть", "#c87939"),
    "embedded_execute_fetch": ("Внутри процесса", "#45836d"),
    "in_jvm_tdb_parse_execute_fetch": ("Внутри JVM", "#7565a1"),
}


def read_measurements(folder):
    metadata = json.loads((folder / "metadata.json").read_text())
    rows = []
    raw = []
    failed = {}
    for engine in metadata["competitors"]:
        if not TOKEN.fullmatch(engine):
            raise ValueError(f"Invalid competitor name: {engine}")
        path = folder / engine / "result.json"
        if not path.is_file():
            failed[engine] = "missing result.json"
            continue
        result = json.loads(path.read_text())
        if result["status"] != "completed":
            failed[engine] = result.get("error", result["status"])
            continue
        for record in result["measurements"].values():
            if not TOKEN.fullmatch(record["id"]):
                raise ValueError(f"Invalid query ID: {record['id']}")
            scopes = [(record["scope"], record["samples_ms"])]
            if "ffi_only_samples_ms" in record:
                scopes.append(("native_prepared_execute", record["ffi_only_samples_ms"]))
            scopes.extend(record.get("phase_samples_ms", {}).items())
            for scope, samples in scopes:
                if len(samples) != metadata["runs"] or any(not math.isfinite(x) or x < 0 for x in samples):
                    raise ValueError(f"Invalid samples: {engine}/{record['id']}/{scope}")
                key = dict(engine=engine, query_id=record["id"], pattern=record["pattern"], scope=scope,
                           resolution_ms=record.get("resolution_ms"), chart=scope == record["scope"])
                rows.append(dict(**key, verification=record["verification"], runs=len(samples),
                                 expected_count=record["expected_count"],
                                 count_metric=record.get("count_metric", "reachable_targets"), mean_ms=statistics.mean(samples),
                                 median_ms=statistics.median(samples),
                                 stdev_ms=statistics.stdev(samples) if len(samples) > 1 else 0,
                                 min_ms=min(samples), max_ms=max(samples)))
                raw.extend(dict(**key, iteration=i, time_ms=value) for i, value in enumerate(samples))
    return metadata, rows, raw, failed


def write_table(path, rows):
    if rows:
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def timing_charts(raw, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    from matplotlib.ticker import FuncFormatter

    native = ("Нативный таймер", "#477eaf")

    grouped = {}
    id_map = {}
    for r in raw:
        if not r["chart"]:
            continue
        # The same ID can be reused by an engine-specific suite for a different pattern.
        key = r["query_id"], r["pattern"]
        group = grouped.setdefault(key, {})
        group.setdefault((r["engine"], r["scope"]), []).append(r["time_ms"])
    for (qid, pattern), data in grouped.items():
        id_map[qid] = id_map.get(qid, 0) + 1
        positive = [value for samples in data.values() for value in samples if value > 0]
        fig, ax = plt.subplots(figsize=(max(8, 0.85 * len(data)), 5.6), layout="constrained")
        ax.set_yscale("log")
        low, high = (min(positive) / 1.8, max(positive) * 2.3) if positive else (0.1, 1)
        ax.set_ylim(low, high)
        if not positive:
            ax.yaxis.set_visible(False)
        ax.set_axisbelow(True)
        ax.grid(axis="y", which="major", alpha=0.25)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
        labels = []
        legend = {}
        for x, ((engine, scope), samples) in enumerate(data.items()):
            labels.append(engine)
            label, color = TIMING_CATEGORIES.get(scope, native)
            legend.setdefault(label, Patch(facecolor=color, label=label))
            median = statistics.median(samples)
            if median > 0:
                ax.bar(x, median - low, bottom=low, width=0.66, color=color, alpha=0.85)
            offsets = [0] if len(samples) == 1 else [
                0.38 * (i / (len(samples) - 1) - 0.5) for i in range(len(samples))
            ]
            points = [(x + offset, value) for offset, value in zip(offsets, samples) if value > 0]
            if points:
                ax.scatter(*zip(*points), s=13, color="#20262e", zorder=3)
            zeros = samples.count(0)
            annotation = f"{median:.3g}"
            if zeros:
                annotation += f"\nнулей: {zeros}/{len(samples)}"
            ax.annotate(annotation, (x, max(max(samples), low)), xytext=(0, 5),
                        textcoords="offset points", ha="center", fontsize=8)
        ax.set_xticks(range(len(labels)), labels, rotation=35, ha="right")
        ax.set_title(f"Q{qid} · {pattern}\nСтолбец — медиана, точки — отдельные замеры", wrap=True)
        ax.set_xlabel("Движок")
        ax.set_ylabel("Время запроса, мс · логарифмическая шкала")
        ax.legend(handles=list(legend.values()), loc="upper left", ncols=min(4, len(legend)),
                  fontsize="small")
        fig.savefig(out / f"timings-{qid}-{id_map[qid]}.png", dpi=160)
        plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tables-only", action="store_true")
    args = parser.parse_args()
    meta, rows, raw, failed = read_measurements(args.run)
    if not rows:
        parser.error(f"No completed results. Failures: {failed}")
    output = args.output or args.run / "analysis"
    output.mkdir(parents=True, exist_ok=True)
    write_table(output / "summary.csv", rows)
    write_table(output / "samples.csv", raw)
    (output / "summary.json").write_text(json.dumps({"dataset": meta["dataset"], "results": rows,
                                                     "failed": failed}, indent=2) + "\n")
    if not args.tables_only:
        timing_charts(raw, output)
    print(output)


if __name__ == "__main__":
    main()
