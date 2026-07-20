#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 <semantic: 0 any-any | 1 any-con | 2 con-any> [dataset_base]" >&2
}

case "${1:-}" in
    0) SEMANTIC="any-any" ;;
    1) SEMANTIC="any-con" ;;
    2) SEMANTIC="con-any" ;;
    *) usage; exit 2 ;;
esac

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
BENCH_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"

resolve_path() {
    local path="$1"
    if [[ "$path" = /* ]]; then
        printf '%s\n' "$path"
    elif [[ -e "$path" || -L "$path" ]]; then
        (CDPATH= cd -- "$(dirname -- "$path")" && printf '%s/%s\n' "$PWD" "$(basename -- "$path")")
    else
        printf '%s/%s\n' "$BENCH_ROOT" "$path"
    fi
}

BIN="$BENCH_ROOT/Databases/rpq-matrix/build/baseline_query"
DATASET="$(resolve_path "${2:-Datasets/rpqbench_250k/rpq-matrix/rpqbench_250k_orig.nt.dat}")"
QUERY_DIR="$BENCH_ROOT/Queries/rpqmatrix/rpqbench_250k/$SEMANTIC/queries_mm_split"
OUT_DIR="$BENCH_ROOT/Results/rpqbench_250k/rpq-matrix/$SEMANTIC"
N_PREDS=9
N_TRIPLES=63052

if [[ ! -f "$DATASET" ]]; then
    echo "Dataset base file does not exist: $DATASET" >&2
    exit 1
fi
if [[ ! -f "$DATASET.SO" || ! -f "$DATASET.P" || ! -f "$DATASET.baseline-64/0001.mat" ]]; then
    echo "Dataset is missing .SO, .P, or .baseline-64/0001.mat for base: $DATASET" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"

found=0
while IFS= read -r name; do
    found=1
    query_file="$QUERY_DIR/$name"
    out_file="$OUT_DIR/$name"
    echo "rpq-matrix $SEMANTIC: $name" >&2
    "$BIN" "$DATASET" "$query_file" "$N_PREDS" "$N_TRIPLES" \
        | awk '/^[0-9]+;/ { print }' > "$out_file"
done < <(find "$QUERY_DIR" -maxdepth 1 -type f -name '*.txt' -printf '%f\n' | sort -V)

if [ "$found" -eq 0 ]; then
    echo "No query files found in $QUERY_DIR" >&2
    exit 1
fi
