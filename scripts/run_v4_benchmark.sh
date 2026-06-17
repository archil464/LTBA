#!/usr/bin/bash
set -euo pipefail

ROOT="${1:-.}"
PKG="$ROOT/kernel/ltba_general"
BENCH="$ROOT/benchmarks"
TESTS="$ROOT/tests/conformance"
DOCS="$ROOT/docs"

mkdir -p "$PKG" "$BENCH" "$TESTS" "$DOCS"

cat > "$BENCH/ltba_general_benchmark_v1.py" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

try:
    from kernel.ltba_general import LTBAExpr, registry
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"Cannot import kernel.ltba_general. Apply v0 first or run with PYTHONPATH=. Error: {exc}")


BRANCHING_FACTOR = {
    "LTBA-0": 1,
    "LTBA-1": 2,
    "LTBA-2": 2,
    "LTBA-3": 3,
    "LTBA-4": 2,
    "LTBA-5": 2,
    "LTBA-6": 2,
    "LTBA-7": 2,
}


def timed(fn):
    t0 = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - t0


@dataclass(frozen=True)
class BranchGroup:
    label: str
    choices: Tuple[Tuple[str, str, str], ...]  # guard, value, tag

    @property
    def branch_count(self) -> int:
        return len(self.choices)


def groups_from_expr(expr: LTBAExpr, family: str) -> List[BranchGroup]:
    """Recover independent local branch groups from the v0 generated expressions."""
    if family == "LTBA-0":
        return []
    bf = BRANCHING_FACTOR[family]
    branches = list(expr.branches)
    if len(branches) % bf != 0:
        raise ValueError(f"cannot group {family}: {len(branches)} branches not divisible by {bf}")
    groups: List[BranchGroup] = []
    for idx in range(0, len(branches), bf):
        chunk = branches[idx: idx + bf]
        gidx = idx // bf + 1
        groups.append(
            BranchGroup(
                label=f"{family}:{gidx}",
                choices=tuple((str(b.guard), b.value, b.tag) for b in chunk),
            )
        )
    return groups


def theoretical_branch_space(groups: Sequence[BranchGroup]) -> int:
    out = 1
    for g in groups:
        out *= g.branch_count
    return out


def materialize_explicit(groups: Sequence[BranchGroup], max_branches: int) -> Dict[str, object]:
    """
    Actually materialize the full Cartesian product of local branches, but only up to
    max_branches. This is the honest explicit-Piecewise-like branch expansion cost.
    """
    total = theoretical_branch_space(groups)
    if total > max_branches:
        return {
            "backend": "explicit_materialized",
            "available": False,
            "reason": f"skipped: total branches {total} > max_materialize {max_branches}",
            "actual_branch_count": None,
            "actual_repr_size": None,
            "rewrite_one_touched_records": None,
            "build_seconds": None,
            "rewrite_one_seconds": None,
        }

    def build():
        if not groups:
            return [((), "base")]
        all_choices = [g.choices for g in groups]
        rows = []
        for combo in itertools.product(*all_choices):
            guards = tuple(c[0] for c in combo)
            payload = " | ".join(c[1] for c in combo)
            rows.append((guards, payload))
        return rows

    rows, build_s = timed(build)

    # A rewrite to the first local choice touches every full branch containing that choice.
    def rewrite_one():
        if not rows or not groups:
            return 0
        first_guard = groups[0].choices[0][0]
        touched = 0
        new_rows = []
        for guards, payload in rows:
            if first_guard in guards:
                touched += 1
                new_rows.append((guards, payload + " | REWRITTEN"))
            else:
                new_rows.append((guards, payload))
        return touched

    touched, rewrite_s = timed(rewrite_one)
    repr_size = sum(sum(len(g) for g in guards) + len(payload) for guards, payload in rows)
    return {
        "backend": "explicit_materialized",
        "available": True,
        "actual_branch_count": len(rows),
        "actual_repr_size": repr_size,
        "rewrite_one_touched_records": touched,
        "build_seconds": build_s,
        "rewrite_one_seconds": rewrite_s,
        "reason": "",
    }


def bdd_backend_status() -> Dict[str, object]:
    try:
        import dd.autoref  # type: ignore  # noqa: F401
        return {"backend": "bdd", "available": True}
    except Exception as exc:
        return {"backend": "bdd", "available": False, "reason": str(exc)}


def bdd_guard_skeleton(groups: Sequence[BranchGroup], max_branches: int) -> Dict[str, object]:
    """
    BDD comparison for guard structure only.

    Important: a plain BDD does not carry algebraic payloads. If we OR all complete
    paths, the result is tautological and collapses. So this benchmark builds and
    keeps the complete path cubes to measure the guard skeleton, and separately
    reports the number of external payload records that a BDD+materialized-payload
    representation would need.
    """
    status = bdd_backend_status()
    if not status["available"]:
        return {**status, "node_count": None, "path_count": None, "payload_records_materialized": None}

    total = theoretical_branch_space(groups)
    if total > max_branches:
        return {
            "backend": "bdd_guard_skeleton",
            "available": False,
            "reason": f"skipped: total paths {total} > max_materialize {max_branches}",
            "node_count": None,
            "path_count": None,
            "payload_records_materialized": None,
            "factor_payload_records": sum(g.branch_count for g in groups),
        }

    import dd.autoref as _bdd  # type: ignore

    def build():
        bdd = _bdd.BDD()
        var_names: List[str] = []
        group_bits: List[List[str]] = []
        for gi, g in enumerate(groups):
            bits = max(1, math.ceil(math.log2(max(1, g.branch_count))))
            names = [f"g{gi}_b{bi}" for bi in range(bits)]
            var_names.extend(names)
            group_bits.append(names)
        if var_names:
            bdd.declare(*var_names)

        paths = []
        if not groups:
            return bdd, [bdd.true]

        for choices in itertools.product(*[range(g.branch_count) for g in groups]):
            node = bdd.true
            for gi, choice_idx in enumerate(choices):
                bits = group_bits[gi]
                for bi, name in enumerate(bits):
                    bit_is_one = bool((choice_idx >> bi) & 1)
                    lit = bdd.var(name)
                    if not bit_is_one:
                        lit = ~lit
                    node &= lit
            paths.append(node)
        return bdd, paths

    (bdd, paths), build_s = timed(build)
    # len(bdd) is the autoref manager's live/known node count approximation.
    node_count = len(bdd)
    return {
        "backend": "bdd_guard_skeleton",
        "available": True,
        "node_count": node_count,
        "path_count": len(paths),
        "payload_records_materialized": total,
        "factor_payload_records": sum(g.branch_count for g in groups),
        "build_seconds": build_s,
        "reason": "BDD stores guard structure only; algebraic payload is external",
    }


def make_mixed_family(n: int) -> Tuple[LTBAExpr, List[BranchGroup]]:
    """Mixed guarded expression across the major LTBA layers."""
    selected = ["LTBA-1", "LTBA-2", "LTBA-3", "LTBA-4", "LTBA-5", "LTBA-6", "LTBA-7"]
    base_parts: List[str] = []
    groups: List[BranchGroup] = []
    expr = LTBAExpr("MIXED", provenance=["LTBA-MIXED:v1"])
    for name in selected:
        sub = registry.get(name).make_family(n)
        base_parts.append(f"[{name}:{sub.base}]")
        sub_groups = groups_from_expr(sub, name)
        for g in sub_groups:
            prefixed_choices = tuple((guard, value, f"{name}:{tag}") for guard, value, tag in g.choices)
            groups.append(BranchGroup(label=f"{name}:{g.label}", choices=prefixed_choices))
            for guard, value, tag in prefixed_choices:
                expr.add_branch(guard, value, tag=tag)
    expr.base = " * ".join(base_parts)
    return expr, groups


def ltba_row(family: str, layer: str, n: int, expr: LTBAExpr, groups: Sequence[BranchGroup]) -> Dict[str, object]:
    _, rewrite_s = timed(lambda: expr.rewrite_local(0, "REWRITTEN", "v1_locality") if expr.local_branch_count else expr)
    return {
        "suite": "v1",
        "family": family,
        "layer": layer,
        "n": n,
        "backend": "ltba_local",
        "repr_size": expr.representation_size,
        "guard_count": expr.guard_count,
        "local_branch_count": expr.local_branch_count,
        "group_count": len(groups),
        "theoretical_full_branch_space": theoretical_branch_space(groups),
        "rewrite_one_touched_records": 1 if expr.local_branch_count else 0,
        "rewrite_one_seconds": rewrite_s,
        "available": True,
    }


def run(ns: argparse.Namespace) -> Dict[str, object]:
    rows: List[Dict[str, object]] = []
    component_names = registry.names() if ns.components == "all" else [x.strip() for x in ns.components.split(",") if x.strip()]

    for name in component_names:
        component = registry.get(name)
        for n in ns.sizes:
            expr, build_s = timed(lambda c=component, n=n: c.make_family(n))
            groups = groups_from_expr(expr, name)

            row = ltba_row(name, component.layer, n, expr, groups)
            row["build_seconds"] = build_s
            rows.append(row)

            explicit = materialize_explicit(groups, ns.max_materialize)
            rows.append({
                "suite": "v1",
                "family": name,
                "layer": component.layer,
                "n": n,
                **explicit,
                "theoretical_full_branch_space": theoretical_branch_space(groups),
            })

            bdd = bdd_guard_skeleton(groups, ns.max_materialize)
            rows.append({
                "suite": "v1",
                "family": name,
                "layer": component.layer,
                "n": n,
                **bdd,
                "theoretical_full_branch_space": theoretical_branch_space(groups),
            })

    if ns.include_mixed:
        for n in ns.mixed_sizes:
            expr, groups = make_mixed_family(n)
            rows.append(ltba_row("LTBA-MIXED", "mixed_all_guarded_layers", n, expr, groups))
            explicit = materialize_explicit(groups, ns.max_materialize)
            rows.append({
                "suite": "v1",
                "family": "LTBA-MIXED",
                "layer": "mixed_all_guarded_layers",
                "n": n,
                **explicit,
                "theoretical_full_branch_space": theoretical_branch_space(groups),
            })
            bdd = bdd_guard_skeleton(groups, ns.max_materialize)
            rows.append({
                "suite": "v1",
                "family": "LTBA-MIXED",
                "layer": "mixed_all_guarded_layers",
                "n": n,
                **bdd,
                "theoretical_full_branch_space": theoretical_branch_space(groups),
            })

    return {
        "benchmark": "LTBA general substrate benchmark v1",
        "claim_under_test": "guarded-local normal form vs actual explicit materialization and BDD guard skeleton",
        "important_note": "BDD rows measure guard skeleton only; algebraic payload records are reported separately because plain BDDs do not store symbolic algebraic payloads.",
        "sizes": ns.sizes,
        "mixed_sizes": ns.mixed_sizes if ns.include_mixed else [],
        "max_materialize": ns.max_materialize,
        "components": component_names,
        "bdd_status": bdd_backend_status(),
        "rows": rows,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--sizes", default="1,2,4,8,12,16", help="comma-separated component n values")
    p.add_argument("--mixed-sizes", default="1,2,3", help="comma-separated mixed-family n values")
    p.add_argument("--components", default="all", help="all or comma-separated LTBA-0,...,LTBA-7")
    p.add_argument("--max-materialize", type=int, default=4096, help="max full explicit branches to actually materialize")
    p.add_argument("--include-mixed", action="store_true", default=True)
    p.add_argument("--out", default="out_ltba_general_benchmark_v1")
    ns = p.parse_args()
    ns.sizes = [int(x) for x in ns.sizes.split(",") if x.strip()]
    ns.mixed_sizes = [int(x) for x in ns.mixed_sizes.split(",") if x.strip()]

    report = run(ns)
    out = Path(ns.out)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "ltba_general_benchmark_v1_report.json"
    csv_path = out / "ltba_general_benchmark_v1_rows.csv"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True))

    fieldnames = sorted({k for row in report["rows"] for k in row})
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(report["rows"])

    print(f"wrote {json_path}")
    print(f"wrote {csv_path}")
    print(json.dumps({
        "rows": len(report["rows"]),
        "bdd_status": report["bdd_status"],
        "max_materialize": report["max_materialize"],
    }, indent=2))


if __name__ == "__main__":
    main()
PY
chmod +x "$BENCH/ltba_general_benchmark_v1.py"

cat > "$TESTS/test_ltba_general_benchmark_v1.py" <<'PY'
from benchmarks.ltba_general_benchmark_v1 import (
    groups_from_expr,
    make_mixed_family,
    materialize_explicit,
    theoretical_branch_space,
)
from kernel.ltba_general import registry


def test_v1_actual_materialization_counts_small_guarded_division():
    expr = registry.get("LTBA-1").make_family(3)
    groups = groups_from_expr(expr, "LTBA-1")
    assert theoretical_branch_space(groups) == 8
    info = materialize_explicit(groups, max_branches=16)
    assert info["available"] is True
    assert info["actual_branch_count"] == 8
    assert info["rewrite_one_touched_records"] == 4


def test_v1_ternary_inequality_branch_space_is_not_forced_binary():
    expr = registry.get("LTBA-3").make_family(4)
    groups = groups_from_expr(expr, "LTBA-3")
    assert len(groups) == 4
    assert theoretical_branch_space(groups) == 3 ** 4


def test_v1_materialization_skip_is_explicit_when_too_large():
    expr = registry.get("LTBA-2").make_family(10)
    groups = groups_from_expr(expr, "LTBA-2")
    info = materialize_explicit(groups, max_branches=128)
    assert info["available"] is False
    assert "skipped" in info["reason"]


def test_v1_mixed_family_combines_all_guarded_layers():
    expr, groups = make_mixed_family(1)
    assert expr.local_branch_count > 0
    labels = {g.label.split(":")[0] for g in groups}
    assert labels == {"LTBA-1", "LTBA-2", "LTBA-3", "LTBA-4", "LTBA-5", "LTBA-6", "LTBA-7"}
    # n=1 mixed branch space = 2*2*3*2*2*2*2 = 192
    assert theoretical_branch_space(groups) == 192
PY

cat > "$DOCS/LTBA_GENERAL_BENCHMARK_V1.md" <<'MD'
# LTBA General Benchmark v1

This benchmark upgrades v0 in three ways:

1. It separates theoretical branch space from actually materialized explicit branches.
2. It adds a BDD guard-skeleton comparison while clearly reporting that algebraic payload is external to a plain BDD.
3. It adds a mixed-layer family combining LTBA-1 through LTBA-7.

Run:

```bash
PYTHONPATH=. pytest -q tests/conformance/test_ltba_general_benchmark_v1.py
PYTHONPATH=. python benchmarks/ltba_general_benchmark_v1.py --sizes 1,2,4,8,12,16 --mixed-sizes 1,2,3 --max-materialize 4096
```

Outputs:

- `out_ltba_general_benchmark_v1/ltba_general_benchmark_v1_report.json`
- `out_ltba_general_benchmark_v1/ltba_general_benchmark_v1_rows.csv`

Interpretation:

- `ltba_local` measures the guarded-local representation.
- `explicit_materialized` actually expands the Cartesian product of local branches until `--max-materialize` is exceeded.
- `bdd_guard_skeleton` measures guard-decision structure only; it also reports `payload_records_materialized` and `factor_payload_records` to distinguish BDD+materialized-payload from BDD+factor-payload models.

The intended claim is narrow:

> LTBA preserves local rewrite cost while explicit materialization grows with the full branch product.

Do not claim from this benchmark alone that LTBA universally beats optimized BDD/ADD systems.
MD

echo "LTBA general benchmark v1 patch applied."
echo "Run: PYTHONPATH=. pytest -q tests/conformance/test_ltba_general_benchmark_v1.py"
echo "Run: PYTHONPATH=. python benchmarks/ltba_general_benchmark_v1.py --sizes 1,2,4,8,12,16 --mixed-sizes 1,2,3 --max-materialize 4096"
