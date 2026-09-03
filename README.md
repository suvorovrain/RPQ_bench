# RPQ benchmark harness

The benchmark workflow is configuration-driven and works the same way from any
clone of this repository. Dataset paths, graph sizes, commands, competitors,
result readers, metrics, and chart series are declared in
`Scripts/benchmark_config.json`.

Run every configured competitor and query set:

```bash
Scripts/runners/run_all.sh --dataset rpqbench --semantic all --query-set all
python3 Scripts/benchmarks/build_speed_tables.py --dataset rpqbench --semantic all --query-set all
```

The runner applies the configured warm-up and measured counts uniformly to
Pathrex and the Matrix competitors. Generated results and charts are not
stored in Git.

The small local dataset is selected with `--dataset rpqbench_250k`. The full
setup, configuration reference, partial result behavior, and extension
examples are documented in
[`Scripts/runners/README.md`](Scripts/runners/README.md).
