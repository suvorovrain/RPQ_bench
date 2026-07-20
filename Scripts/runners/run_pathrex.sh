#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 <semantic: 0 any-any | 1 any-con | 2 con-any> [dataset_dir]" >&2
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

GRAPH="$(resolve_path "${2:-Datasets/rpqbench_250k/pathrex}")"
QUERIES="$BENCH_ROOT/Queries/pathrex/rpqbench_250k/$SEMANTIC/queries.txt"
OUT_DIR="$BENCH_ROOT/Results/rpqbench_250k/pathrex-test/$SEMANTIC"
OUT_FILE="$OUT_DIR/res.json"

if [[ ! -d "$GRAPH" ]]; then
    echo "Dataset directory does not exist: $GRAPH" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"

cargo run --release \
    --manifest-path "$BENCH_ROOT/Databases/pathrex/Cargo.toml" \
    -p pathrex \
    --features bench \
    --bin pathrex \
    -- query \
    --graph "$GRAPH" \
    --format mm \
    --queries "$QUERIES" \
    --base-iri=http://example.org/ \
    --algo rpqmatrix \
    --rpqmatrix-optimizer cardinality \
    --output "$OUT_FILE"
