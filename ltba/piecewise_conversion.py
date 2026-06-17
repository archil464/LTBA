"""Helpers to materialize LTBA local branches into an explicit product.

Warning: materialization enumerates the Cartesian product of independent
local branch groups and can grow exponentially. Use only for small examples
or tests.
"""
from __future__ import annotations

import itertools
from typing import Dict, List, Tuple

from .core import LTBAExpr, LocalBranch


def materialize_explicit(expr: LTBAExpr, group_size: int = 2, max_branches: int = 1024) -> Dict[str, object]:
    """Materialize local branches into explicit branches.

    This naive implementation groups branches into fixed-size groups of
    `group_size` sequential records. It then computes the Cartesian product of
    the groups' choices. The `group_size` parameter is a simplification for
    this prototype; real grouping logic should be provided by components.
    """
    if not expr.branches:
        return {"available": True, "branches": [((), expr.base)], "actual_branch_count": 1}

    groups: List[List[Tuple[str, str, str]]] = []
    b = list(expr.branches)
    for i in range(0, len(b), group_size):
        chunk = b[i : i + group_size]
        groups.append([(str(bb.guard), bb.value, bb.tag) for bb in chunk])

    total = 1
    for g in groups:
        total *= len(g)
    if total > max_branches:
        return {"available": False, "reason": f"skipped: total {total} > max_branches {max_branches}", "actual_branch_count": None}

    rows = []
    for combo in itertools.product(*groups):
        guards = tuple(c[0] for c in combo)
        payload = " | ".join(c[1] for c in combo)
        rows.append((guards, payload))

    return {"available": True, "actual_branch_count": len(rows), "branches": rows}
