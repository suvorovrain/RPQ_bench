# Wikidata benchmark on ADBIS2026

Run commands from `/home/lamba/ADBIS2026/RPQ_bench`. The machine-specific configuration is
`Scripts/benchmark_config.adbis2026.json`; it does not replace the configuration used on the
other benchmark server.

The three query sets are `sparql-queries-any-con`, `sparql-queries_CON_ANY`, and
`only-any-safe`. The original files live in `/home/lamba/ADBIS2026/wikidata-*.txt`.
Pathrex reads those files directly. The two standalone RPQ-matrix engines read converted
queries in `Queries/rpqmatrix/wikidata/`.

Generate ID-aware standalone queries from the original numbered files:

```bash
python3 Scripts/converters/convert_query_mm_to_rpqmatrix.py --preserve-ids \
  ../wikidata-sparql-queries-any-con.txt \
  ../wikidata-sparql-queries_CON_ANY.txt \
  ../wikidata-only-any-safe.txt \
  -o Queries/rpqmatrix/wikidata
for source in Queries/rpqmatrix/wikidata/*.tsv; do
  python3 Scripts/converters/split_and_extend.py "$source" 1 \
    -o "${source%.tsv}_split_id"
done
```

The TSV and every split `<ID>.txt` keep each original query ID as a tab-separated
prefix (`<ID>\t<query>`). Both baseline engines strip the prefix before parsing
and print that ID in every semicolon result row. The runner takes the current
IDs from the original catalog, so obsolete split files left after removing a
query are ignored. `--runs` and `--warmup-runs` are passed to the engines, which
execute each query `warmup_runs + runs` times in the same loaded process;
split files need only one query line. Each successful result has a neighboring
`<ID>.txt.meta.json` with the source ID, warm-up count, measured count and paths.
The first `warmup_runs` rows are excluded by the report reader. Old unprefixed
query files remain supported; those use the engine's one-based line number as ID.

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

**Runtime warning:** the current runner starts each standalone RPQ-matrix engine once
per query. Each process reloads the entire Wikidata index; with hundreds of queries,
this can take far longer than the measured query execution. The benchmark's recorded
times exclude this loading, but the wall-clock time of the full run does not. Prefer
running Pathrex first and plan a separate window for the standalone engines. `--keep-going`
continues after a failed competitor/query set, not after an individual Pathrex query
fails inside one `pathrex bench` process.
