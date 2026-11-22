from collections import defaultdict
from pathlib import Path
import shutil

from .config import ROOT
from .runtime import require


def run_matrix(s, gb):
    dataset = s.data / ("matrix-gb/graph.dat" if gb else "matrix/graph.dat")
    index = Path(str(dataset) + ".baseline-64")
    labels = s.manifest["labels"]
    edges = s.manifest["edges"]
    if not gb and not index.exists():
        pairs = s.folder / "pairs"
        pairs.mkdir()
        s.run([ROOT / "Databases/rpq-matrix/build/create_pairs", dataset, len(labels), edges], cwd=pairs)
        # baseline_build passes its output argument to mkdir via a shell.
        s.run([ROOT / "Databases/rpq-matrix/build/baseline_build", "./", "index", s.manifest["vertices"]],
              cwd=pairs)
        built_index = pairs / "index"
        require(all((built_index / f"{int(pid):04d}.mat").is_file() for pid in labels),
                "rpq-matrix index build did not produce every label matrix")
        if not index.exists():
            shutil.move(built_index, index)
    binary = ROOT / ("Databases/rpq-matrix_GB/build/baselineGB_query" if gb
                     else "Databases/rpq-matrix/build/baseline_query")
    output = s.run([binary, dataset, s.query_dir / "matrix.tsv", len(labels), edges,
                    s.args.runs, s.args.warmups])
    samples = defaultdict(list)
    queries = {q["id"]: q for q in s.queries}
    for line in output.splitlines():
        parts = line.split(";")
        if len(parts) != 3 or parts[0] not in queries:
            continue
        qid, count, ns = parts
        require(int(count) == queries[qid]["count"], f"Wrong result count: {line}")
        nanoseconds = int(ns)
        require(nanoseconds > 0, f"Missing matrix timing or native query error: {line}")
        samples[qid].append(nanoseconds / 1e6)
    for q in s.queries:
        times = samples[q["id"]]
        require(len(times) == s.args.warmups + s.args.runs, f"Incomplete samples for {q['id']}")
        s.add(q, times[s.args.warmups:], "native_matrix_solver")
