# RPQ benchmark harness

The benchmark workflow is configuration-driven and works the same way from any
clone of this repository. Dataset paths, graph sizes, commands, competitors,
result readers, metrics, and chart series are declared in
`Scripts/benchmark_config.json`.

Additional competitor sources are registered as Git submodules in `Databases/`.
See the [competitor overview and launch guide](Databases/README.md) for source revisions,
integration status, RPQ support, limitations, and systems distributed without
public engine sources. Source availability does not imply benchmark integration;
the common runner currently supports Pathrex and the two Matrix engines.

For all 15 competitors, see the [launch/data/query guides](Databases/guides/README.md)
and [actual rpqbench_250k smoke results](Databases/guides/smoke-results.md).
The separate smoke runner validates inputs and endpoints; it does not yet extend
the common performance runner.
The overview includes all 15 selected systems, N3/NT conversion, four shared
simple queries and commands to run each competitor with `--basic`.
A [100-run benchmark and plotting guide](Databases/guides/benchmark.md) covers
all 15 competitors with Pathrex pang-hybrid, raw samples and colored HTML/Excel tables.

## Repository Organization

- `Databases/pathrex`: Rust library and command-line interface, including its own LAGraph and GraphBLAS dependencies.
- `Databases/rpq-matrix`: C++ matrix-based baseline.
- `Databases/rpq-matrix_GB`: C++ GraphBLAS-based baseline.
- `vendor/GraphBLAS` and `vendor/LAGraph`: dependencies for rpq-matrix_GB.
- `vendor/larpq`: the [la-rpq](https://github.com/SparseLinearAlgebra/la-rpq) submodule and upstream dataset preparation utilities.
- `Datasets/` and `Queries/`: local experimental inputs; large datasets are not stored in version control.
- `Results/`: generated experimental results, excluded from version control.
- `Scripts/`: the benchmark runner, converters, and the report generator.

## Quick Start

The following commands assume that all engines have been built and that datasets
and query files have been prepared. All commands are executed from the repository root.
Set the executable, input, and output paths in
[Scripts/benchmark_config.json](Scripts/benchmark_config.json), then launch:

```bash
Scripts/runners/run_all.sh --dataset rpqbench --semantic all --query-set all
python3 Scripts/benchmarks/build_speed_tables.py --dataset rpqbench --semantic all --query-set all
```

The runner applies the configured warm-up and measured counts uniformly to
Pathrex and the Matrix competitors. Generated results and charts are not
stored in Git.

## Reproduction Procedure

### 1. Source Code and Dependencies

The workflow requires Linux, Git, Rust/Cargo 1.90 or later, Python 3.10 or
later, CMake, GCC/G++, and OpenMP. Report generation additionally requires
Matplotlib. N-Triples preprocessing uses the Python dependencies of la-rpq.

```bash
git submodule update --init --recursive
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r vendor/larpq/Scripts/requirements.txt
python3 -m pip install matplotlib xlsxwriter
```

For reproducibility, record the repository commit (`git rev-parse HEAD`), submodule
revisions (`git submodule status --recursive`), compiler versions, thread counts,
graph dimensions, query files, and configuration. Avoid
`git submodule update --remote`, which replaces pinned dependency revisions.

### 2. Building the Execution Engines

Pathrex builds its native dependency automatically. Generated Rust bindings are
included in the source tree; ordinary builds do not require the
`regenerate-bindings` feature.
The [Pathrex local build guide](Databases/pathrex/README.md#local-build-linux)
lists system packages, feature flags, test commands, and dependency-locking
instructions.

```bash
cargo build --release --manifest-path Databases/pathrex/Cargo.toml --features bench
cmake -S Databases/rpq-matrix -B Databases/rpq-matrix/build -DCMAKE_BUILD_TYPE=Release
cmake --build Databases/rpq-matrix/build --target baseline_query create_pairs baseline_build -j 8

cmake -S vendor/GraphBLAS -B vendor/GraphBLAS/build \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON \
  -DGRAPHBLAS_USE_CUDA=OFF -DSUITESPARSE_DEMOS=OFF
cmake --build vendor/GraphBLAS/build -j 8
cmake -S vendor/LAGraph -B vendor/LAGraph/build \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON -DBUILD_TESTING=OFF \
  -DGraphBLAS_DIR="$PWD/vendor/GraphBLAS/build"
cmake --build vendor/LAGraph/build -j 8
cmake -S Databases/rpq-matrix_GB -B Databases/rpq-matrix_GB/build -DCMAKE_BUILD_TYPE=Release
cmake --build Databases/rpq-matrix_GB/build --target baselineGB_query -j 8
```

With CMake 4, configuration of older C++ projects may additionally require
`-DCMAKE_POLICY_VERSION_MINIMUM=3.5`. The resulting executables are
`target/release/pathrex`, `build/baseline_query`, and `build/baselineGB_query`
within their respective source directories.

### 3. Wikidata Source

For the Wikidata workload, use the snapshot associated with the MillenniumDB
Path Query Challenge. The
[la-rpq Wikidata instructions](https://github.com/SparseLinearAlgebra/la-rpq/blob/main/Datasets/Wikidata/README.md)
reference the [N-Triples dataset on Figshare](https://figshare.com/s/50b7544ad6b1f51de060).
The query workload and challenge description are available in
[MillenniumDB/path-query-challenge](https://github.com/MillenniumDB/path-query-challenge).

The commands below assume that the downloaded file is stored at
`Datasets/wikidata/raw/wikidata.nt`. Other snapshots, including the one referenced
by the upstream rpq-matrix README, may have different dimensions. All three
engines must receive representations of the same processed graph.

### 4. Graph Preprocessing and Conversion

Create `Datasets/wikidata` and place the source file in `raw/`. Preprocessing
retains URI-to-URI edges, excludes literals and blank nodes, removes URI prefixes,
and eliminates duplicate triples before constructing engine-specific representations.

```bash
python3 vendor/larpq/Scripts/truncate Datasets/wikidata/raw/wikidata.nt \
  | python3 vendor/larpq/Scripts/deprefix-nt \
  > Datasets/wikidata/processed-with-dups.nt
python3 vendor/larpq/Scripts/remove-dups Datasets/wikidata/processed-with-dups.nt \
  > Datasets/wikidata/processed.nt

python3 vendor/larpq/Scripts/nt-to-mm \
  Datasets/wikidata/processed.nt Datasets/wikidata/pathrex

python3 Scripts/converters/mm_to_rpq_GB.py Datasets/wikidata/pathrex \
  --output-base Datasets/wikidata/rpq-matrix_GB/wikidata.dat

python3 vendor/larpq/Databases/RPQ-matrix/nt-to-rpqm-txts \
  Datasets/wikidata/processed.nt Datasets/wikidata/rpq-matrix wikidata
```

The output directories of upstream converters must not already exist.
`mm_to_rpq_GB.py` creates symbolic links to MatrixMarket matrices by default;
`--copy` creates independent copies. Repeated conversion replaces dictionaries
and matching output links. Use a separate directory to preserve an earlier conversion.

Obtain graph dimensions from the converted dataset: `N` denotes the number of
triples, `P` the number of predicates, and `V` the number of vertices. The
rpq-matrix converter prints these values. Set `n_triples` and `n_predicates`
accordingly.

Construct the binary index for rpq-matrix, replacing `P`, `N`, and `V` with
the actual numeric values:

```bash
mkdir -p Datasets/wikidata/pairs
# create_pairs writes its output to the current working directory.
(cd Datasets/wikidata/pairs && \
  ../../../Databases/rpq-matrix/build/create_pairs ../rpq-matrix/wikidata.dat P N)
# baseline_build creates the output directory.
Databases/rpq-matrix/build/baseline_build \
  Datasets/wikidata/pairs Datasets/wikidata/rpq-matrix/wikidata.dat.baseline-64 V
```

The GB baseline does not require this binary index. Its `.mat` files are
MatrixMarket files arranged by the converter. Binary matrices produced for
rpq-matrix must not be supplied to rpq-matrix_gb.

The upstream Python converters retain substantial dictionaries or sets in memory;
`remove-dups` stores all unique lines. Preprocessing the full Wikidata graph
therefore requires adequate RAM or an already prepared dataset. Dataset conversion
must be performed separately from query timing measurements.

### 5. Query Preparation

For the common runner, convert Pathrex query catalogs to the Matrix query format:

```bash
python3 Scripts/converters/convert_query_mm_to_diego.py \
  Queries/queries.txt -o Queries/rpqmatrix
python3 Scripts/converters/split_and_extend.py \
  Queries/rpqmatrix/queries.tsv 12
```

The converter writes `<subject> <path> <object>#`, without a query ID, and normalizes
variables to `?x` and `?y`. The splitter repeats each query in a separate file;
its repetition count must equal `runs + warmup_runs` in the configuration.
The Matrix engines also support explicit space-delimited IDs and native repetition
arguments; the separate competitor adapters use that batch interface.
For shared inputs for all 15 competitors, follow [the preparation guide](Databases/README.md).

### 6. Experiment Configuration

Execution and configuration-based reporting share
[Scripts/benchmark_config.json](Scripts/benchmark_config.json).
It defines repetitions in `defaults`, graph statistics and paths in `datasets`,
and command templates and result readers in `competitors`.
The [configuration reference](Scripts/runners/README.md) describes all fields,
path variables, and how to add a dataset or competitor.

### 7. Benchmark Execution

```bash
python3 Scripts/runners/run_benchmarks.py \
  --dataset rpqbench_250k --semantic all --query-set all --dry-run
python3 Scripts/runners/run_benchmarks.py \
  --dataset rpqbench_250k --semantic all --query-set all --keep-going
```

Use `--competitor` to select configured engines, `--runs` and `--warmup-runs` to
set repetitions, and `--config` to select another configuration. The common runner
currently selects `pathrex-old`, `pathrex-opt`, `rpqmatrix`, and `rpqmatrix-gb`.
Its Pathrex optimizer choices are part of the configured command templates.
For the separate 15-system workflow, use [the smoke guide](Databases/guides/README.md)
and [benchmark guide](Databases/guides/benchmark.md).

### 8. Results and Measurement Protocol

The archived Wikidata measurements use the following layout, read directly by
`Scripts/benchmarks/analyze_results.py`. Current common-runner output paths are
defined in `Scripts/benchmark_config.json`:

```text
<output>/<query-set>/
  <pathrex-optimizer>/res.json
  <pathrex-optimizer>/res.runs.json
  rpqmatrix/res.txt
  rpqmatrix/res.txt.meta.json
  rpqmatrix-gb/res.txt
  rpqmatrix-gb/res.txt.meta.json
```

Pathrex optimizer names distinguish result subdirectories. Repeated execution
overwrites the same paths; use separate output directories for separate experiments.

Graph loading is excluded from per-query timing. Pathrex `total` includes query
preparation and execution; `ffi_only` measures execution alone. These modes use
separate repetition sequences. Baseline output includes warm-up rows, which are
excluded by the report generator according to the configured warm-up count.
Pathrex therefore performs `2 × (runs + warmup_runs)` preparation/execution cycles
per query, whereas each baseline performs `runs + warmup_runs` executions.

The competitor adapters use `none` and `pang-hybrid`. Additional CLI optimizer
choices depend on the pinned Pathrex revision; check the built executable help.

Answer counts have different semantics: Pathrex `result_count` reports distinct
reachable target vertices, whereas the baselines report pairs in the path relation.
For any-any and any-con queries, these counts cannot be directly compared as
a correctness criterion.

Pathrex writes its result JSON at the end of the query batch. A failed process,
including out-of-memory termination, may therefore lose the current batch's
measurements.

### 9. Performance Reports

Analyze downloaded result directories directly, including experiments with
different repetition counts:

```bash
python3 Scripts/benchmarks/analyze_results.py \
  --results Results/wikidata \
  --output Scripts/benchmarks/benchmark_results/wikidata
```

The analyzer reads repetition counts from each result file's metadata. Pathrex
raw arrays exclude warm-ups; baseline warm-up rows are removed before averaging.
It validates raw Pathrex measurements against the recorded means and standard
deviations. No external query catalog or common repetition count is required.

Each workload produces nine files:

| Files | Contents |
| --- | --- |
| `queries.png`, `queries.csv`, `queries.xlsx` | One table covering all query IDs and available competitors. |
| `queries_deviation.csv`, `queries_deviation.xlsx` | Per-query means, sample standard deviations, RSD, run counts, statuses and errors. |
| `summary.png`, `summary.csv`, `summary.xlsx` | Total, mean and median query times; mean and median per-query speedups; fastest-query counts. |
| `query_times.png` | Per-query timing scatter plots with mean and median markers; total and ffi-only panels. |

Pathrex total and ffi-only measurements appear as separate columns in the same
table; baselines contribute one overall-time column. CSV files contain numeric
values with consistent precision; Excel files provide formatted tables, filters,
frozen headers and RSD highlighting. The Excel `Methodology` sheet records run
counts and the query IDs used in comparative summaries.
PNG and Excel tables highlight the lowest times and highest total-time speedups
in bold. Times are compared separately for total and ffi-only; speedups are reported
only for total. Baseline overall times participate in both timing comparisons.
Tied best values are all highlighted. CSV files retain plain numeric values.
Total winners are green; ffi-only winners are blue. A baseline winning both
comparisons has green text on a blue background. Bold formatting is retained.

Comparative summaries use the intersection of successfully measured IDs across
all columns. Missing or failed measurements remain blank, not zero. The default
reference is `rpqmatrix-gb`, configurable with `--reference`. Rows named
`Mean speedup` and `Median speedup` report the arithmetic mean and median of
reference total time (overall for GB) divided by competitor total time for each
query. Above 1 means faster, below 1 means slower, and GB has a speedup of 1.
These are not ratios of aggregate times or inverses of mean normalized times.
No ffi-only speedups are reported.
The summary also reports fastest-query counts with the common query count as
the denominator. One comparison ranks all selected competitors by Pathrex total
or baseline overall time; no ffi-only win counts are reported. Every tied minimum
is credited, using a relative tolerance of `1e-12`. These counts describe observed
mean-time rankings, not statistically significant differences. The highest counts
are highlighted in the formatted tables.
Reports omit `join` by default; use `--exclude-competitors` to change the
comma-separated exclusion list, or `--exclude-competitors ''` to include all
competitors. Exclusions affect reports only, not the raw measurements.
RSD uses sample standard deviation (`ddof=1`); estimates from two repetitions
should be interpreted cautiously.

In `query_times.png`, each gray point is the mean measured time of one query.
Red circles and blue diamonds denote the arithmetic mean and median across the
common query set. Both panels use seconds and the same logarithmic vertical scale;
all outliers are retained. Baselines show their overall execution time in both panels.

To produce the same reports per workload after excluding single-label
closures (`A*` and `A+`), run:

```bash
python3 Scripts/benchmarks/analyze_results.py --exclude-single-closure
```

The filtered tables are written to `Scripts/benchmarks/benchmark_results/wikidata-hard`.
Parentheses around a single label or its closure do not affect filtering. Composite
expressions such as `A/B*`, `(A|B)*` and `(A/B)+` remain included. The filter applies
to complete path expressions, independent of endpoint semantics and execution time.
Excluded IDs are recorded on the Excel `Methodology` sheet; original results and
unfiltered reports remain unchanged.

For `wikidata-harder`, additionally exclude two-label expressions `A/B`, `A|B`,
`(A/B)*`, `(A/B)+`, `(A|B)*`, and `(A|B)+`:

```bash
python3 Scripts/benchmarks/analyze_results.py --exclude-simple-paths
```

This option includes the single-label closure filter and writes the same nine
reports per workload to `Scripts/benchmarks/benchmark_results/wikidata-harder`.
Here `A` and `B` are individual labels; redundant parentheses are accepted.
Expressions such as `A/B*`, `A/(B|C)`, and `(A|B|C)*` remain included.
This is a structural workload selection, not a claim that the excluded expressions
cannot benefit from optimization. The `wikidata` and `wikidata-hard` reports are
preserved.

To rebuild only compact summary PNG/CSV tables for `pang-hybrid` and
`RPQ-matrix_GB`, run:

```bash
python3 Scripts/benchmarks/analyze_results.py --exclude-simple-paths --compact-summary
```

Each competitor occupies one column with `total / exec` values. `exec` denotes
the existing Pathrex `ffi_only` measurement; GB overall time is displayed as
total, with no exec measurement. The rows report sum, mean, and median query
times in milliseconds, mean and median per-query speedups, and finally total-only
fastest-query counts. Speedup and win-count rows contain one value per competitor, without
a total/exec pair: reference total (overall for GB; default reference:
`rpqmatrix-gb`) / competitor total. Larger speedups are better. Ratios are aggregated
per query, not from aggregate times. Total wins compare the selected competitors;
exec win counts are not reported.
All rows use the intersection of valid query IDs across those measurements.
Only `summary.png` and `summary.csv` are rewritten;
previous Excel, per-query, and scatter-plot reports are left unchanged.

To write one pooled summary for all three semantics without rebuilding the
individual workload reports, use:

```bash
python3 Scripts/benchmarks/analyze_results.py --exclude-simple-paths --compact-summary --aggregate-only
```

Only `wikidata-harder/all/summary.png` and `summary.csv` are generated. Each
`(semantic, query ID)` is a separate observation. Means, medians, speedups, and
win counts are recomputed over the pooled common-query sets, rather than averaging
the three workload summaries. Each query has equal weight; semantics are not
equally weighted.

For configuration-based reports from current runs:

```bash
python3 Scripts/benchmarks/build_speed_tables.py \
  --dataset rpqbench_250k --semantic all --query-set all --competitor all
```

Execution and reporting use the same configuration. `--config` selects another
configuration and `--output-dir` overrides the report directory. See
[the runner and report reference](Scripts/runners/README.md) for current options.
The metadata-aware analyzer above handles the existing Wikidata batch results
without the former ADBIS2026 configuration.

## Script and Configuration Reference

| File | Purpose |
| --- | --- |
| `Scripts/runners/run_benchmarks.py` | Benchmark runner; Python standard library only. |
| `Scripts/runners/README.md` | Runner and shared configuration reference. |
| `Scripts/converters/convert_query_mm_to_diego.py` | Convert queries to the Matrix input format. |
| `Scripts/converters/mm_to_rpq_GB.py` | Conversion of a MatrixMarket graph to the GB baseline layout. |
| `Scripts/benchmarks/build_speed_tables.py` | Performance tables and histograms; requires Matplotlib. |
| `Scripts/benchmarks/analyze_results.py` | Metadata-aware analysis of raw measurements, CSV exports, variability and aggregate comparisons. |
| `Scripts/benchmark_config.py` | Shared configuration library for execution and reporting. |
| `Scripts/benchmark_config.json` | Shared RPQBench execution and reporting configuration. |

`mm_to_rpq_GB.py` reads `vertices.txt`, `edges.txt`, and `N.txt`, and produces
`.SO`, `.P`, and `.baseline-64/0001.mat` and subsequent matrices. Matrix outputs
are absolute symbolic links by default; use `--copy` when the converted dataset
must be portable independently of its MatrixMarket source. `--output-base`
specifies the output base path; `--base-name` specifies a name inside the input
directory when `--output-base` is omitted. Both converters provide `--help`.

The upstream utilities `truncate`, `deprefix-nt`, `deprefix-sparql`, `remove-dups`,
`nt-to-mm`, `nt-to-csv`, and `sparql-to-fa` are documented in
[vendor/larpq/Scripts/README.md](vendor/larpq/Scripts/README.md).
Additional rpq-matrix preparation details are provided in
[vendor/larpq/Databases/RPQ-matrix/README.md](vendor/larpq/Databases/RPQ-matrix/README.md).
