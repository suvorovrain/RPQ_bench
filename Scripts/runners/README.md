# Configurable benchmark workflow

All benchmark execution and reporting is controlled by:

```text
Scripts/benchmark_config.json
```

Paths are resolved from the repository root, so the same commands work in a
local clone and in `~/Projects/RPQ_bench` on the benchmark server. There are
no machine-specific absolute paths in the config.

## Quick start

List configured datasets and competitors:

```bash
Scripts/runners/run_all.sh --list
```

Preview one query set without executing binaries:

```bash
Scripts/runners/run_all.sh \
  --dataset rpqbench \
  --semantic any-any \
  --query-set 1 \
  --dry-run
```

Run everything configured for a dataset and build all reports:

```bash
Scripts/runners/run_all.sh \
  --dataset rpqbench \
  --semantic all \
  --query-set all \
  --keep-going

python3 Scripts/benchmarks/build_speed_tables.py \
  --dataset rpqbench \
  --semantic all \
  --query-set all
```

`--keep-going` continues after a failed query set or missing competitor and
returns a non-zero status at the end if anything failed. Without it, execution
stops on the first failure.

The old positional syntax is still accepted and uses the default dataset:

```bash
Scripts/runners/run_all.sh any-any 1
python3 Scripts/benchmarks/build_speed_tables.py any-any 1
```

## Selecting work

The universal runner is:

```bash
python3 Scripts/runners/run_benchmarks.py [options]
```

Important selectors:

```text
--dataset NAME
--competitor NAME             repeatable; also accepts comma-separated names or all
--semantic NAME               all, a configured name, or a configured alias
--query-set NAME              all or one query-set name
--runs N
--warmup-runs N
--dry-run
--keep-going
```

The familiar wrappers select one configured competitor and pass every argument
to the universal runner:

```text
run_pathrex_old.sh       pathrex-old
run_pathrex.sh           pathrex-opt
run_rpqmatrix.sh         rpqmatrix
run_rpqmatrix_gb.sh      rpqmatrix-gb
run_all.sh               all dataset competitors
```

Examples:

```bash
Scripts/runners/run_pathrex.sh --dataset rpqbench --semantic con-any --query-set 11

python3 Scripts/runners/run_benchmarks.py \
  --dataset rpqbench_250k \
  --competitor rpqmatrix,rpqmatrix-gb \
  --semantic all
```

## Configuration model

The top-level config contains:

```text
defaults       default dataset and run counts
semantics      semantic names and CLI aliases
variables      shared paths/settings inherited by every dataset
datasets       dataset metadata, enabled competitors, and path variables
competitors    generic command templates and result-reader definitions
```

Every path and command argument is a template. Built-in variables are:

```text
{root}               detected repository root
{dataset}            selected dataset name
{semantic}           selected semantic
{query_set}          selected query-set name
{runs}               measured run count
{warmup_runs}        warm-up count
{total_runs}         warm-up plus measured run count
{n_predicates}       dataset predicate count
{n_triples}          dataset triple count
{binary}             resolved competitor binary
{query_set_path}     configured query file/directory
{query_path}         current query file
{query_name}         current query filename
{query_stem}         current query filename without suffix
{query_index}        one-based current query index
{output_path}        resolved output file
```

Shared and dataset `variables` may reference built-ins and each other. Dataset
values override shared values with the same name. For example:

```json
{
  "results_root": "{root}/Results/{dataset}",
  "solver_result_dir": "{results_root}/solver/{semantic}/{query_set}"
}
```

The dataset's `query_catalog` is the canonical query list used to discover
query sets and label report rows. It must contain exactly one
`{query_set}` placeholder.

## Adding a dataset

Add one object under `datasets`. No runner or analysis code needs to change.
The object supplies graph statistics, the competitor list, and values for all
path variables used by those competitors:

```json
{
  "my_dataset": {
    "description": "My new graph",
    "n_predicates": 42,
    "n_triples": 1234567,
    "competitors": ["pathrex-opt", "rpqmatrix"],
    "variables": {
      "query_catalog": "{root}/Queries/rpqmatrix/my_dataset/{semantic}/{query_set}.tsv",
      "pathrex_query": "{root}/Queries/pathrex/my_dataset/{semantic}/{query_set}.txt",
      "rpqmatrix_query_dir": "{root}/Queries/rpqmatrix/my_dataset/{semantic}/{query_set}.tsv_split",
      "pathrex_graph": "{root}/Datasets/my_dataset/pathrex",
      "rpqmatrix_dataset": "{root}/Datasets/my_dataset/rpq-matrix/graph.dat",
      "results_root": "{root}/Results/my_dataset",
      "pathrex_opt_result": "{results_root}/pathrex-test/{semantic}/{query_set}/res.json",
      "pathrex_opt_checkpoint": "{results_root}/pathrex-test/{semantic}/{query_set}/checkpoint.json",
      "rpqmatrix_result_dir": "{results_root}/rpq-matrix/{semantic}/{query_set}",
      "analysis_output": "{root}/Scripts/benchmarks/benchmark_results/my_dataset"
    }
  }
}
```

Only variables referenced by the selected competitors are required. Validate
the new section before a long run:

```bash
Scripts/runners/run_all.sh --dataset my_dataset --dry-run
```

## Adding a competitor

Add one object under `competitors`, then include its name in the desired
dataset's `competitors` array. The runner does not contain competitor-specific
code: `run.command` is an argument array, so paths and arguments with spaces
are handled without shell parsing.

A per-query-file command sets `query_files_glob`; omit it when a single
command consumes the whole query-set file. `stdout_include_regex` optionally
stores only matching stdout lines. Filtered output is written through a
temporary file and atomically replaces the previous result only after a
successful command.

Set `query_file_repetitions` when a competitor expects one query per run in
its input file. The runner reads the single distinct query from each configured
file and creates a temporary input with the requested number of repetitions.
For example, `"query_file_repetitions": "{total_runs}"` gives every competitor
the same warm-up and measured sample counts without regenerating split files.

Example:

```json
{
  "my-solver": {
    "label": "my_solver",
    "run": {
      "binary": "{my_solver_binary}",
      "query_path": "{my_solver_query_dir}",
      "query_files_glob": "*.txt",
      "query_file_repetitions": "{total_runs}",
      "output_path": "{my_solver_result_dir}/{query_name}",
      "required_paths": ["{my_solver_dataset}"],
      "build_hint": "Build my-solver first",
      "command": ["{binary}", "{my_solver_dataset}", "{query_path}"],
      "stdout_include_regex": "^[0-9]+;"
    },
    "analysis": {
      "reader": "semicolon_files",
      "path": "{my_solver_result_dir}/{query_index}.txt",
      "delimiter": ";",
      "value_column": 2,
      "warmup_runs": "{warmup_runs}",
      "runs": "{runs}",
      "table_metric": "total",
      "metrics": {
        "total": {
          "label": "my_solver",
          "color": "#4c956c",
          "histogram": true
        }
      }
    }
  }
}
```

Supported result readers:

- `semicolon_files`: one delimited result file per query; configurable value
  column, delimiter, warm-up count, measured count, and nanosecond scale. The
  reader skips exactly `warmup_runs`, averages exactly `runs`, and treats a
  shorter result as incomplete.
- `json_timing`: Pathrex-style JSON; configurable algorithm, timing field,
  metric labels, colors, and zero/one-based query index.

Adding another metric under `analysis.metrics` adds a histogram series.
`table_metric` chooses the metric shown in the comparison table.

## Reports and partial results

The report command uses the same config and competitor selection:

```bash
python3 Scripts/benchmarks/build_speed_tables.py \
  --dataset rpqbench \
  --competitor pathrex-old,rpqmatrix,pathrex-opt \
  --semantic any-con \
  --query-set 10
```

Missing competitor directories, missing individual query files, empty outputs,
and incomplete JSON files do not abort report generation. Missing table cells
are labeled `missing`; histogram series are built only from available positive
measurements. Each report prints coverage such as:

```text
any-con/10: pathrex-old=20/20, pathrex-opt=0/20, rpqmatrix=20/20
```

Use `--hide-empty-competitors` to remove completely empty table columns. By
default they remain visible, which makes incomplete coverage explicit.

Reports are written below the dataset's `analysis_output`, normally:

```text
Scripts/benchmarks/benchmark_results/<dataset>/<semantic>/<query-set>_table.png
Scripts/benchmarks/benchmark_results/<dataset>/<semantic>/<query-set>_hist.png
```

## Overrides

For one-off machine-specific changes, avoid editing the shared config:

```bash
Scripts/runners/run_pathrex_old.sh \
  --dataset rpqbench \
  --set old_pathrex_root=/work/pathrex \
  --semantic any-any \
  --query-set 1
```

Every dataset variable can also be overridden by an environment variable named
`RPQBENCH_<VARIABLE_NAME_IN_UPPERCASE>`. Common overrides are:

```text
RPQBENCH_CONFIG
RPQBENCH_DATASET
RPQBENCH_RUNS
RPQBENCH_WARMUP_RUNS
RPQBENCH_N_PREDICATES
RPQBENCH_N_TRIPLES
RPQBENCH_DRY_RUN=1
RPQBENCH_OLD_PATHREX_ROOT
```

`--set NAME=VALUE` has precedence over dataset variables and environment
variable overrides. A different repository root can be supplied with
`--root PATH`, and a separate config can be supplied with `--config PATH`.
