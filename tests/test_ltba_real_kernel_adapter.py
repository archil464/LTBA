from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

from benchmarks.ltba_real_kernel_adapter import real_kernel_available, run_real_kernel_case


REQUIRED_COLUMNS = {
    "guard_count",
    "deduped_guard_count",
    "local_rewrite_records",
    "provenance_query_status",
    "incremental_update_status",
}


def test_import_and_run_case_returns_dict_shape():
    row = run_real_kernel_case("A", 3)
    assert isinstance(row, dict)
    assert row["system"] == "ltba_real_kernel"
    assert row["family"] == "A"
    assert row["n"] == 3


def test_unavailable_is_graceful_when_kernel_missing():
    row = run_real_kernel_case("A", 3)
    if not real_kernel_available():
        assert "UNAVAILABLE" in str(row["correctness_status"])


def test_required_columns_present():
    row = run_real_kernel_case("B", 2)
    for key in REQUIRED_COLUMNS:
        assert key in row


def test_cli_small_run_contains_real_kernel_rows(tmp_path: Path):
    out_csv = tmp_path / "piecewise_small.csv"
    cmd = [
        sys.executable,
        "benchmarks/ltba_piecewise_comparison.py",
        "--max-n",
        "3",
        "--out",
        str(out_csv),
    ]
    subprocess.run(cmd, check=True)

    with out_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        systems = {row["system"] for row in reader}

    assert "ltba_real_kernel" in systems


def test_soft_assertions_if_real_kernel_available():
    row = run_real_kernel_case("C", 3)
    if real_kernel_available() and "UNAVAILABLE" not in str(row.get("correctness_status", "")):
        assert int(row.get("guard_count", 0)) >= 0
        assert int(row.get("serialized_size_bytes", 0)) > 0
