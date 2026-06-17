"""Helpers to materialize LTBA local branches into an explicit product.

Warning: materialization enumerates the Cartesian product of independent
local branch groups and can grow exponentially. Use only for small examples
or tests.
"""
from __future__ import annotations

import itertools
from typing import Dict, List, Tuple

from .core import LTBAExpr, LocalBranchGroup, LocalBranch


def materialize_explicit(expr: LTBAExpr, max_branches: int = 1024) -> Dict[str, object]:
    """Materialize local branch groups into explicit global cases.

    Returns a dict with keys:
    - available: bool
    - actual_branch_count: int (if available)
    - cases: list of tuples (combined_guard, combined_value, selected_tags)

    Raises ValueError if the Cartesian product exceeds `max_branches`.
    """
    groups = list(expr.branch_groups)
    if not groups:
        return {"available": True, "actual_branch_count": 1, "cases": [("", expr.base, [])]}

    arities = [max(1, len(g.branches)) for g in groups]
    total = 1
    for a in arities:
        total *= a
    if total > max_branches:
        raise ValueError(f"materialization would produce {total} cases > max_branches {max_branches}")

    # Build list of choices per group: each choice is (guard, value, tag, group_id)
    choices_per_group = []
    for g in groups:
        choices = []
        for b in g.branches:
            choices.append((str(b.guard), b.value, b.tag, g.group_id))
        # If a group has zero branches, add a neutral empty choice
        if not choices:
            choices.append(("", "", "", g.group_id))
        choices_per_group.append(choices)

    cases = []
    for combo in itertools.product(*choices_per_group):
        guards = [c[0] for c in combo if c[0]]
        values = [c[1] for c in combo if c[1]]
        tags = [(c[3], c[2]) for c in combo if c[2]]
        combined_guard = " and ".join(guards)
        combined_value = expr.base
        if values:
            combined_value = expr.base + " | " + " | ".join(values)
        cases.append((combined_guard, combined_value, tags))

    return {"available": True, "actual_branch_count": len(cases), "cases": cases}
