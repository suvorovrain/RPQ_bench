# RPQ_bench

RPQ_bench is an experimental framework for evaluating regular path queries (RPQs)
using three execution engines: **Pathrex**, **rpq-matrix**, and **rpq-matrix_gb**.
It provides a common launch interface, dataset and query conversion utilities,
and performance report generation.

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
[Scripts/run_config.json](Scripts/run_config.json), then validate and launch:

```bash
python3 Scripts/runners/run_benchmarks.py --dry-run
python3 Scripts/runners/run_benchmarks.py --keep-going
```

Each process loads its graph once and evaluates all queries in its input file.
Warm-up and measurement repetitions are performed by the execution engines;
query lines are not duplicated.

## Reproduction Procedure

### 1. Source Code and Dependencies

The workflow requires Linux, Git, a current Rust/Cargo toolchain, Python 3.10 or
later, CMake, GCC/G++, and OpenMP. Report generation additionally requires
Matplotlib. N-Triples preprocessing uses the Python dependencies of la-rpq.

```bash
git submodule update --init --recursive
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r vendor/larpq/Scripts/requirements.txt
python3 -m pip install matplotlib
```

For reproducibility, record the repository commit (`git rev-parse HEAD`), submodule
revisions (`git submodule status --recursive`), compiler versions, thread counts,
graph dimensions, query files, and configuration. Avoid
`git submodule update --remote`, which replaces pinned dependency revisions.

### 2. Building the Execution Engines

Pathrex builds its native dependency automatically. Generated Rust bindings are
included in the source tree; ordinary builds do not require the
`regenerate-bindings` feature.

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

Pathrex accepts one query per line in the format `ID,<source> <path> <target>`.
Query IDs must be numeric, unique, and preserved from the original workload.
Queries must use the same URI prefix transformation as the processed graph.

```bash
python3 vendor/larpq/Scripts/deprefix-sparql original-queries.txt > Queries/queries.txt
python3 Scripts/converters/convert_query_mm_to_rpqmatrix.py --preserve-ids \
  Queries/queries.txt -o Queries/rpqmatrix
```

The converter accepts multiple input files and preserves IDs with `--preserve-ids`.
It produces `queries.tsv` in the output directory, using the format `ID <query>#`
with one space after the ID. The `.tsv` extension is historical; the delimiter
is not a tab. Variables are normalized to `?x` and `?y`.
Both RPQ-matrix engines use the same converted query files.

### 6. Experiment Configuration

Configure the experiment in [Scripts/run_config.json](Scripts/run_config.json):

| Field | Description |
| --- | --- |
| `runs`, `warmup_runs` | Measured and warm-up repetitions, shared by all engines. |
| `n_predicates`, `n_triples` | Counts for the processed graph, passed to both baselines. |
| `<engine>.source`, `<engine>.binary` | Source directory and executable path within it. |
| `<engine>.output` | Root output directory for that engine. |
| `pathrex.graph`, `pathrex.base_iri` | MatrixMarket graph directory and base IRI. |
| `pathrex.optimizers` | Optimizer names accepted by the Pathrex CLI. |
| `rpq-matrix.dataset`, `rpq-matrix_gb.dataset` | Base `*.dat` paths for the two graph representations. |
| `queries.<name>.pathrex`, `queries.<name>.rpqmatrix` | Original query file and converted file shared by both baselines. |

Each entry in `queries` defines a workload. Its name is used in result paths;
the runner does not infer query semantics from the name.
Relative paths are resolved against the repository root, except `binary`, which
is resolved against `source`. Absolute paths are also supported.

The supplied configuration is an example for the prepared ADBIS2026 deployment
at `/home/lamba/ADBIS2026/RPQ_bench`:

| Input | Path relative to the repository root |
| --- | --- |
| Pathrex graph | `../wikidata/Wikidata/wikidata-mm` |
| rpq-matrix dataset | `../wikidata/Wikidata/wikidata-orig/wikidata.dat` |
| rpq-matrix_gb dataset | `../wikidata/Wikidata/wikidata-mm-txt/wikidata.dat` |
| Original queries | `../wikidata-<query-set>.txt` |
| Converted queries | `Queries/rpqmatrix/wikidata/wikidata-<query-set>.tsv` |

This processed graph contains 609358925 triples and 1393 predicates. The configured
protocol uses five measured repetitions and one warm-up repetition, with results
in `Results/wikidata`. For a different deployment, replace these paths and counts
with those obtained during dataset preparation.

### 7. Benchmark Execution

Run all engines, Pathrex optimizers, and workloads selected in the configuration:

```bash
python3 Scripts/runners/run_benchmarks.py --config Scripts/run_config.json --dry-run
python3 Scripts/runners/run_benchmarks.py --config Scripts/run_config.json --keep-going
```

`--config` selects the configuration file; `--root` overrides the root used for
relative paths. Optional `--engine`, `--optimizer`, and `--query-set` filters
accept `all` or comma-separated names from the configuration. The optimizer filter
applies only to Pathrex. `--runs` and `--warmup-runs` override repetition counts.
The full interface is available through `--help`.

Execution is sequential, ordered by engine, optimizer, and workload. Workloads
follow their order in `queries`. Before execution, the runner checks binaries,
selected input files, query IDs and ordering, and available Pathrex optimizers.
`--dry-run` validates file inputs and prints commands without executing binaries.
These checks do not validate all graph matrices or establish memory requirements.

The `--keep-going` option proceeds to the next process after a failure. It does
not prevent out-of-memory termination or resume queries within a failed process.
The runner returns exit status 1 if any benchmark process fails. Baseline output
is collected in a temporary file and published as `res.txt` only after successful
process completion. Its `res.txt.meta.json` records query IDs and repetition parameters.

### 8. Results and Measurement Protocol

Outputs retain the directory structure expected by the report generator:

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

Pathrex sampling parameters are inherited from the environment:
`RPQ_SAMPLE_PERCENT=1`, `RPQ_SAMPLE_SEED=0`, and `RPQ_SAMPLE_MAX_STAR_ITERS=64`
are the defaults. The iteration limit does not bound memory consumption.

Answer counts have different semantics: Pathrex `result_count` reports distinct
reachable target vertices, whereas the baselines report pairs in the path relation.
For any-any and any-con queries, these counts cannot be directly compared as
a correctness criterion.

Pathrex writes its result JSON at the end of the query batch. A failed process,
including out-of-memory termination, may therefore lose the current batch's
measurements.

### 9. Performance Reports

Select a report configuration matching the result and query paths. For the
ADBIS2026 Wikidata results:

```bash
python3 Scripts/benchmarks/build_speed_tables.py \
  --config Scripts/benchmark_config.adbis2026.json \
  --dataset wikidata --semantic wikidata --query-set all \
  --competitor all --runs 5 --warmup-runs 1
```

`run_config.json` is a launch configuration, not a report configuration. If input
or output paths change, the corresponding report paths must be updated as well.

Reports group Pathrex `total` and `ffi_only` measurements and baseline rows by query
ID. For baseline results, supply the actual `--runs` and `--warmup-runs` used during
execution. `--competitor` selects series, `--output-dir` selects the report
directory, `--set results_root=/path` overrides the result input directory, and
`--hide-empty-competitors` omits entirely empty series. The complete option reference
is available through `python3 Scripts/benchmarks/build_speed_tables.py --help`.

## Script and Configuration Reference

| File | Purpose |
| --- | --- |
| `Scripts/runners/run_benchmarks.py` | Benchmark runner; Python standard library only. |
| `Scripts/run_config.json` | Launch configuration. |
| `Scripts/converters/convert_query_mm_to_rpqmatrix.py` | Query conversion with ID preservation through `--preserve-ids`. |
| `Scripts/converters/mm_to_rpq_GB.py` | Conversion of a MatrixMarket graph to the GB baseline layout. |
| `Scripts/benchmarks/build_speed_tables.py` | Performance tables and histograms; requires Matplotlib. |
| `Scripts/benchmark_config.py` | Configuration library for reporting, not benchmark execution. |
| `Scripts/benchmark_config.json` | RPQBench report configuration and the report generator's default. |
| `Scripts/benchmark_config.adbis2026.json` | Report configuration for existing ADBIS2026 Wikidata measurements. |

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
