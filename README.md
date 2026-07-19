# How to bench all (wip. closed alpha.)

### pathrex
- query source: RPQ_bench/Queries/pathrex/rpqbench_250k
- dataset source: RPQ_bench/Datasets/rpqbench_250k/mm
- output:  RPQ_bench/Results/pathrex
- run commnad:
```
cargo run --release -p pathrex --features bench --bin pathrex -- bench --bench-mode fixed   --graph pathrex/tests/testdata/mm_graph   --format mm   --queries pathrex/tests/testdata/cases/con-any/queries.txt   --base-iri=http://example.org/   --algo rpqmatrix   --rpqmatrix-optimizer cardinality   --output ./results/bench/card/con-any/res.json  --warm-up-runs 5 --runs 100
```
### rpqmatrix-orig
- query source:
- dataset source:
- output:
- run commnad:
### rpqmatrix-gb
- query source:
- dataset source:
- output:
- run commnad:

# Future work:
## Reachability
- PathDB?
- LARPQ
- FalkorDB
- MillenniumDB
- pathrex (differnt optimizers)
- rpqmatrix
- rpqmatrixGB
- DuckDB
- Memgraph
- Neo4j
- Kuzu
- Umbra
- BlazeGraph
- TigerGraph
- Jena
- Virtuoso
- RingRPQ?
- Postgres?
- cuRPQ?
## Pathes
- PathDB
- LARPQ with pathes
- FalkorDB
- MillenniumDB
- something relative
- DuckDB
- Memgraph
- Neo4j
- Kuzu
- ReCAP