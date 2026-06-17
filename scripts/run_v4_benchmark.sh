#!/usr/bin/env bash
set -euo pipefail

# Simple wrapper to run the reproducible v4 benchmark runner from the tracked package.
PYTHON=${PYTHON:-python}
exec "$PYTHON" -m benchmarks.benchmark_v4 "$@"
