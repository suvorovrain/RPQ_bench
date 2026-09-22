#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SOURCE="$ROOT/Scripts/benchmarks/bound_matrix_vs_vector.c"
BUILD_ROOT="$ROOT/Databases/pathrex/target/release/build"
LIBRARY=$(find "$BUILD_ROOT" -maxdepth 5 -type f -path '*/out/lib/libgraphblas.a' \
  -print 2>/dev/null | sort | tail -n 1)

if [[ -z "$LIBRARY" ]]; then
  echo "GraphBLAS release build not found." >&2
  echo "Run: cargo build --release --manifest-path Databases/pathrex/Cargo.toml -p pathrex --features bench --bin pathrex" >&2
  exit 1
fi

OUT_DIR=$(dirname "$(dirname "$LIBRARY")")
INCLUDE_DIR="$OUT_DIR/include/suitesparse"
BINARY="${TMPDIR:-/tmp}/bound_matrix_vs_vector"

cc -std=c11 -O3 -march=native -DNDEBUG -Wall -Wextra -Wpedantic \
  -I"$INCLUDE_DIR" "$SOURCE" "$LIBRARY" \
  -fopenmp -lm -lpthread -ldl -o "$BINARY"

exec "$BINARY" "$@"
