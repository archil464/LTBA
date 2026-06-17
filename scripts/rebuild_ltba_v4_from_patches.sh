#!/usr/bin/bash
set -euo pipefail

ROOT="${1:-.}"
PKG="$ROOT/kernel/ltba_general"
BENCH="$ROOT/benchmarks"
TESTS="$ROOT/tests/conformance"

mkdir -p "$PKG" "$BENCH" "$TESTS"

cat > "$PKG/__init__.py" <<'PY'
from .core import Guard, LocalBranch, LTBAExpr, LTBAComponent, registry
from .components import install_default_components

install_default_components()

__all__ = [
    "Guard",
    "LocalBranch",
    "LTBAExpr",
    "LTBAComponent",
    "registry",
    "install_default_components",
]
PY

cat > "$PKG/core.py" <<'PY'
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True, order=True)
class Guard:
    """Atomic guard used by the experimental LTBA general layer."""
    text: str

    def __str__(self) -> str:
        return self.text


@dataclass(frozen=True)
class LocalBranch:
    """A local branch attached to one algebraic term/factor, not globally expanded."""
    guard: Guard
    value: str
    tag: str = ""


@dataclass
class LTBAExpr:
    """
    Experimental general guarded expression.

    Design goal:
    - keep ordinary algebra text separate from local branch records
    - estimate explicit Piecewise branch explosion without eagerly materializing it
    - support O(1)-style local replacement of one branch/factor record
    """
    base: str
    branches: List[LocalBranch] = field(default_factory=list)
    provenance: List[str] = field(default_factory=list)

    def add_branch(self, guard: str, value: str, tag: str = "") -> "LTBAExpr":
        self.branches.append(LocalBranch(Guard(guard), value, tag))
        return self

    @property
    def guard_count(self) -> int:
        return len({b.guard for b in self.branches})

    @property
    def local_branch_count(self) -> int:
        return len(self.branches)

    @property
    def explicit_branch_upper_bound(self) -> int:
        # Binary independent guard upper bound. Conservative by design.
        return 2 ** self.guard_count

    @property
    def representation_size(self) -> int:
        # Stable coarse metric, not Python object memory.
        return len(self.base) + sum(len(str(b.guard)) + len(b.value) + len(b.tag) for b in self.branches)

    def rewrite_local(self, index: int, new_value: str, reason: str) -> "LTBAExpr":
        """Return a new LTBAExpr with exactly one local branch value changed."""
        if index < 0 or index >= len(self.branches):
            raise IndexError("branch index out of range")
        new = LTBAExpr(self.base, list(self.branches), list(self.provenance))
        old = new.branches[index]
        new.branches[index] = LocalBranch(old.guard, new_value, old.tag)
        new.provenance.append(f"local_rewrite:{index}:{reason}")
        return new

    def metric_row(self, family: str, n: int, backend: str = "ltba") -> Dict[str, object]:
        return {
            "family": family,
            "n": n,
            "backend": backend,
            "repr_size": self.representation_size,
            "guard_count": self.guard_count,
            "local_branch_count": self.local_branch_count,
            "explicit_branch_upper_bound": self.explicit_branch_upper_bound,
            "provenance_len": len(self.provenance),
        }


@dataclass(frozen=True)
class LTBAComponent:
    name: str
    layer: str
    description: str
    make_family: Callable[[int], LTBAExpr]


class ComponentRegistry:
    def __init__(self) -> None:
        self._items: Dict[str, LTBAComponent] = {}

    def register(self, component: LTBAComponent) -> None:
        self._items[component.name] = component

    def get(self, name: str) -> LTBAComponent:
        return self._items[name]

    def names(self) -> List[str]:
        return sorted(self._items)

    def values(self) -> Iterable[LTBAComponent]:
        return [self._items[k] for k in self.names()]


registry = ComponentRegistry()
PY

cat > "$PKG/components.py" <<'PY'
from __future__ import annotations

from .core import LTBAComponent, LTBAExpr, registry


def ordinary_algebra_family(n: int) -> LTBAExpr:
    # LTBA-0: no special guards; ordinary algebra should have no branch overhead.
    terms = [f"(x{i}+1)*(x{i}-1)" for i in range(1, n + 1)]
    return LTBAExpr(" + ".join(terms), provenance=["LTBA-0:ordinary_algebra"])


def guarded_division_family(n: int) -> LTBAExpr:
    # LTBA-1: x_i/x_i as local guarded cancellation.
    e = LTBAExpr(" * ".join([f"(x{i}/x{i})" for i in range(1, n + 1)]), provenance=["LTBA-1:guarded_division"])
    for i in range(1, n + 1):
        e.add_branch(f"x{i} != 0", "1", tag=f"cancel:x{i}/x{i}")
        e.add_branch(f"x{i} == 0", "0", tag=f"singular:x{i}/x{i}")
    return e


def radicals_abs_family(n: int) -> LTBAExpr:
    # LTBA-2: sqrt(x_i^2) -> abs(x_i), with sign split available lazily.
    e = LTBAExpr(" + ".join([f"sqrt(x{i}^2)" for i in range(1, n + 1)]), provenance=["LTBA-2:radicals_abs"])
    for i in range(1, n + 1):
        e.add_branch(f"x{i} >= 0", f"x{i}", tag=f"sqrt_square_pos:x{i}")
        e.add_branch(f"x{i} < 0", f"-x{i}", tag=f"sqrt_square_neg:x{i}")
    return e


def inequalities_order_family(n: int) -> LTBAExpr:
    # LTBA-3: multiplying inequality by symbolic a_i requires sign branch.
    e = LTBAExpr(" ; ".join([f"a{i}*x < a{i}*b" for i in range(1, n + 1)]), provenance=["LTBA-3:inequalities_ordering"])
    for i in range(1, n + 1):
        e.add_branch(f"a{i} > 0", "x < b", tag=f"ineq_keep:{i}")
        e.add_branch(f"a{i} < 0", "x > b", tag=f"ineq_flip:{i}")
        e.add_branch(f"a{i} == 0", "0 < 0", tag=f"ineq_degenerate:{i}")
    return e


def logs_exp_trig_domains_family(n: int) -> LTBAExpr:
    # LTBA-4: log product expansion under positive domain guards.
    e = LTBAExpr(" + ".join([f"log(x{i}*y{i})" for i in range(1, n + 1)]), provenance=["LTBA-4:transcendental_domains"])
    for i in range(1, n + 1):
        e.add_branch(f"x{i} > 0 and y{i} > 0", f"log(x{i}) + log(y{i})", tag=f"log_product_expand:{i}")
        e.add_branch(f"not(x{i} > 0 and y{i} > 0)", f"BLOCKED:log(x{i}*y{i})", tag=f"log_product_blocked:{i}")
    return e


def matrix_inverse_family(n: int) -> LTBAExpr:
    # LTBA-5: inverse exists iff determinant is nonzero.
    e = LTBAExpr(" ; ".join([f"inv(A{i})" for i in range(1, n + 1)]), provenance=["LTBA-5:matrix_inverse"])
    for i in range(1, n + 1):
        e.add_branch(f"det(A{i}) != 0", f"A{i}^-1", tag=f"inverse_valid:{i}")
        e.add_branch(f"det(A{i}) == 0", "BLOCKED:singular_matrix", tag=f"inverse_blocked:{i}")
    return e


def limits_removable_family(n: int) -> LTBAExpr:
    # LTBA-6: removable singularity split: expression undefined at point, limit value preserved.
    e = LTBAExpr(" ; ".join([f"(x^2-a{i}^2)/(x-a{i})" for i in range(1, n + 1)]), provenance=["LTBA-6:limits_removable"])
    for i in range(1, n + 1):
        e.add_branch(f"x != a{i}", f"x + a{i}", tag=f"cancel_valid:{i}")
        e.add_branch(f"x == a{i}", f"REMOVABLE_LIMIT:2*a{i}", tag=f"limit_value:{i}")
    return e


def solver_provenance_family(n: int) -> LTBAExpr:
    # LTBA-7: solving branches carry ordered provenance, not just final answer.
    e = LTBAExpr(" ; ".join([f"x/(x-a{i}) = 1" for i in range(1, n + 1)]), provenance=["LTBA-7:solver_branch_provenance"])
    for i in range(1, n + 1):
        e.add_branch(f"x != a{i}", f"UNSAT_AFTER_CROSS_MULTIPLY:{i}", tag="solve_regular_branch")
        e.add_branch(f"x == a{i}", f"SINGULAR_BRANCH:{i}", tag="solve_singular_branch")
    return e


def install_default_components() -> None:
    items = [
        LTBAComponent("LTBA-0", "ordinary_algebra", "ordinary algebra, no guard overhead", ordinary_algebra_family),
        LTBAComponent("LTBA-1", "guarded_division", "division/cancellation guards", guarded_division_family),
        LTBAComponent("LTBA-2", "radicals_abs", "sqrt/abs sign split", radicals_abs_family),
        LTBAComponent("LTBA-3", "inequalities_ordering", "sign-sensitive inequality rewrites", inequalities_order_family),
        LTBAComponent("LTBA-4", "transcendental_domains", "log/exp/trig domain guarded rewrites", logs_exp_trig_domains_family),
        LTBAComponent("LTBA-5", "matrix_inverse", "determinant/inverse guards", matrix_inverse_family),
        LTBAComponent("LTBA-6", "limits_removable", "removable singularity branches", limits_removable_family),
        LTBAComponent("LTBA-7", "solver_provenance", "solver branch provenance", solver_provenance_family),
    ]
    for item in items:
        registry.register(item)
PY

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
