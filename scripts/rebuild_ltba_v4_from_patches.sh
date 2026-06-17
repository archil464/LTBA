#!/usr/bin/env bash
set -euo pipefail

echo "Rebuild script deprecated: source is now tracked under ltba/"
echo "Use the tracked package: import ltba; the scripts/ helpers are convenience only."

exit 0

cat > "$BENCH/ltba_general_benchmark.py" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from pathlib import Path
from typing import Dict, List

try:
    from kernel.ltba_general import registry
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"Cannot import kernel.ltba_general. Run with PYTHONPATH=. Error: {exc}")


def timed(fn):
    t0 = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - t0


def sympy_piecewise_estimate(component_name: str, n: int) -> Dict[str, object]:
    """
    Optional benchmark/estimate for mainstream explicit branch style.
    We do not force full SymPy expansion for large n because that is exactly the explosion under test.
    """
    try:
        import sympy as sp  # type: ignore
    except Exception:
        return {"backend": "sympy_piecewise", "available": False, "reason": "sympy_not_available"}

    if component_name == "LTBA-0":
        x = sp.symbols("x")
        expr = sum((x + i) * (x - i) for i in range(1, n + 1))
        return {"backend": "sympy_expr", "available": True, "repr_size": len(str(expr)), "materialized_branches": 1}

    # For all guarded families, explicit binary-ish branching grows exponentially.
    # LTBA-3 has ternary local branch options, so we report the component's LTBA upper-bound separately.
    # Here we use a conservative explicit expansion estimate, not a full materialization.
    return {
        "backend": "sympy_piecewise_estimate",
        "available": True,
        "repr_size": None,
        "materialized_branches_estimate": 2 ** n,
        "note": "full explicit Piecewise materialization intentionally avoided for large n",
    }


def bdd_availability() -> Dict[str, object]:
    try:
        import dd.autoref  # type: ignore  # noqa: F401
        return {"backend": "bdd", "available": True}
    except Exception:
        return {"backend": "bdd", "available": False, "reason": "python package 'dd' not installed"}


def run(ns: argparse.Namespace) -> Dict[str, object]:
    rows: List[Dict[str, object]] = []
    bdd = bdd_availability()

    names = registry.names() if ns.components == "all" else [x.strip() for x in ns.components.split(",") if x.strip()]

    for name in names:
        component = registry.get(name)
        for n in ns.sizes:
            expr, build_s = timed(lambda c=component, n=n: c.make_family(n))
            _, rewrite_s = timed(lambda e=expr: e.rewrite_local(0, "REWRITTEN", "benchmark_locality") if e.local_branch_count else e)

            row = expr.metric_row(component.name, n, "ltba")
            row.update({
                "layer": component.layer,
                "build_seconds": build_s,
                "rewrite_one_seconds": rewrite_s,
                "rewrite_one_touched_records": 1 if expr.local_branch_count else 0,
            })
            rows.append(row)

            sym = sympy_piecewise_estimate(component.name, n)
            sym_row = {
                "family": component.name,
                "n": n,
                "layer": component.layer,
                "backend": sym.get("backend"),
                "available": sym.get("available"),
                "repr_size": sym.get("repr_size"),
                "materialized_branches_estimate": sym.get("materialized_branches_estimate", sym.get("materialized_branches")),
                "note": sym.get("note", sym.get("reason", "")),
            }
            rows.append(sym_row)

    report = {
        "benchmark": "LTBA general substrate benchmark v0",
        "claim_under_test": "one guarded-local substrate can host specialized symbolic components without eager global Piecewise expansion",
        "sizes": ns.sizes,
        "components": names,
        "bdd_status": bdd,
        "rows": rows,
    }
    return report


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sizes", default="1,2,4,8,12,16", help="comma-separated n values")
    p.add_argument("--components", default="all", help="all or comma-separated LTBA-0,...,LTBA-7")
    p.add_argument("--out", default="out_ltba_general_benchmark", help="output directory")
    ns = p.parse_args()
    ns.sizes = [int(x) for x in ns.sizes.split(",") if x.strip()]

    report = run(ns)
    out = Path(ns.out)
    out.mkdir(parents=True, exist_ok=True)

    json_path = out / "ltba_general_benchmark_report.json"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True))

    csv_path = out / "ltba_general_benchmark_rows.csv"
    fieldnames = sorted({k for row in report["rows"] for k in row})
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(report["rows"])

    print(f"wrote {json_path}")
    print(f"wrote {csv_path}")
    print(json.dumps({"rows": len(report["rows"]), "bdd_status": report["bdd_status"]}, indent=2))


if __name__ == "__main__":
    main()
PY
chmod +x "$BENCH/ltba_general_benchmark.py"

cat > "$TESTS/test_ltba_general_components.py" <<'PY'
from kernel.ltba_general import registry


def test_all_eight_ltba_components_are_registered():
    assert registry.names() == [f"LTBA-{i}" for i in range(8)]


def test_guarded_division_family_is_linear_locally_but_exponential_if_expanded():
    expr = registry.get("LTBA-1").make_family(5)
    assert expr.guard_count == 10
    assert expr.local_branch_count == 10
    assert expr.explicit_branch_upper_bound == 2 ** 10
    assert expr.rewrite_local(0, "1_REWRITTEN", "unit_test").provenance[-1].startswith("local_rewrite:0")


def test_general_components_share_same_guarded_local_interface():
    for name in registry.names():
        expr = registry.get(name).make_family(3)
        assert hasattr(expr, "branches")
        assert hasattr(expr, "provenance")
        assert isinstance(expr.representation_size, int)
        assert expr.representation_size > 0


def test_matrix_inverse_component_has_determinant_guards():
    expr = registry.get("LTBA-5").make_family(2)
    guards = {str(b.guard) for b in expr.branches}
    assert "det(A1) != 0" in guards
    assert "det(A1) == 0" in guards


def test_limits_component_preserves_regular_and_removable_limit_branches():
    expr = registry.get("LTBA-6").make_family(1)
    values = {b.value for b in expr.branches}
    assert "x + a1" in values
    assert "REMOVABLE_LIMIT:2*a1" in values
PY

cat > "$PKG/README.md" <<'MD'
# LTBA General Experimental Layer

This is an intentionally non-invasive experimental layer.

Purpose:
- test whether LTBA can become a shared guarded-local substrate
- patch in specialized components LTBA-0 through LTBA-7
- benchmark local guarded representation against explicit Piecewise-style expansion

Components:
- LTBA-0 ordinary algebra
- LTBA-1 guarded division / cancellation
- LTBA-2 radicals and absolute values
- LTBA-3 inequalities and ordering
- LTBA-4 logarithms / exponentials / trig domains
- LTBA-5 matrices / determinants / inverses
- LTBA-6 limits / removable singularities
- LTBA-7 solver branch provenance

Run:

```bash
PYTHONPATH=. pytest -q tests/conformance/test_ltba_general_components.py
PYTHONPATH=. python benchmarks/ltba_general_benchmark.py --sizes 1,2,4,8,12,16
```

Outputs:
- `out_ltba_general_benchmark/ltba_general_benchmark_report.json`
- `out_ltba_general_benchmark/ltba_general_benchmark_rows.csv`

The benchmark is not claiming LTBA beats all BDD/ADD systems. It tests the narrower claim:

> One guarded-local substrate can host multiple specialized symbolic components without eager global branch expansion.
MD

echo "LTBA general benchmark patch applied."
echo "Run: PYTHONPATH=. pytest -q tests/conformance/test_ltba_general_components.py"
echo "Run: PYTHONPATH=. python benchmarks/ltba_general_benchmark.py --sizes 1,2,4,8,12,16"

