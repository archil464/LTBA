#!/usr/bin/env bash
set -euo pipefail

PY=${PYTHON:-python}

echo "[LTBA] Python version"
$PY --version

echo "[LTBA] Running tests (pytest)"
$PY -m pytest -q

echo "[LTBA] Running benchmark smoke"
$PY -m benchmarks.benchmark_v4 --smoke

echo "[LTBA] Done"

