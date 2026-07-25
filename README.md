# How to bench all (wip. closed alpha.)

### pathrex
- query source: RPQ_bench/Queries/pathrex/rpqbench_250k
- dataset source: RPQ_bench/Datasets/rpqbench_250k/pathrex
- output: RPQ_bench/Results/rpqbench_250k/pathrex-test
- runner:
```
./Scripts/runners/run_pathrex.sh <0 any-any | 1 any-con | 2 con-any>
```
- run command:
`any-any`
```
cargo run --release -p pathrex --manifest-path ./Databases/pathrex/Cargo.toml --features bench --bin pathrex -- query --graph ./Datasets/rpqbench_250k/pathrex --format mm --queries ./Queries/pathrex/rpqbench_250k/any-any/queries.txt --base-iri=http://example.org/ --algo rpqmatrix --rpqmatrix-optimizer cardinality --output ./Results/rpqbench_250k/pathrex-test/any-any/res.json
```
`any-con`
```
cargo run --release -p pathrex --manifest-path ./Databases/pathrex/Cargo.toml --features bench --bin pathrex -- query --graph ./Datasets/rpqbench_250k/pathrex --format mm --queries ./Queries/pathrex/rpqbench_250k/any-con/queries.txt --base-iri=http://example.org/ --algo rpqmatrix --rpqmatrix-optimizer cardinality --output ./Results/rpqbench_250k/pathrex-test/any-con/res.json
```
`con-any`
```
cargo run --release -p pathrex --manifest-path ./Databases/pathrex/Cargo.toml --features bench --bin pathrex -- query --graph ./Datasets/rpqbench_250k/pathrex --format mm --queries ./Queries/pathrex/rpqbench_250k/con-any/queries.txt --base-iri=http://example.org/ --algo rpqmatrix --rpqmatrix-optimizer cardinality --output ./Results/rpqbench_250k/pathrex-test/con-any/res.json
```
### rpqmatrix-orig
- query source: RPQ_bench/Queries/rpqmatrix/rpqbench_250k
- dataset source: RPQ_bench/Datasets/rpqbench_250k/rpq-matrix/rpqbench_250k_orig.nt.dat
- output: RPQ_bench/Results/rpqbench_250k/rpq-matrix
- runner:
```
./Scripts/runners/run_rpqmatrix.sh <0 any-any | 1 any-con | 2 con-any>
```
- run command:
`any-any`
```
./Databases/rpq-matrix/build/baseline_query ./Datasets/rpqbench_250k/rpq-matrix/rpqbench_250k_orig.nt.dat ./Queries/rpqmatrix/rpqbench_250k/any-any/queries_mm.tsv 9 63052
```
`any-con`
```
./Databases/rpq-matrix/build/baseline_query ./Datasets/rpqbench_250k/rpq-matrix/rpqbench_250k_orig.nt.dat ./Queries/rpqmatrix/rpqbench_250k/any-con/queries_mm.tsv 9 63052
```
`con-any`
```
./Databases/rpq-matrix/build/baseline_query ./Datasets/rpqbench_250k/rpq-matrix/rpqbench_250k_orig.nt.dat ./Queries/rpqmatrix/rpqbench_250k/con-any/queries_mm.tsv 9 63052
```
### rpqmatrix-gb
- query source: RPQ_bench/Queries/rpqmatrix_gb/rpqbench_250k
- dataset source: RPQ_bench/Datasets/rpqbench_250k/rpq-matrix_GB/rpqbench_250k_orig.nt.dat
- output: RPQ_bench/Results/rpqbench_250k/rpq-matrix_GB
- prepare dataset from MatrixMarket directory:
```
./Scripts/converters/mm_to_rpq_GB.py ./Datasets/rpqbench_250k/rpq-matrix_GB rpqbench_250k_orig.nt.dat
```
- runner:
```
./Scripts/runners/run_rpqmatrix_gb.sh <0 any-any | 1 any-con | 2 con-any>
```
- run command:

`any-any`
```
./Databases/rpq-matrix_GB/build/baselineGB_query ./Datasets/rpqbench_250k/rpq-matrix_GB/rpqbench_250k_orig.nt.dat ./Queries/rpqmatrix_gb/rpqbench_250k/any-any/queries_mm.tsv 9 63052
```
`any-con`
```
./Databases/rpq-matrix_GB/build/baselineGB_query ./Datasets/rpqbench_250k/rpq-matrix_GB/rpqbench_250k_orig.nt.dat ./Queries/rpqmatrix_gb/rpqbench_250k/any-con/queries_mm.tsv 9 63052
```
`con-any`
```
./Databases/rpq-matrix_GB/build/baselineGB_query ./Datasets/rpqbench_250k/rpq-matrix_GB/rpqbench_250k_orig.nt.dat ./Queries/rpqmatrix_gb/rpqbench_250k/con-any/queries_mm.tsv 9 63052
```

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
