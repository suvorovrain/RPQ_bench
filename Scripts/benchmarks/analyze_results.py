#!/usr/bin/env python3
"""Analyze result directories using per-file repetition metadata and raw timings."""

import argparse
import csv
import json
import math
import os
from pathlib import Path
import re
import random
import statistics as stats

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
ORDER = ["join", "metaac", "mnc", "hybrid", "pang-hybrid", "sampling", "rpqmatrix", "rpqmatrix-gb"]
COMPACT_ORDER = ['pang-hybrid', 'rpqmatrix-gb']
SEMANTICS = {"sparql-queries-any-con": "Any–Con", "sparql-queries_CON_ANY": "Con–Any", "only-any-safe": "Any–Any"}
WINNER_COLORS = {
    frozenset({'total'}): ('#17622b', '#dff2e1'),
    frozenset({'ffi_only'}): ('#174b9b', '#dceafb'),
    frozenset({'total', 'ffi_only'}): ('#17622b', '#dceafb'),
}
WINNER_LEGEND = 'Best total: green; best ffi-only: blue; best in both: green text on blue background.'


def single_label_closure(query):
    expression = ''.join(query.split()[1:-1])
    # Parentheses do not change a single-label closure. Do not remove other operators.
    expression = re.sub(r'<[^>]+>|[()]', lambda match: '' if match.group() in ('(', ')') else match.group(), expression)
    return re.fullmatch(r'<[^<>]+>[*+]', expression) is not None


def simple_binary_path(query):
    """Match two-label Seq/Alt, optionally enclosed in a whole-path * or +."""
    expression = re.sub(r'<[^<>]+>', 'L', ''.join(query.split()[1:-1]))
    # Remove parentheses around leaves only; keep operator grouping intact.
    while '(L)' in expression:
        expression = expression.replace('(L)', 'L')

    def unwrap(value):
        while value.startswith('(') and value.endswith(')'):
            depth = 0
            for index, char in enumerate(value):
                depth += (char == '(') - (char == ')')
                if depth == 0:
                    break
            if index != len(value) - 1:
                break
            value = value[1:-1]
        return value

    expression = unwrap(expression)
    if expression.endswith(('*', '+')):
        expression = expression[:-1]
        # A/B* is not (A/B)*: a binary closure requires a grouped operand.
        if not (expression.startswith('(') and expression.endswith(')')):
            return False
        expression = unwrap(expression)
    return re.fullmatch(r'L[/|]L', expression) is not None


def write_csv(path, rows, fields=None):
    fields = fields or list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: f"{value:.9f}" if isinstance(value, float) else value for key, value in row.items()} for row in rows)


def measurement(semantic, competitor, mode, query_id, samples, runs, warmup, status="ok", error="", query=""):
    if any(not math.isfinite(value) or value < 0 for value in samples):
        raise ValueError(f"invalid timing: {semantic}/{competitor}/{query_id}")
    if status == "ok" and len(samples) != runs:
        status, error = "incomplete", f"expected {runs} measurements, found {len(samples)}"
    if status == "ok" and any(value == 0 for value in samples):
        status, error = "zero_time", "zero time is not a valid timed execution"
    mean = stats.mean(samples) if samples else None
    sd = stats.stdev(samples) if len(samples) > 1 else None
    return {"semantic": semantic, "competitor": competitor, "mode": mode, "query_id": str(query_id),
            "status": status, "runs": runs, "warmup_runs": warmup, "observed_runs": len(samples),
            "mean_ms": mean, "stddev_ms": sd,
            "rsd_percent": 100 * sd / mean if sd is not None and mean and status == "ok" else None,
            "query_text": query, "error": error, "samples": samples}


def load_results(root):
    rows, inventory = [], []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        semantic = directory.name
        for engine in sorted(directory.iterdir()):
            if not engine.is_dir():
                continue
            summary, text = engine / "res.json", engine / "res.txt"
            if summary.exists():
                data = json.loads(summary.read_text())
                raw = json.loads((engine / "res.runs.json").read_text())
                metadata = data["metadata"]
                runs, warmup = metadata["runs"], metadata["warm_up_runs"]
                if raw["metadata"] != metadata:
                    raise ValueError(f"raw/summary metadata differ: {engine}")
                raw_by_id = {str(item["query_id"]): item for item in raw["results"]}
                if len(raw_by_id) != len(raw["results"]):
                    raise ValueError(f"duplicate raw query IDs: {engine}")
                ids = set()
                for item in data["results"]:
                    query_id = str(item["query_id"])
                    if query_id in ids:
                        raise ValueError(f"duplicate query ID: {engine}/{query_id}")
                    ids.add(query_id)
                    result = item["algorithms"]["rpqmatrix"]
                    for mode in ("total", "ffi_only"):
                        samples = raw_by_id.get(query_id, {}).get("algorithms", {}).get("rpqmatrix", {}).get(mode + "_ns", [])
                        if result["status"] == "ok":
                            timing = result["timing"][mode]
                            if timing["iterations"] != runs or len(samples) != runs:
                                raise ValueError(f"repetition count mismatch: {engine}/{query_id}/{mode}")
                            if not math.isclose(stats.mean(samples), timing["mean_ns"], rel_tol=1e-9, abs_tol=0.1):
                                raise ValueError(f"raw/summary mean mismatch: {engine}/{query_id}/{mode}")
                            if not math.isclose(stats.pstdev(samples), timing["stddev_ns"], rel_tol=1e-9, abs_tol=0.1):
                                raise ValueError(f"raw/summary stddev mismatch: {engine}/{query_id}/{mode}")
                        rows.append(measurement(semantic, engine.name, mode, query_id, [x / 1e6 for x in samples],
                                                runs, warmup, result["status"], result.get("error", ""), item["query_text"]))
                if set(raw_by_id) - ids:
                    raise ValueError(f"raw query IDs absent from summary: {engine}")
                inventory.append({"semantic": semantic, "competitor": engine.name, "runs": runs,
                                  "warmup_runs": warmup, "query_count": len(ids), "source": str(summary)})
            elif text.exists():
                metadata = json.loads(text.with_name(text.name + ".meta.json").read_text())
                runs, warmup = metadata["runs"], metadata["warmup_runs"]
                ids = [str(value) for value in metadata["query_ids"]]
                if len(ids) != len(set(ids)):
                    raise ValueError(f"duplicate metadata IDs: {engine}")
                grouped = {query_id: [] for query_id in ids}
                for line in text.read_text().splitlines():
                    if not line.strip():
                        continue
                    query_id, _, duration = line.split(";")
                    if query_id not in grouped:
                        raise ValueError(f"unknown baseline query ID: {engine}/{query_id}")
                    grouped[query_id].append(float(duration) / 1e6)
                for query_id, values in grouped.items():
                    complete = len(values) == runs + warmup
                    samples = values[warmup:] if complete else []
                    rows.append(measurement(semantic, engine.name, "overall", query_id, samples, runs, warmup,
                                            "ok" if complete else "incomplete",
                                            "" if complete else f"expected {runs + warmup} rows, found {len(values)}"))
                inventory.append({"semantic": semantic, "competitor": engine.name, "runs": runs,
                                  "warmup_runs": warmup, "query_count": len(ids), "source": str(text)})
    if not rows:
        raise ValueError(f"no results found in {root}")
    return rows, inventory


def best_cells(fields, rows):
    winners = {}
    for row_index, row in enumerate(rows):
        metric = row.get('Metric', '')
        speedup = metric.endswith('speedup')
        maximize = speedup or metric.startswith('Fastest queries')
        for mode in ('total', 'ffi_only'):
            if mode == 'ffi_only' and (speedup or maximize):
                continue
            candidates = []
            for column, field in enumerate(fields):
                parts = field.split(' | ')
                if len(parts) < 2 or (len(parts) > 2 and not field.endswith(' | Mean, ms')):
                    continue
                # Overall speedups participate only in the Total comparison.
                modes = (mode, 'overall') if mode == 'total' or not speedup else (mode,)
                value = row[field]
                if parts[1] in modes and isinstance(value, (int, float)) and math.isfinite(value):
                    candidates.append((column, value))
            if candidates:
                best = (max if maximize else min)(value for column, value in candidates)
                for column, value in candidates:
                    if math.isclose(value, best, rel_tol=1e-12, abs_tol=0):
                        winners.setdefault((row_index, column), set()).add(mode)
    return winners


def count_wins(variants, lookup, query_ids):
    counts = {variant: 0 for variant in variants}
    for query_id in query_ids:
        best = min(lookup[name, mode, query_id]['mean_ms'] for name, mode in variants)
        for name, mode in variants:
            if math.isclose(lookup[name, mode, query_id]['mean_ms'], best, rel_tol=1e-12, abs_tol=0):
                counts[name, mode] += 1
    return counts


def compact_summary(out, title, variants, lookup, query_ids, reference='rpqmatrix-gb'):
    total = [(name, 'overall' if name == 'rpqmatrix-gb' else 'total') for name in COMPACT_ORDER]
    execute = [(name, 'ffi_only') for name in COMPACT_ORDER if name != 'rpqmatrix-gb']
    if not set(total + execute).issubset(variants):
        raise ValueError('compact summary requires all five competitors and both Pathrex timing modes')
    if reference not in COMPACT_ORDER:
        raise ValueError('compact speedup reference must be a selected competitor')
    wins = count_wins(total, lookup, query_ids)
    aggregates = {}
    reference_mode = 'overall' if (reference, 'overall') in variants else 'total'
    for name, mode in total + execute:
        values = [lookup[name, mode, query_id]['mean_ms'] for query_id in query_ids]
        ratios = [lookup[reference, reference_mode, query_id]['mean_ms'] / value
                  for query_id, value in zip(query_ids, values)] if mode != 'ffi_only' else []
        aggregates[name, mode] = [sum(values), stats.mean(values), stats.median(values),
                                 stats.mean(ratios) if ratios else None,
                                 stats.median(ratios) if ratios else None, wins.get((name, mode))]
    metrics = ['Sum, ms', 'Mean, ms', 'Median, ms', 'Mean speedup', 'Median speedup',
               f'Fastest queries (of {len(query_ids)})']
    columns = [name if name != 'rpqmatrix-gb' else 'RPQ-matrix_GB' for name in COMPACT_ORDER]
    numeric = [[(aggregates[name, mode][index],
                 aggregates[name, 'ffi_only'][index] if name != 'rpqmatrix-gb' else None)
                for name, mode in total] for index in range(len(metrics))]

    def formatted(value):
        return '—' if value is None else str(value) if isinstance(value, int) else f'{value:,.3f}'

    rows = [{'Metric': metric, **{f'{column} (total / exec)': formatted(a) if metric.endswith('speedup') or metric.startswith('Fastest queries') else f'{formatted(a)} / {formatted(b)}'
                                 for column, (a, b) in zip(columns, values)}}
            for metric, values in zip(metrics, numeric)]
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / 'summary.csv', rows)

    fig, ax = plt.subplots(figsize=(17, 4))
    ax.axis('off')
    ax.set_title(f'{title} — {len(query_ids)} common queries; reference: {reference}\n'
                 'Best times: Total green, Exec blue; speedup and win counts: Total only; GB Exec: unavailable\n'
                 'Speedup rows: reference Total (overall for GB) / competitor Total; higher is better',
                 fontsize=11, pad=12)
    table = ax.table(cellText=[[''] * len(columns) for _ in metrics], rowLabels=metrics,
                     colLabels=columns, bbox=[0, 0, 1, .96], cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor('#b7c3d0')
        cell.set_linewidth(.5)
        if row == 0:
            cell.set_facecolor('#203c59')
            cell.set_text_props(color='white', weight='bold')
        elif row % 2:
            cell.set_facecolor('#edf2f7')
    fig.canvas.draw()
    for row, values in enumerate(numeric):
        single = metrics[row].endswith('speedup') or metrics[row].startswith('Fastest queries')
        select = max if single else min
        best = [select((pair[mode] for pair in values if pair[mode] is not None), default=None) for mode in (0, 1)]
        for column, pair in enumerate(values):
            cell = table[row + 1, column]
            x, y = cell.get_xy()
            width, height = cell.get_width(), cell.get_height()
            if not single:
                ax.text(x + width / 2, y + height / 2, '/', ha='center', va='center',
                        fontsize=10, transform=ax.transAxes)
            for mode, value in enumerate(pair):
                if single and mode == 1:
                    continue
                winner = value is not None and math.isclose(value, best[mode], rel_tol=1e-12, abs_tol=0)
                color = ('#17622b' if mode == 0 else '#174b9b') if winner else '#222222'
                ax.text(x + width * (.5 if single else .47 if mode == 0 else .53), y + height / 2,
                        formatted(value), ha='center' if single else 'right' if mode == 0 else 'left', va='center',
                        color=color, weight='bold' if winner else 'normal', fontsize=10,
                        transform=ax.transAxes)
    fig.savefig(out / 'summary.png', dpi=180, bbox_inches='tight')
    plt.close(fig)


def table_png(path, title, columns, labels, cells, highlights=()):
    # One image contains the entire workload, without pagination.
    height = max(3, .22 * (len(labels) + 1) + 1.1)
    fig, ax = plt.subplots(figsize=(max(12, 1.25 * len(columns) + 1.5), height))
    ax.axis('off')
    ax.set_title(title + '\n' + WINNER_LEGEND, fontsize=10, pad=12)
    table = ax.table(cellText=cells, rowLabels=labels, colLabels=columns,
                     bbox=[0, 0, 1, .98], cellLoc='right')
    table.auto_set_font_size(False)
    table.set_fontsize(7)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor('#b7c3d0')
        cell.set_linewidth(.35)
        if row == 0:
            cell.set_facecolor('#203c59')
            cell.set_text_props(color='white', weight='bold')
        elif row % 2:
            cell.set_facecolor('#edf2f7')
        if (row - 1, col) in highlights:
            foreground, background = WINNER_COLORS[frozenset(highlights[row - 1, col])]
            cell.set_facecolor(background)
            cell.set_text_props(weight='bold', color=foreground)
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)


def query_scatter(path, title, timings):
    columns = [key for key in timings[0] if key.endswith(' | Mean, ms')]
    common = [row for row in timings if all(row[key] not in (None, '') for key in columns)]
    if not common:
        raise ValueError(f'no common measured queries for {title}')
    rng = random.Random(0)
    jitter = [rng.uniform(-.15, .15) for row in common]
    fig, axes = plt.subplots(1, 2, figsize=(19, 7), sharey=True)
    maximum = max(float(row[key]) / 1000 for row in common for key in columns)
    minimum = min(float(row[key]) / 1000 for row in common for key in columns)
    for ax, mode in zip(axes, ('total', 'ffi_only')):
        selected = [key for key in columns if key.split(' | ')[1] in (mode, 'overall')]
        labels = []
        for index, key in enumerate(selected):
            values = [float(row[key]) / 1000 for row in common]
            name, timing_mode, _ = key.split(' | ')
            labels.append(name + ('\n(overall)' if timing_mode == 'overall' else ''))
            ax.scatter([index + offset for offset in jitter], values, s=18, c='#888888', alpha=.4, edgecolors='none')
            ax.scatter(index, stats.mean(values), s=65, c='red', marker='o', zorder=4, label='Mean' if index == 0 else None)
            ax.scatter(index, stats.median(values), s=65, c='blue', marker='D', zorder=5, label='Median' if index == 0 else None)
        ax.set_xticks(range(len(selected)), labels, rotation=20, ha='right')
        ax.set_title('Total' if mode == 'total' else 'FFI-only (baselines: overall)')
        ax.set_yscale('log')
        ax.set_ylim(minimum / 1.5, maximum * 1.5)
        ax.set_xlim(-.45, len(selected) - .55)
        ax.set_axisbelow(True)
        ax.grid(linestyle='--', alpha=.5)
        ax.legend(loc='upper right')
        ax.set_xlabel('Execution engine / optimizer')
    axes[0].set_ylabel('Per-query mean time (s, log scale)')
    fig.suptitle(f'{title} — {len(common)} common queries; warm-ups excluded')
    fig.tight_layout(rect=(0, 0, 1, .95))
    fig.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def excel(path, rows, notes):
    import xlsxwriter
    with xlsxwriter.Workbook(path) as book:
        sheet = book.add_worksheet('Results')
        fields = list(rows[0])
        number = book.add_format({'num_format': '#,##0.000'})
        winner_formats = {modes: book.add_format({'num_format': '#,##0.000', 'bold': True,
                                                'font_color': colors[0], 'bg_color': colors[1]})
                          for modes, colors in WINNER_COLORS.items()}
        integer = book.add_format({'num_format': '0'})
        winner_integer_formats = {modes: book.add_format({'num_format': '0', 'bold': True,
                                                        'font_color': colors[0], 'bg_color': colors[1]})
                                  for modes, colors in WINNER_COLORS.items()}
        percentage = book.add_format({'num_format': '0.00"%"'})
        wrap = book.add_format({'text_wrap': True, 'valign': 'top'})
        green = book.add_format({'bg_color': '#e5f3e3'})
        amber = book.add_format({'bg_color': '#fff1b8'})
        red = book.add_format({'bg_color': '#f8c6c6'})
        columns = [{'header': field.replace(' | ', '\n'),
                    'format': percentage if field.endswith('RSD, %') else number}
                   for field in fields]
        data = [[row[field] for field in fields] for row in rows]
        sheet.add_table(0, 0, len(rows), len(fields) - 1,
                        {'columns': columns, 'data': data, 'style': 'Table Style Medium 2'})
        for row_index, row in enumerate(rows):
            if row.get('Metric', '').startswith('Fastest queries'):
                for column, field in enumerate(fields[1:], 1):
                    if row[field] is not None:
                        sheet.write_number(row_index + 1, column, row[field], integer)
        for (row, column), modes in best_cells(fields, rows).items():
            formats = winner_integer_formats if rows[row].get('Metric', '').startswith('Fastest queries') else winner_formats
            sheet.write_number(row + 1, column, rows[row][fields[column]], formats[frozenset(modes)])
        sheet.set_row(0, 54)
        sheet.freeze_panes(1, 1)
        sheet.set_column(0, 0, 22)
        sheet.set_column(1, len(fields) - 1, 22)
        for index, field in enumerate(fields):
            if field == 'query_text':
                sheet.set_column(index, index, 65, wrap)
            if field.endswith('RSD, %'):
                cell = f'{xlsxwriter.utility.xl_col_to_name(index)}2'
                for condition, color in [(f'{cell}>10', red), (f'{cell}>=5,{cell}<=10', amber), (f'{cell}<5', green)]:
                    sheet.conditional_format(1, index, len(rows), index,
                                             {'type': 'formula', 'criteria': f'=AND(ISNUMBER({cell}),{condition})', 'format': color})
        sheet.autofit()
        for index, field in enumerate(fields):
            if field == 'query_text':
                sheet.set_column(index, index, 65, wrap)
            elif field.endswith('Error'):
                sheet.set_column(index, index, 48, wrap)
        sheet.set_landscape()
        sheet.fit_to_pages(1, 0)
        sheet.repeat_rows(0)
        metadata = book.add_worksheet('Methodology')
        metadata.set_column(0, 0, 110, wrap)
        for index, note in enumerate([WINNER_LEGEND, *notes]):
            metadata.write(index, 0, note, wrap)
            metadata.set_row(index, 45)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=ROOT / 'Results/wikidata')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--reference', default='rpqmatrix-gb', help='Baseline for per-query reference Total / competitor Total speedups (default: RPQ-matrix_GB overall time).')
    parser.add_argument('--exclude-competitors', default='join', help='Comma-separated competitors omitted from reports; an empty string includes all.')
    parser.add_argument('--exclude-single-closure', action='store_true', help='Exclude queries consisting only of one label followed by * or +.')
    parser.add_argument('--exclude-simple-paths', action='store_true', help='Wikidata-harder: also exclude A/B, A|B and their whole-path * or + closures; implies --exclude-single-closure.')
    parser.add_argument('--compact-summary', action='store_true', help='Write only summary PNG/CSV for pang-hybrid and GB, with Total / Exec pairs.')
    parser.add_argument('--aggregate-only', action='store_true', help='Combine all semantics and write only all/summary.png and all/summary.csv; requires --compact-summary.')
    args = parser.parse_args()
    if args.aggregate_only and not args.compact_summary:
        parser.error('--aggregate-only requires --compact-summary')
    profile = 'wikidata-harder' if args.exclude_simple_paths else 'wikidata-hard' if args.exclude_single_closure else 'wikidata'
    if args.output is None:
        args.output = ROOT / 'Scripts/benchmarks/benchmark_results' / profile
    # Check the optional presentation dependency before producing any reports.
    if not args.compact_summary:
        import xlsxwriter
    rows, inventory = load_results(args.results)
    excluded_competitors = {name.strip() for name in args.exclude_competitors.split(',') if name.strip()}
    if not args.compact_summary and args.reference in excluded_competitors:
        raise ValueError(f'reference {args.reference!r} is excluded')
    rows = [row for row in rows if row['competitor'] not in excluded_competitors]
    inventory = [item for item in inventory if item['competitor'] not in excluded_competitors]
    if args.compact_summary:
        rows = [row for row in rows if row['competitor'] in COMPACT_ORDER]
    if not rows:
        raise ValueError('no results remain after excluding competitors')
    combined_lookup, combined_ids, combined_variants = {}, [], None
    for semantic in sorted({row['semantic'] for row in rows}):
        subset = [row for row in rows if row['semantic'] == semantic]
        texts = {}
        for row in subset:
            if row['query_text']:
                old = texts.setdefault(row['query_id'], row['query_text'])
                if old != row['query_text']:
                    raise ValueError(f'query text disagreement: {semantic}/{row["query_id"]}')
        excluded = set()
        original_count = len({row['query_id'] for row in subset})
        if args.exclude_single_closure or args.exclude_simple_paths:
            if any(row['query_id'] not in texts for row in subset):
                raise ValueError(f'query texts are required for filtering: {semantic}')
            excluded = {query_id for query_id, text in texts.items()
                        if single_label_closure(text) or (args.exclude_simple_paths and simple_binary_path(text))}
            subset = [row for row in subset if row['query_id'] not in excluded]
        if not subset:
            raise ValueError(f'no queries remain after filtering: {semantic}')
        order = COMPACT_ORDER if args.compact_summary else ORDER
        competitors = sorted({row['competitor'] for row in subset},
                             key=lambda name: (order.index(name) if name in order else len(order), name))
        variants = [(name, mode) for name in competitors
                    for mode in ('total', 'ffi_only', 'overall')
                    if any(row['competitor'] == name and row['mode'] == mode for row in subset)]
        names = [f'{name} | {mode}' for name, mode in variants]
        lookup = {(row['competitor'], row['mode'], row['query_id']): row for row in subset}
        ids = sorted({row['query_id'] for row in subset}, key=int)
        valid = {(name, mode): {row['query_id'] for row in subset
                               if row['competitor'] == name and row['mode'] == mode and row['status'] == 'ok'}
                 for name, mode in variants}
        common = set.intersection(*valid.values())
        if (not args.compact_summary and args.reference not in competitors) or not common:
            raise ValueError(f'no common queries or reference for {semantic}')
        if args.compact_summary:
            if args.aggregate_only:
                if combined_variants is not None and variants != combined_variants:
                    raise ValueError('aggregate summary requires the same competitor timing modes in every semantic')
                combined_variants = variants
                combined_ids.extend((semantic, query_id) for query_id in sorted(common, key=int))
                combined_lookup.update({(name, mode, (semantic, query_id)): result
                                        for (name, mode, query_id), result in lookup.items() if query_id in common})
                continue
            title = f'{profile.capitalize()} / {SEMANTICS.get(semantic, semantic)}'
            compact_summary(args.output / semantic, title, variants, lookup, sorted(common, key=int), args.reference)
            print(f'{semantic}: {len(common)} common queries; summary.png and summary.csv rebuilt', flush=True)
            continue
        timings, deviations = [], []
        for query_id in ids:
            time_row = {'query_id': query_id, 'query_text': texts.get(query_id, '')}
            deviation_row = dict(time_row)
            for name, mode in variants:
                label = f'{name} | {mode}'
                row = lookup.get((name, mode, query_id))
                ok = row is not None and row['status'] == 'ok'
                time_row[label + ' | Mean, ms'] = row['mean_ms'] if ok else None
                deviation_row[label + ' | Mean, ms'] = row['mean_ms'] if ok else None
                deviation_row[label + ' | SD, ms'] = row['stddev_ms'] if ok else None
                deviation_row[label + ' | RSD, %'] = row['rsd_percent'] if ok else None
                deviation_row[label + ' | Runs'] = row['observed_runs'] if row else 0
                deviation_row[label + ' | Status'] = row['status'] if row else 'missing'
                deviation_row[label + ' | Error'] = row['error'] if row else 'no result'
            timings.append(time_row)
            deviations.append(deviation_row)
        metrics = ['Total, ms', 'Mean, ms', 'Median, ms', 'Mean speedup', 'Median speedup']
        summary = [{'Metric': metric} for metric in metrics]
        common_ids = sorted(common, key=int)
        reference_mode = 'overall' if (args.reference, 'overall') in valid else 'total'
        for name, mode in variants:
            values = [lookup[name, mode, query_id]['mean_ms'] for query_id in common_ids]
            ratios = [lookup[args.reference, reference_mode, query_id]['mean_ms'] / value
                      for query_id, value in zip(common_ids, values)] if mode != 'ffi_only' else []
            aggregates = [sum(values), stats.mean(values), stats.median(values),
                          stats.mean(ratios) if ratios else None, stats.median(ratios) if ratios else None]
            for row, value in zip(summary, aggregates):
                row[f'{name} | {mode}'] = value
        all_wins = count_wins([(name, mode) for name, mode in variants if mode in ('total', 'overall')],
                              lookup, common_ids)
        summary.append({'Metric': f'Fastest queries / {len(common)} (total)',
                        **{f'{name} | {mode}': all_wins.get((name, mode)) for name, mode in variants}})
        metrics = [row['Metric'] for row in summary]
        experiment = [item for item in inventory if item['semantic'] == semantic]
        notes = [
            f'{SEMANTICS.get(semantic, semantic)}: {len(ids)} catalog IDs; {len(common)} common valid queries in the summary; {len(ids) - len(common)} excluded.',
            'Competitors omitted from reports: ' + (', '.join(sorted(excluded_competitors)) or 'none') + '. Raw results are unchanged.',
            'Query time is the arithmetic mean of measured runs. Warm-ups are excluded using each file’s metadata; Pathrex raw arrays already exclude them.',
            'Blank timing cells denote failed, missing, incomplete or zero-time executions. Status and error details are included in queries_deviation.',
            'SD is sample standard deviation (ddof=1); RSD = 100 × SD / mean. RSD from two measurements has limited precision. No outliers are removed.',
            'RSD cell colors: green below 5%, amber from 5% to 10%, red above 10%.',
            f'Speedup is {args.reference} total (overall for GB) / competitor total (or baseline overall) for each query. Higher is better: above 1 is faster, below 1 is slower. Mean and median aggregate per-query speedups, not total times; the mean is recomputed from individual ratios, not obtained by inverting a mean of normalized times. No ffi_only speedups are reported.',
            'The summary uses the same intersection of valid IDs for every column, including both Pathrex modes. RPQ-matrix_GB overall time is treated as total; GB has no exec measurement.',
            'Pathrex total and ffi_only are separate execution sequences, not paired overhead measurements. Baseline overall is not ffi_only.',
            'Fastest-query counts compare per-query Pathrex total and baseline overall means on the same common IDs as the timing summary. All selected competitors participate in one comparison; no ffi_only win counts are reported.',
            'Equal minima (relative tolerance 1e-12) credit every tied competitor. Counts are descriptive rankings, not tests of statistical significance; small differences within measurement noise still count as wins.',
            'Repetitions (measured/warm-up): ' + '; '.join(f'{item["competitor"]}={item["runs"]}/{item["warmup_runs"]}' for item in experiment),
            'Common IDs: ' + ', '.join(common_ids),
        ]
        if args.exclude_single_closure or args.exclude_simple_paths:
            forms = 'A*, A+, A/B, A|B, (A/B)*, (A/B)+, (A|B)*, (A|B)+' if args.exclude_simple_paths else 'A*, A+'
            notes.extend([f'{profile.capitalize()}: excluded {len(excluded)} of {original_count} catalog queries whose entire path matches {forms}, with A and B single labels. This is a structural filter, not a runtime threshold or proof that a query cannot be optimized.',
                          'Excluded IDs: ' + ', '.join(sorted(excluded, key=int))])
        out = args.output / semantic
        out.mkdir(parents=True, exist_ok=True)
        write_csv(out / 'queries.csv', timings)
        write_csv(out / 'queries_deviation.csv', deviations)
        write_csv(out / 'summary.csv', summary)
        excel(out / 'queries.xlsx', timings, notes)
        excel(out / 'queries_deviation.xlsx', deviations, notes)
        excel(out / 'summary.xlsx', summary, notes)
        cells = [['—' if row[name + ' | Mean, ms'] is None else f'{row[name + " | Mean, ms"]:,.3f}'
                  for name in names] for row in timings]
        title = (profile.capitalize() + ' / ' if profile != 'wikidata' else '') + SEMANTICS.get(semantic, semantic)
        table_png(out / 'queries.png',
                  f'{title} — per-query mean time (ms); — = unavailable',
                  [name.replace(' | ', '\n') for name in names], ids, cells,
                  best_cells([name + ' | Mean, ms' for name in names], timings))
        cells = [['—' if row[name] is None else str(row[name]) if isinstance(row[name], int) else f'{row[name]:,.3f}'
                  for name in names] for row in summary]
        table_png(out / 'summary.png',
                  f'{title} — {len(common)} common queries; reference: {args.reference}\nSpeedup rows: reference Total (overall for GB) / competitor Total; higher is better',
                  [name.replace(' | ', '\n') for name in names], metrics, cells,
                  best_cells(names, summary))
        query_scatter(out / 'query_times.png', title, timings)
        print(f'{semantic}: {len(excluded)} queries excluded by structural filter; {len(ids)} query rows, {len(common)} common queries, 9 files in {out}', flush=True)
    if args.aggregate_only:
        compact_summary(args.output / 'all', f'{profile.capitalize()} / All semantics',
                        combined_variants, combined_lookup, combined_ids, args.reference)
        print(f'All semantics: {len(combined_ids)} common queries; summary.png and summary.csv written to {args.output / "all"}', flush=True)


if __name__ == '__main__':
    main()
