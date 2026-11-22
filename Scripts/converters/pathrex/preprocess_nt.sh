#!/usr/bin/env bash
# Preserve the legacy upstream Wikidata filtering and name projection.
set -euo pipefail
if [[ $# -ne 2 || -e "$2" ]]; then
  echo "Usage: $0 input.nt new-output-directory" >&2
  exit 2
fi
rpq_root=$(cd "$(dirname "$0")/../../.." && pwd)
rpq_python=${RPQ_PYTHON:-python3}
rpq_temp=$(mktemp -d)
trap 'rm -f -- "$rpq_temp/graph.nt"; rmdir -- "$rpq_temp"' EXIT
"$rpq_python" "$rpq_root/vendor/larpq/Scripts/truncate" "$1" \
  | "$rpq_python" "$rpq_root/vendor/larpq/Scripts/deprefix-nt" \
  | "$rpq_python" "$rpq_root/vendor/larpq/Scripts/remove-dups" /dev/stdin \
  > "$rpq_temp/graph.nt"
"$rpq_python" "$rpq_root/vendor/larpq/Scripts/nt-to-mm" "$rpq_temp/graph.nt" "$2"
