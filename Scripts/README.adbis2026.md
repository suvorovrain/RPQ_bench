# Wikidata benchmark on ADBIS2026

Run commands from `/home/lamba/ADBIS2026/RPQ_bench`. The machine-specific configuration is
`Scripts/benchmark_config.adbis2026.json`; it does not replace the configuration used on the
other benchmark server.

The three query sets are `sparql-queries-any-con`, `sparql-queries_CON_ANY`, and
`only-any-safe`. The original files live in `/home/lamba/ADBIS2026/wikidata-*.txt`.
Pathrex reads those files directly. The two standalone RPQ-matrix engines read one
converted TSV per query set from `Queries/rpqmatrix/wikidata/`.

Generate ID-aware standalone queries from the original numbered files:

```bash
python3 Scripts/converters/convert_query_mm_to_rpqmatrix.py --preserve-ids \
  ../wikidata-sparql-queries-any-con.txt \
  ../wikidata-sparql-queries_CON_ANY.txt \
  ../wikidata-only-any-safe.txt \
  -o Queries/rpqmatrix/wikidata
```

Each TSV line has an original query ID as a tab-separated prefix (`<ID>\t<query>`).
The runner validates the TSV's ordered IDs against the original catalog, then
launches each baseline engine **once per query set**. The engine loads the index
once, strips the prefix before parsing, executes every query `warmup_runs + runs`
times, and prints its original ID in every semicolon result row. One `res.txt`
and one `res.txt.meta.json` are written per engine and query set. The report
reader groups rows by ID and excludes the first `warmup_runs` samples per ID.
The older split files are no longer used by this configuration.

The dataset paths differ by engine:

- Pathrex: `../wikidata/Wikidata/wikidata-mm` (MatrixMarket directory).
- `rpqmatrix`: `../wikidata/Wikidata/wikidata-orig/wikidata.dat` (binary baseline index).
- `rpqmatrix-gb`: `../wikidata/Wikidata/wikidata-mm-txt/wikidata.dat` (text MatrixMarket index).

The available competitors in the server checkout are `none`, `join`, `metaac`, `mnc`,
`hybrid`, `rpqmatrix`, and `rpqmatrix-gb`. `rpq-static`, `row-sampling`, and the two
additional star hybrids are not in this checkout. The local uncommitted Pathrex changes
were deliberately not copied to the server.

Check all paths and generated commands without running the benchmark:

```bash
python3 Scripts/runners/run_benchmarks.py \
  --config Scripts/benchmark_config.adbis2026.json \
  --dataset wikidata --semantic wikidata \
  --query-set all --competitor all \
  --runs 5 --warmup-runs 1 --dry-run
```

Run the Pathrex optimizers over all three query sets:

```bash
python3 Scripts/runners/run_benchmarks.py \
  --config Scripts/benchmark_config.adbis2026.json \
  --dataset wikidata --semantic wikidata \
  --query-set all --competitor join,metaac,mnc,hybrid \
  --runs 5 --warmup-runs 1 --keep-going
```

To run the standalone engines as well, replace the competitor list with
`join,metaac,mnc,hybrid,rpqmatrix,rpqmatrix-gb` (or use `all` to include `none`).
Results go to `Results/wikidata/<query-set>/<competitor>/`.

The RPQ-matrix engines now load the index once per query set, not once per query.
`--keep-going` continues after a failed competitor/query set; it cannot recover
individual queries if an engine process is killed (for example, by OOM).
