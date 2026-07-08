from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


def test_piecewise_benchmark_cli_writes_csv_json_and_summary(tmp_path: Path):
    out_csv = tmp_path / "ltba_piecewise_comparison.csv"
    cmd = [
        sys.executable,
        "benchmarks/ltba_piecewise_comparison.py",
        "--max-n",
        "3",
        "--out",
        str(out_csv),
    ]
    subprocess.run(cmd, check=True)

    out_json = out_csv.with_suffix(".json")
    out_md = out_csv.parent / "LTBA_PIECEWISE_COMPARISON_SUMMARY.md"

    assert out_csv.exists()
    assert out_json.exists()
    assert out_md.exists()

    with out_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert rows
    systems = {r["system"] for r in rows}
    assert "ltba_native_mock" in systems
    assert "explicit_piecewise_baseline" in systems
    assert "bdd_global_condition_baseline" in systems
    assert "sympy" in systems
    assert "ltba_real_kernel" in systems

    report = json.loads(out_json.read_text(encoding="utf-8"))
    assert report["benchmark"] == "ltba_piecewise_comparison"
    assert any(r["system"] == "ltba_real_kernel" for r in report["rows"])

    summary = out_md.read_text(encoding="utf-8")
    assert "Real LTBA Kernel Integration" in summary


def test_family_d_not_treated_as_plain_pass_and_sympy_parses(tmp_path: Path):
    out_csv = tmp_path / "ltba_piecewise_comparison_d.csv"
    cmd = [
        sys.executable,
        "benchmarks/ltba_piecewise_comparison.py",
        "--families",
        "D",
        "--max-n",
        "3",
        "--out",
        str(out_csv),
    ]
    subprocess.run(cmd, check=True)

    with out_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert rows

    sympy_rows = [r for r in rows if r["system"] == "sympy"]
    assert sympy_rows
    for row in sympy_rows:
        assert "NameError: name 'Mul' is not defined" not in row.get("notes", "")
        assert row["correctness_status"] in {"PASS", "REQUIRES_BRANCHING", "UNAVAILABLE_SYMPY"}

    for system in {"explicit_piecewise_baseline", "bdd_global_condition_baseline", "sympy"}:
        branch_rows = [r for r in rows if r["system"] == system]
        assert branch_rows
        for row in branch_rows:
            if system == "bdd_global_condition_baseline":
                assert int(row["materialized_branch_count"]) == 0
            if system == "sympy" and row["family"] in {"A", "B", "C"}:
                assert int(row["forced_piecewise_branch_count"]) == 3 or int(row["forced_piecewise_branch_count"]) > 0

    mock_rows = [r for r in rows if r["system"] == "ltba_native_mock"]
    assert mock_rows
    mock = mock_rows[0]
    assert mock["native_value_repr"] == "BRANCH_REQUIRED: abs(x)/x"
    assert mock["correctness_status"] == "REQUIRES_BRANCHING"
    assert mock["provenance_query_status"] == "NOT_APPLICABLE_REQUIRES_BRANCHING"
    assert mock["incremental_update_status"] == "NOT_APPLICABLE_REQUIRES_BRANCHING"
    assert int(mock["local_rewrite_records"]) == 0
    assert int(mock["materialized_branch_count"]) == 0
    assert int(mock["forced_piecewise_branch_count"]) == 3
    assert int(mock["guard_count"]) == 0
    assert int(mock["deduped_guard_count"]) == 0


def test_ltba_mock_a_b_c_metrics_are_semantically_correct(tmp_path: Path):
    out_csv = tmp_path / "ltba_piecewise_comparison_abc.csv"
    cmd = [
        sys.executable,
        "benchmarks/ltba_piecewise_comparison.py",
        "--families",
        "A,B,C",
        "--max-n",
        "5",
        "--out",
        str(out_csv),
    ]
    subprocess.run(cmd, check=True)

    with out_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    def pick(system: str, family: str, n: str = "5"):
        return [r for r in rows if r["system"] == system and r["family"] == family and r["n"] == n][0]

    a = pick("ltba_native_mock", "A")
    assert a["native_value_repr"] == "1"
    assert int(a["guard_count"]) == 5
    assert int(a["deduped_guard_count"]) == 5
    assert int(a["local_rewrite_records"]) == 5
    assert int(a["materialized_branch_count"]) == 0
    assert int(a["forced_piecewise_branch_count"]) == 32
    assert a["correctness_status"] == "PASS"
    assert a["guard_recall_status"] == "PASS"
    assert a["guard_precision_status"] == "PASS"
    assert a["provenance_query_status"] == "PASS"
    assert int(a["provenance_query_records_examined"]) == 1
    assert int(a["provenance_query_result_count"]) == 1
    assert "x3/x3" in a["provenance_query_result_repr"] or "x2/x2" in a["provenance_query_result_repr"]
    assert a["incremental_update_status"] == "PASS"
    assert int(a["incremental_update_records_touched"]) == 1
    assert a["incremental_update_old_guard"] == "x2 != 0" or a["incremental_update_old_guard"] == "x3 != 0"
    assert a["incremental_update_new_guard"] == "x2 + 1 != 0" or a["incremental_update_new_guard"] == "x3 + 1 != 0"

    b = pick("ltba_native_mock", "B")
    assert int(b["guard_count"]) == 5
    assert int(b["deduped_guard_count"]) == 5
    assert int(b["local_rewrite_records"]) == 5
    assert int(b["materialized_branch_count"]) == 0
    assert int(b["forced_piecewise_branch_count"]) == 32
    assert "x1 + a1" in b["native_value_repr"]
    assert b["correctness_status"] == "PASS"
    assert b["guard_recall_status"] == "PASS"
    assert b["guard_precision_status"] == "PASS"
    assert b["provenance_query_status"] == "PASS"
    assert int(b["provenance_query_records_examined"]) == 1
    assert int(b["provenance_query_result_count"]) == 1
    assert "(x3^2 - a3^2)/(x3 - a3)" in b["provenance_query_result_repr"] or "(x2^2 - a2^2)/(x2 - a2)" in b["provenance_query_result_repr"]
    assert b["incremental_update_status"] == "PASS"
    assert int(b["incremental_update_records_touched"]) == 1
    assert b["incremental_update_old_guard"] == "x2 != a2" or b["incremental_update_old_guard"] == "x3 != a3"
    assert b["incremental_update_new_guard"] == "x2 != b2" or b["incremental_update_new_guard"] == "x3 != b3"

    c = pick("ltba_native_mock", "C")
    assert c["native_value_repr"] == "1"
    assert int(c["guard_count"]) == 5
    assert int(c["deduped_guard_count"]) == 1
    assert int(c["local_rewrite_records"]) == 5
    assert int(c["materialized_branch_count"]) == 0
    assert int(c["forced_piecewise_branch_count"]) == 32
    assert int(c["provenance_query_result_count"]) == 5
    assert c["correctness_status"] == "PASS"
    assert c["guard_recall_status"] == "PASS"
    assert c["guard_precision_status"] == "PASS"
    assert c["provenance_query_status"] == "PASS"
    assert c["incremental_update_status"] == "PASS"
    assert int(c["incremental_update_records_touched"]) == 1


def test_ltba_mock_a_b_c_metrics_are_semantically_correct(tmp_path: Path):
    out_csv = tmp_path / "ltba_piecewise_comparison_abc.csv"
    cmd = [
        sys.executable,
        "benchmarks/ltba_piecewise_comparison.py",
        "--families",
        "A,B,C",
        "--max-n",
        "5",
        "--out",
        str(out_csv),
    ]
    subprocess.run(cmd, check=True)

    with out_csv.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    def pick(system: str, family: str, n: str = "5"):
        return [r for r in rows if r["system"] == system and r["family"] == family and r["n"] == n][0]

    a = pick("ltba_native_mock", "A")
    assert a["native_value_repr"] == "1"
    assert int(a["guard_count"]) == 5
    assert int(a["deduped_guard_count"]) == 5
    assert int(a["local_rewrite_records"]) == 5
    assert int(a["materialized_branch_count"]) == 0
    assert int(a["forced_piecewise_branch_count"]) == 32
    assert a["correctness_status"] == "PASS"
    assert a["guard_recall_status"] == "PASS"
    assert a["guard_precision_status"] == "PASS"
    assert a["provenance_query_status"] == "PASS"
    assert int(a["provenance_query_records_examined"]) == 1
    assert int(a["provenance_query_result_count"]) == 1
    assert "x3/x3" in a["provenance_query_result_repr"] or "x2/x2" in a["provenance_query_result_repr"]
    assert a["incremental_update_status"] == "PASS"
    assert int(a["incremental_update_records_touched"]) == 1

    b = pick("ltba_native_mock", "B")
    assert int(b["guard_count"]) == 5
    assert int(b["deduped_guard_count"]) == 5
    assert int(b["local_rewrite_records"]) == 5
    assert int(b["materialized_branch_count"]) == 0
    assert int(b["forced_piecewise_branch_count"]) == 32
    assert "x1 + a1" in b["native_value_repr"]
    assert b["correctness_status"] == "PASS"
    assert b["guard_recall_status"] == "PASS"
    assert b["guard_precision_status"] == "PASS"
    assert b["provenance_query_status"] == "PASS"
    assert int(b["provenance_query_records_examined"]) == 1
    assert int(b["provenance_query_result_count"]) == 1
    assert "(x3^2 - a3^2)/(x3 - a3)" in b["provenance_query_result_repr"] or "(x2^2 - a2^2)/(x2 - a2)" in b["provenance_query_result_repr"]
    assert b["incremental_update_status"] == "PASS"
    assert int(b["incremental_update_records_touched"]) == 1

    c = pick("ltba_native_mock", "C")
    assert c["native_value_repr"] == "1"
    assert int(c["guard_count"]) == 5
    assert int(c["deduped_guard_count"]) == 1
    assert int(c["local_rewrite_records"]) == 5
    assert int(c["materialized_branch_count"]) == 0
    assert int(c["forced_piecewise_branch_count"]) == 32
    assert int(c["provenance_query_result_count"]) == 5
    assert c["correctness_status"] == "PASS"
    assert c["guard_recall_status"] == "PASS"
    assert c["guard_precision_status"] == "PASS"
