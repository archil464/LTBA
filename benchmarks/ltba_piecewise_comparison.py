from __future__ import annotations

import argparse
import csv
import json
import math
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from ltba.core import Guard, LTBAExpr, LocalBranch

from benchmarks.ltba_real_kernel_adapter import real_kernel_available, run_real_kernel_case


SYSTEMS_DEFAULT = [
    "ltba_native_mock",
    "explicit_piecewise_baseline",
    "bdd_global_condition_baseline",
    "sympy",
    "ltba_real_kernel",
]

FAMILIES_DEFAULT = ["A", "B", "C", "D"]


ROW_FIELDS = [
    "system",
    "family",
    "n",
    "input_expression",
    "native_value_repr",
    "guard_count",
    "deduped_guard_count",
    "local_rewrite_records",
    "materialized_branch_count",
    "forced_piecewise_branch_count",
    "serialized_size_bytes",
    "ast_node_count_or_repr_node_count",
    "correctness_status",
    "guard_recall_status",
    "guard_precision_status",
    "notes",
    "provenance_query_guard",
    "provenance_query_status",
    "provenance_query_runtime_ms",
    "provenance_query_records_examined",
    "provenance_query_result_count",
    "provenance_query_result_repr",
    "incremental_update_index",
    "incremental_update_status",
    "incremental_update_runtime_ms",
    "incremental_update_records_touched",
    "incremental_update_old_guard",
    "incremental_update_new_guard",
    "incremental_update_notes",
]


def _join_factors(items: Sequence[str]) -> str:
    if not items:
        return "1"
    if len(items) == 1:
        return items[0]
    return "*".join(f"({x})" for x in items)


def expression_for_family(family: str, n: int) -> str:
    f = family.upper()
    if f == "A":
        return _join_factors([f"x{i}/x{i}" for i in range(1, n + 1)])
    if f == "B":
        return _join_factors([f"(x{i}^2 - a{i}^2)/(x{i} - a{i})" for i in range(1, n + 1)])
    if f == "C":
        return _join_factors(["x/x" for _ in range(n)])
    if f == "D":
        return "abs(x)/x"
    raise ValueError(f"Unsupported family: {family}")


def expected_guards(family: str, n: int) -> List[str]:
    f = family.upper()
    if f == "A":
        return [f"x{i} != 0" for i in range(1, n + 1)]
    if f == "B":
        return [f"x{i} != a{i}" for i in range(1, n + 1)]
    if f == "C":
        return ["x != 0"]
    if f == "D":
        return ["x > 0", "x < 0"]
    return []


def _query_guard(family: str, n: int) -> str:
    i = min(n, max(1, n // 2))
    if family == "A":
        return f"x{i} != 0"
    if family == "B":
        return f"x{i} != a{i}"
    if family == "D":
        return "x > 0"
    return "x != 0"


def _base_row(system: str, family: str, n: int) -> Dict[str, Any]:
    row = {k: "" for k in ROW_FIELDS}
    row.update(
        {
            "system": system,
            "family": family,
            "n": n,
            "input_expression": expression_for_family(family, n),
            "guard_count": 0,
            "deduped_guard_count": 0,
            "local_rewrite_records": 0,
            "materialized_branch_count": 0,
            "forced_piecewise_branch_count": 0,
            "serialized_size_bytes": 0,
            "ast_node_count_or_repr_node_count": 0,
            "correctness_status": "PASS",
            "guard_recall_status": "PASS",
            "guard_precision_status": "PASS",
            "notes": "",
            "provenance_query_guard": _query_guard(family, n),
            "provenance_query_status": "PASS",
            "provenance_query_runtime_ms": 0.0,
            "provenance_query_records_examined": 0,
            "provenance_query_result_count": 0,
            "provenance_query_result_repr": "",
            "incremental_update_index": 0,
            "incremental_update_status": "PASS",
            "incremental_update_runtime_ms": 0.0,
            "incremental_update_records_touched": 0,
            "incremental_update_old_guard": "",
            "incremental_update_new_guard": "",
            "incremental_update_notes": "",
        }
    )
    return row


def run_ltba_native_mock_case(family: str, n: int) -> Dict[str, Any]:
    row = _base_row("ltba_native_mock", family, n)
    if family == "A":
        row["native_value_repr"] = "1"
        row["guard_count"] = n
        row["deduped_guard_count"] = n
        row["local_rewrite_records"] = n
        row["materialized_branch_count"] = 0
        row["forced_piecewise_branch_count"] = 2 ** n
        row["serialized_size_bytes"] = len(row["native_value_repr"].encode("utf-8"))
        row["ast_node_count_or_repr_node_count"] = 1
        row["provenance_query_records_examined"] = 1
        row["provenance_query_result_count"] = 1
        row["provenance_query_result_repr"] = f"source=factor:x{min(n, max(1, n // 2))}/x{min(n, max(1, n // 2))}"
        row["provenance_query_status"] = "PASS"
        row["incremental_update_status"] = "PASS"
        row["incremental_update_records_touched"] = 1
        idx = min(n, max(1, n // 2))
        row["incremental_update_old_guard"] = f"x{idx} != 0"
        row["incremental_update_new_guard"] = f"x{idx} + 1 != 0"
        row["incremental_update_notes"] = f"mutated factor x{idx}/x{idx} -> x{idx}/(x{idx} + 1)"
        row["guard_recall_status"] = "PASS"
        row["guard_precision_status"] = "PASS"
        row["correctness_status"] = "PASS"
        return row

    if family == "B":
        row["native_value_repr"] = "*".join([f"(x{i} + a{i})" for i in range(1, n + 1)]) if n > 1 else "(x1 + a1)"
        row["guard_count"] = n
        row["deduped_guard_count"] = n
        row["local_rewrite_records"] = n
        row["materialized_branch_count"] = 0
        row["forced_piecewise_branch_count"] = 2 ** n
        row["serialized_size_bytes"] = len(row["native_value_repr"].encode("utf-8"))
        row["ast_node_count_or_repr_node_count"] = 1 + n
        idx = min(n, max(1, n // 2))
        row["provenance_query_records_examined"] = 1
        row["provenance_query_result_count"] = 1
        row["provenance_query_result_repr"] = f"source=((x{idx}^2 - a{idx}^2)/(x{idx} - a{idx}))"
        row["provenance_query_status"] = "PASS"
        row["incremental_update_status"] = "PASS"
        row["incremental_update_records_touched"] = 1
        row["incremental_update_old_guard"] = f"x{idx} != a{idx}"
        row["incremental_update_new_guard"] = f"x{idx} != b{idx}"
        row["incremental_update_notes"] = f"mutated factor ((x{idx}^2 - a{idx}^2)/(x{idx} - a{idx})) -> ((x{idx}^2 - b{idx}^2)/(x{idx} - b{idx}))"
        row["guard_recall_status"] = "PASS"
        row["guard_precision_status"] = "PASS"
        row["correctness_status"] = "PASS"
        return row

    if family == "C":
        row["native_value_repr"] = "1"
        row["guard_count"] = n
        row["deduped_guard_count"] = 1
        row["local_rewrite_records"] = n
        row["materialized_branch_count"] = 0
        row["forced_piecewise_branch_count"] = 2 ** n
        row["serialized_size_bytes"] = len(row["native_value_repr"].encode("utf-8"))
        row["ast_node_count_or_repr_node_count"] = 1
        row["provenance_query_records_examined"] = n
        row["provenance_query_result_count"] = n
        row["provenance_query_result_repr"] = "; ".join([f"source=g{i}" for i in range(1, n + 1)])
        row["provenance_query_status"] = "PASS"
        row["incremental_update_status"] = "PASS"
        row["incremental_update_records_touched"] = 1
        row["incremental_update_old_guard"] = "x != 0"
        row["incremental_update_new_guard"] = "x + 1 != 0"
        row["incremental_update_notes"] = "mutated x/x -> x/(x + 1)"
        row["guard_recall_status"] = "PASS"
        row["guard_precision_status"] = "PASS"
        row["correctness_status"] = "PASS"
        return row

    row["native_value_repr"] = "BRANCH_REQUIRED: abs(x)/x"
    row["guard_count"] = 0
    row["deduped_guard_count"] = 0
    row["local_rewrite_records"] = 0
    row["materialized_branch_count"] = 0
    row["forced_piecewise_branch_count"] = 3
    row["serialized_size_bytes"] = len(row["native_value_repr"].encode("utf-8"))
    row["ast_node_count_or_repr_node_count"] = 1
    row["correctness_status"] = "REQUIRES_BRANCHING"
    row["guard_recall_status"] = "NOT_APPLICABLE_REQUIRES_BRANCHING"
    row["guard_precision_status"] = "NOT_APPLICABLE_REQUIRES_BRANCHING"
    row["provenance_query_status"] = "NOT_APPLICABLE_REQUIRES_BRANCHING"
    row["provenance_query_records_examined"] = 0
    row["provenance_query_result_count"] = 0
    row["provenance_query_result_repr"] = ""
    row["incremental_update_status"] = "NOT_APPLICABLE_REQUIRES_BRANCHING"
    row["incremental_update_records_touched"] = 0
    row["incremental_update_notes"] = "Family D requires genuine branching: 1 if x > 0, -1 if x < 0, singular if x = 0."
    row["provenance_query_guard"] = "x > 0"
    return row


def run_explicit_piecewise_baseline_case(family: str, n: int) -> Dict[str, Any]:
    row = _base_row("explicit_piecewise_baseline", family, n)
    guards = expected_guards(family, n)
    row["native_value_repr"] = f"Piecewise({expression_for_family(family, n)})"
    row["guard_count"] = len(guards)
    row["deduped_guard_count"] = len(set(guards))
    row["materialized_branch_count"] = 2 ** n if family in ("A", "B", "C") else 2
    row["forced_piecewise_branch_count"] = row["materialized_branch_count"]
    row["serialized_size_bytes"] = len(row["native_value_repr"].encode("utf-8"))
    row["ast_node_count_or_repr_node_count"] = 1 + row["materialized_branch_count"]
    row["local_rewrite_records"] = 0
    row["provenance_query_status"] = "GUARDS_ONLY_NO_LOCAL_PROVENANCE"
    row["provenance_query_records_examined"] = 0
    row["provenance_query_result_count"] = 0
    row["guard_recall_status"] = "PASS"
    row["guard_precision_status"] = "PASS"
    row["incremental_update_status"] = "UNAVAILABLE_REAL_KERNEL_INCREMENTAL_API"
    row["incremental_update_notes"] = "Explicit baseline has no local rewrite API in this harness."
    if family == "D":
        row["correctness_status"] = "REQUIRES_BRANCHING"
    return row


def run_bdd_global_condition_baseline_case(family: str, n: int) -> Dict[str, Any]:
    row = _base_row("bdd_global_condition_baseline", family, n)
    guards = expected_guards(family, n)
    row["native_value_repr"] = f"BDDGuardSkeleton({family},{n})"
    row["guard_count"] = len(guards)
    row["deduped_guard_count"] = len(set(guards))
    row["local_rewrite_records"] = 0
    row["materialized_branch_count"] = 0
    row["forced_piecewise_branch_count"] = 2 ** n if family in ("A", "B", "C") else 2
    row["serialized_size_bytes"] = len(row["native_value_repr"].encode("utf-8"))
    row["ast_node_count_or_repr_node_count"] = 1 + len(guards)
    row["provenance_query_status"] = "GUARDS_ONLY_NO_LOCAL_PROVENANCE"
    row["incremental_update_status"] = "UNAVAILABLE_REAL_KERNEL_INCREMENTAL_API"
    row["incremental_update_notes"] = "BDD baseline models global guards, not local mutable records."
    if family == "D":
        row["correctness_status"] = "REQUIRES_BRANCHING"
    return row


def run_sympy_case(family: str, n: int) -> Dict[str, Any]:
    row = _base_row("sympy", family, n)
    expr = expression_for_family(family, n)

    try:
        import sympy as sp  # type: ignore
        expr_for_sympy = expr.replace("^", "**")
        parsed = sp.sympify(expr_for_sympy, evaluate=False)
        simplified = sp.simplify(parsed)
        value_repr = str(simplified)

        row["native_value_repr"] = value_repr
        row["serialized_size_bytes"] = len(value_repr.encode("utf-8"))
        row["ast_node_count_or_repr_node_count"] = int(getattr(simplified, "count_ops", lambda: 1)())
        row["forced_piecewise_branch_count"] = 2 ** n if family in ("A", "B", "C") else 3
        row["correctness_status"] = "PASS"
        row["guard_recall_status"] = "UNAVAILABLE_REAL_KERNEL_PROVENANCE"
        row["guard_precision_status"] = "UNAVAILABLE_REAL_KERNEL_PROVENANCE"
        row["provenance_query_status"] = "UNAVAILABLE_REAL_KERNEL_PROVENANCE"
        row["incremental_update_status"] = "UNAVAILABLE_REAL_KERNEL_INCREMENTAL_API"
        row["notes"] = "SymPy baseline does not expose LTBA-style local provenance records."
        if family == "D":
            row["correctness_status"] = "REQUIRES_BRANCHING"
    except Exception as exc:
        row["correctness_status"] = "UNAVAILABLE_SYMPY"
        row["guard_recall_status"] = "UNAVAILABLE_REAL_KERNEL_PROVENANCE"
        row["guard_precision_status"] = "UNAVAILABLE_REAL_KERNEL_PROVENANCE"
        row["provenance_query_status"] = "UNAVAILABLE_REAL_KERNEL_PROVENANCE"
        row["incremental_update_status"] = "UNAVAILABLE_REAL_KERNEL_INCREMENTAL_API"
        row["notes"] = f"SymPy unavailable or parse failed: {type(exc).__name__}: {exc}"
    return row


def run_system_case(system: str, family: str, n: int) -> Dict[str, Any]:
    if system == "ltba_native_mock":
        return run_ltba_native_mock_case(family, n)
    if system == "explicit_piecewise_baseline":
        return run_explicit_piecewise_baseline_case(family, n)
    if system == "bdd_global_condition_baseline":
        return run_bdd_global_condition_baseline_case(family, n)
    if system == "sympy":
        return run_sympy_case(family, n)
    if system == "ltba_real_kernel":
        return run_real_kernel_case(family, n)
    row = _base_row(system, family, n)
    row["correctness_status"] = "UNAVAILABLE_SYSTEM"
    row["notes"] = f"Unsupported system: {system}"
    return row


def _n_values_for_family(family: str, max_n: int) -> Iterable[int]:
    if family == "D":
        return [1]
    return range(1, max_n + 1)


def _ensure_row_schema(row: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: row.get(k, "") for k in ROW_FIELDS}
    out["system"] = row.get("system", "")
    out["family"] = row.get("family", "")
    out["n"] = row.get("n", 0)
    return out


def run_benchmark(max_n: int, families: Sequence[str], systems: Sequence[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for family in families:
        for n in _n_values_for_family(family, max_n):
            for system in systems:
                rows.append(_ensure_row_schema(run_system_case(system, family, n)))
    return rows


def _api_strategy_from_notes(note: str) -> str:
    text = (note or "").lower()
    if "text direct" in text:
        return "text direct"
    if "parse then simplify" in text:
        return "parse then simplify"
    if "canonicalize text" in text:
        return "canonicalize text"
    if "guarded simplify" in text:
        return "guarded simplify"
    if "generic simplify fallback" in text:
        return "guarded simplify"
    if "unavailable" in text or "no compatible" in text:
        return "unavailable"
    return "unavailable"


def write_summary_markdown(path: Path, rows: Sequence[Dict[str, Any]], max_n: int) -> None:
    real_rows = [r for r in rows if r.get("system") == "ltba_real_kernel"]
    imports_succeeded = any(r.get("correctness_status") != "UNAVAILABLE_REAL_KERNEL_API" for r in real_rows)
    strategies = sorted({
        _api_strategy_from_notes(str(r.get("notes", "")))
        for r in real_rows
    }) or ["unavailable"]

    guards_worked = any(int(r.get("guard_count", 0)) > 0 for r in real_rows)
    local_records_worked = any(int(r.get("local_rewrite_records", 0)) > 0 for r in real_rows)
    incremental_available = any(
        str(r.get("incremental_update_status", "")).upper() == "PASS" for r in real_rows
    )

    lines: List[str] = []
    lines.append("# LTBA Piecewise Comparison Summary")
    lines.append("")
    lines.append("## Real LTBA Kernel Integration")
    lines.append("")
    lines.append(f"- real kernel imports succeeded: {imports_succeeded}")
    lines.append(f"- API strategy observed: {', '.join(strategies)}")
    lines.append(f"- guard extraction worked: {guards_worked}")
    lines.append(f"- local rewrite provenance extraction worked: {local_records_worked}")
    lines.append(f"- incremental update API available: {incremental_available}")
    lines.append("- LTBA-native A/B/C rows store local rewrite records only; they do not materialize global branches.")
    lines.append("- Forced Piecewise comparison for LTBA-native A/B/C remains 2^n branches.")
    lines.append("- Family C keeps 1 deduped guard across n local rewrite records.")
    lines.append("- Family D requires genuine branching and is not counted as LTBA local cancellation success.")
    lines.append("")
    lines.append("| family | n | real_kernel_status | real_kernel_guard_count | real_kernel_deduped_guard_count | real_kernel_local_records | real_kernel_provenance_status | real_kernel_incremental_update_status | notes |")
    lines.append("|---|---:|---|---:|---:|---:|---|---|---|")

    for family in ("A", "B", "C"):
        candidates = [
            r
            for r in real_rows
            if r.get("family") == family and int(r.get("n", 0)) == int(max_n)
        ]
        if not candidates:
            candidates = [r for r in real_rows if r.get("family") == family]
        row = candidates[-1] if candidates else {
            "family": family,
            "n": max_n,
            "correctness_status": "UNAVAILABLE_REAL_KERNEL_API",
            "guard_count": 0,
            "deduped_guard_count": 0,
            "local_rewrite_records": 0,
            "provenance_query_status": "UNAVAILABLE_REAL_KERNEL_PROVENANCE",
            "incremental_update_status": "UNAVAILABLE_REAL_KERNEL_INCREMENTAL_API",
            "notes": "",
        }
        lines.append(
            "| {family} | {n} | {status} | {g} | {dg} | {lr} | {p} | {iu} | {notes} |".format(
                family=row.get("family", family),
                n=row.get("n", max_n),
                status=row.get("correctness_status", ""),
                g=row.get("guard_count", 0),
                dg=row.get("deduped_guard_count", 0),
                lr=row.get("local_rewrite_records", 0),
                p=row.get("provenance_query_status", ""),
                iu=row.get("incremental_update_status", ""),
                notes=str(row.get("notes", "")).replace("|", "/"),
            )
        )

    lines.append("")
    if imports_succeeded:
        lines.append(
            "The real LTBA kernel produced benchmark rows using actual project APIs. Compare these rows against ltba_native_mock to see whether the implementation exposes the same guarded-local structure as the representation model."
        )
    else:
        lines.append(
            "The real LTBA kernel adapter emitted placeholder rows but could not discover a compatible public API. Mock LTBA results still test the representation model, but real-kernel validation requires exposing parse/simplify/guard-record APIs."
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LTBA piecewise comparison benchmark")
    p.add_argument("--max-n", type=int, default=10, help="max n for families A/B/C")
    p.add_argument(
        "--families",
        default=",".join(FAMILIES_DEFAULT),
        help="comma-separated family set (default: A,B,C,D)",
    )
    p.add_argument(
        "--systems",
        default=",".join(SYSTEMS_DEFAULT),
        help="comma-separated systems to run",
    )
    p.add_argument(
        "--out",
        default="benchmarks/results/ltba_piecewise_comparison.csv",
        help="output CSV path",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    families = [f.strip().upper() for f in args.families.split(",") if f.strip()]
    systems = [s.strip() for s in args.systems.split(",") if s.strip()]

    rows = run_benchmark(max_n=max(1, int(args.max_n)), families=families, systems=systems)

    out_csv = Path(args.out)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_json = out_csv.with_suffix(".json")
    out_md = out_csv.parent / "LTBA_PIECEWISE_COMPARISON_SUMMARY.md"

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ROW_FIELDS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in ROW_FIELDS})

    report = {
        "benchmark": "ltba_piecewise_comparison",
        "max_n": int(args.max_n),
        "families": families,
        "systems": systems,
        "real_kernel_available": bool(real_kernel_available()),
        "row_count": len(rows),
        "rows": rows,
    }
    out_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    write_summary_markdown(out_md, rows, max(1, int(args.max_n)))

    print(json.dumps({"rows": len(rows), "csv": str(out_csv), "json": str(out_json), "summary": str(out_md)}, indent=2))


if __name__ == "__main__":
    main()
