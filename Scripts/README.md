# Scripts

Benchmark execution and report generation are driven by
`benchmark_config.json`. The complete CLI and configuration reference is in
[`runners/README.md`](runners/README.md).

Common commands:

```bash
Scripts/runners/run_all.sh --dataset rpqbench --semantic all --query-set all
python3 Scripts/benchmarks/build_speed_tables.py --dataset rpqbench --semantic all --query-set all
```

Directories:

- `runners/`: universal benchmark runner plus compatibility shell wrappers.
- `benchmarks/`: partial-result-safe tables and histograms.
- `converters/`: dataset and query conversion helpers; each executable script
  exposes its current arguments through `--help`.

The benchmark runner and report builder use only Python's standard library
apart from Matplotlib, which is required only for rendering PNG reports.
