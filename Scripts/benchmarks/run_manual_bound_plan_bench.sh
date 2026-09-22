#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SOURCE="$ROOT/Scripts/benchmarks/manual_bound_plan_bench.c"
BUILD_ROOT="$ROOT/Databases/pathrex/target/release/build"
GRAPHBLAS=$(find "$BUILD_ROOT" -maxdepth 5 -type f -path '*/out/lib/libgraphblas.a' \
  -print 2>/dev/null | sort | tail -n 1)

if [[ -z "$GRAPHBLAS" ]]; then
  echo "Pathrex release GraphBLAS build not found" >&2
  exit 1
fi

OUT_DIR=$(dirname "$(dirname "$GRAPHBLAS")")
LAGRAPH="$OUT_DIR/lib/liblagraph.a"
INCLUDE_DIR="$OUT_DIR/include/suitesparse"
BINARY="${TMPDIR:-/tmp}/manual_bound_plan_bench"

if [[ ! -f "$LAGRAPH" ]]; then
  echo "LAGraph static library not found: $LAGRAPH" >&2
  exit 1
fi

cc -std=c11 -O3 -march=native -DNDEBUG -Wall -Wextra -Wpedantic \
  -I"$INCLUDE_DIR" "$SOURCE" "$LAGRAPH" "$GRAPHBLAS" \
  -fopenmp -lm -lpthread -ldl -o "$BINARY"

exec "$BINARY" "$@"
