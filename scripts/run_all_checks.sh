#!/usr/bin/bash
set -euo pipefail

echo "[LTBA] Python version"
python3 --version

echo "[LTBA] Checking required packages"
python3 - <<'PY'
import importlib

required = ["pytest", "sympy", "dd"]
missing = []

for name in required:
    try:
        importlib.import_module(name)
        print(f"OK: {name}")
    except Exception as exc:
        print(f"MISSING: {name} ({exc})")
        missing.append(name)

if missing:
    raise SystemExit("Missing packages: " + ", ".join(missing))
PY

echo "[LTBA] Rebuilding v4 benchmark code from patches"
bash scripts/rebuild_ltba_v4_from_patches.sh

echo "[LTBA] Running v4 benchmark"
bash scripts/run_v4_benchmark.sh

echo "[LTBA] Done"
