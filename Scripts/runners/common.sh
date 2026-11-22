#!/usr/bin/env bash

run_configured_competitor() {
    local competitor="$1"
    shift
    local script_dir
    script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
    exec python3 "$script_dir/run_benchmarks.py" --competitor "$competitor" "$@"
}
