# Datasets

The full `rpqbench` dataset contains 150,144,666 triples, 57,761,174 vertices,
and 9 predicates. Dataset files are machine-local benchmark inputs and are not
stored in Git.

## Competitor inputs

The [competitor guide](../Databases/README.md) documents the complete N3/NT
conversion and all 15 engine formats. Existing `rpqbench_250k` uses the legacy
resource-edge projection: 24,225 vertices, 9 labels, 61,017 unique edges.
`prepare_250k.py --bootstrap-mm` prepares it from the source N3 when matrices
are missing; it refuses to overwrite an existing `prepared/`.

For a new dataset, `Scripts/competitors/prepare_rdf.py SOURCE OUTPUT --format nt`
(or `--format n3` / `turtle`) produces RDF, CSV, MatrixMarket and native matrix
layouts with collision-free names and a shared ID mapping. It retains resource
edges and excludes literal-object triples; its IDs differ from legacy 250k.
The generated graph inputs, dictionaries and manifest must be kept together.
