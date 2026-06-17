"""Demo components for the LTBA prototype.

These are simple, deterministic families used by benchmarks and tests. They
illustrate how local branches are attached to algebraic payloads.
"""
from __future__ import annotations

from .core import LTBAComponent, LTBAExpr, registry


def ordinary_algebra_family(n: int) -> LTBAExpr:
    terms = [f"(x{i}+1)*(x{i}-1)" for i in range(1, n + 1)]
    return LTBAExpr(" + ".join(terms), provenance=["LTBA-0:ordinary_algebra"])


def guarded_division_family(n: int) -> LTBAExpr:
    e = LTBAExpr(" * ".join([f"(x{i}/x{i})" for i in range(1, n + 1)]), provenance=["LTBA-1:guarded_division"])
    for i in range(1, n + 1):
        e.add_branch(f"x{i} != 0", "1", tag=f"cancel:x{i}/x{i}")
        e.add_branch(f"x{i} == 0", "0", tag=f"singular:x{i}/x{i}")
    return e


def radicals_abs_family(n: int) -> LTBAExpr:
    e = LTBAExpr(" + ".join([f"sqrt(x{i}^2)" for i in range(1, n + 1)]), provenance=["LTBA-2:radicals_abs"])
    for i in range(1, n + 1):
        e.add_branch(f"x{i} >= 0", f"x{i}", tag=f"sqrt_square_pos:x{i}")
        e.add_branch(f"x{i} < 0", f"-x{i}", tag=f"sqrt_square_neg:x{i}")
    return e


def install_default_components() -> None:
    items = [
        LTBAComponent("LTBA-0", "ordinary_algebra", "ordinary algebra, no guard overhead", ordinary_algebra_family),
        LTBAComponent("LTBA-1", "guarded_division", "division/cancellation guards", guarded_division_family),
        LTBAComponent("LTBA-2", "radicals_abs", "sqrt/abs sign split", radicals_abs_family),
    ]
    for item in items:
        registry.register(item)
