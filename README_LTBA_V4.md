#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
TESTS="$ROOT/tests/conformance"
mkdir -p "$TESTS"

cat > "$TESTS/test_ltba_general_imports.py" <<'PY'
def test_ltba_general_package_exports_core_symbols():
    from kernel.ltba_general import (
        Guard,
        LocalBranch,
        LTBAComponent,
        LTBAExpr,
        install_default_components,
        registry,
    )

    assert Guard is not None
    assert LocalBranch is not None
    assert LTBAExpr is not None
    assert LTBAComponent is not None
    assert install_default_components is not None
    assert registry.names() == [f"LTBA-{i}" for i in range(8)]
PY

cat > "$TESTS/test_ltba_general_components.py" <<'PY'
from kernel.ltba_general import registry


def test_all_eight_ltba_components_are_registered():
    assert registry.names() == [f"LTBA-{i}" for i in range(8)]


def test_guarded_division_family_is_linear_locally_but_exponential_if_expanded():
    expr = registry.get("LTBA-1").make_family(5)
    assert expr.guard_count == 10
    assert expr.local_branch_count == 10
    assert expr.explicit_branch_upper_bound == 2 ** 10

    rewritten = expr.rewrite_local(0, "1_REWRITTEN", "unit_test")
    assert rewritten.provenance[-1].startswith("local_rewrite:0")
    assert rewritten.branches[0].value == "1_REWRITTEN"
    assert rewritten.branches[1:] == expr.branches[1:]


def test_general_components_share_same_guarded_local_interface():
    for name in registry.names():
        expr = registry.get(name).make_family(3)
        assert hasattr(expr, "branches")
        assert hasattr(expr, "provenance")
        assert isinstance(expr.representation_size, int)
        assert expr.representation_size > 0
        assert isinstance(expr.guard_count, int)
        assert isinstance(expr.local_branch_count, int)


def test_ordinary_algebra_component_has_no_guard_overhead():
    expr = registry.get("LTBA-0").make_family(4)
    assert expr.guard_count == 0
    assert expr.local_branch_count == 0
    assert expr.explicit_branch_upper_bound == 1


def test_radicals_abs_component_has_sign_split_guards():
    expr = registry.get("LTBA-2").make_family(2)
    guards = {str(b.guard) for b in expr.branches}
    values = {b.value for b in expr.branches}
    assert "x1 >= 0" in guards
    assert "x1 < 0" in guards
    assert "x1" in values
    assert "-x1" in values


def test_inequality_component_has_ternary_sign_split():
    expr = registry.get("LTBA-3").make_family(2)
    guards = {str(b.guard) for b in expr.branches}
    values = {b.value for b in expr.branches}
    assert "a1 > 0" in guards
    assert "a1 < 0" in guards
    assert "a1 == 0" in guards
    assert "x < b" in values
    assert "x > b" in values
    assert "0 < 0" in values


def test_transcendental_component_has_domain_guard_and_blocked_branch():
    expr = registry.get("LTBA-4").make_family(1)
    guards = {str(b.guard) for b in expr.branches}
    values = {b.value for b in expr.branches}
    assert "x1 > 0 and y1 > 0" in guards
    assert "not(x1 > 0 and y1 > 0)" in guards
    assert "log(x1) + log(y1)" in values
    assert "BLOCKED:log(x1*y1)" in values


def test_matrix_inverse_component_has_determinant_guards():
    expr = registry.get("LTBA-5").make_family(2)
    guards = {str(b.guard) for b in expr.branches}
    values = {b.value for b in expr.branches}
    assert "det(A1) != 0" in guards
    assert "det(A1) == 0" in guards
    assert "A1^-1" in values
    assert "BLOCKED:singular_matrix" in values


def test_limits_component_preserves_regular_and_removable_limit_branches():
    expr = registry.get("LTBA-6").make_family(1)
    values = {b.value for b in expr.branches}
    assert "x + a1" in values
    assert "REMOVABLE_LIMIT:2*a1" in values


def test_solver_provenance_component_keeps_regular_and_singular_solver_branches():
    expr = registry.get("LTBA-7").make_family(1)
    values = {b.value for b in expr.branches}
    tags = {b.tag for b in expr.branches}
    assert "UNSAT_AFTER_CROSS_MULTIPLY:1" in values
    assert "SINGULAR_BRANCH:1" in values
    assert "solve_regular_branch" in tags
    assert "solve_singular_branch" in tags
PY

cat > "$TESTS/test_ltba_general_benchmark_v1.py" <<'PY'
from benchmarks.ltba_general_benchmark_v1 import (
    bdd_guard_skeleton,
    groups_from_expr,
    make_mixed_family,
    materialize_explicit,
    theoretical_branch_space,
)
from kernel.ltba_general import registry


def test_v1_actual_materialization_counts_small_guarded_division():
    expr = registry.get("LTBA-1").make_family(3)
    groups = groups_from_expr(expr, "LTBA-1")
    assert len(groups) == 3
    assert theoretical_branch_space(groups) == 8

    info = materialize_explicit(groups, max_branches=16)
    assert info["available"] is True
    assert info["actual_branch_count"] == 8
    # Rewriting one local choice touches half the explicit product branches.
    assert info["rewrite_one_touched_records"] == 4


def test_v1_radical_family_materializes_binary_sign_product():
    expr = registry.get("LTBA-2").make_family(4)
    groups = groups_from_expr(expr, "LTBA-2")
    assert len(groups) == 4
    assert theoretical_branch_space(groups) == 16

    info = materialize_explicit(groups, max_branches=16)
    assert info["available"] is True
    assert info["actual_branch_count"] == 16
    assert info["rewrite_one_touched_records"] == 8


def test_v1_ternary_inequality_branch_space_is_not_forced_binary():
    expr = registry.get("LTBA-3").make_family(4)
    groups = groups_from_expr(expr, "LTBA-3")
    assert len(groups) == 4
    assert [g.branch_count for g in groups] == [3, 3, 3, 3]
    assert theoretical_branch_space(groups) == 3 ** 4


def test_v1_materialization_skip_is_explicit_when_too_large():
    expr = registry.get("LTBA-2").make_family(10)
    groups = groups_from_expr(expr, "LTBA-2")
    info = materialize_explicit(groups, max_branches=128)
    assert info["available"] is False
    assert "skipped" in info["reason"]
    assert "1024" in info["reason"]


def test_v1_mixed_family_combines_all_guarded_layers():
    expr, groups = make_mixed_family(1)
    assert expr.local_branch_count > 0
    labels = {g.label.split(":")[0] for g in groups}
    assert labels == {"LTBA-1", "LTBA-2", "LTBA-3", "LTBA-4", "LTBA-5", "LTBA-6", "LTBA-7"}
    # n=1 mixed branch space = 2*2*3*2*2*2*2 = 192
    assert theoretical_branch_space(groups) == 192


def test_v1_mixed_family_n2_is_large_enough_to_skip_with_default_cap():
    _expr, groups = make_mixed_family(2)
    assert theoretical_branch_space(groups) == 192 ** 2
    info = materialize_explicit(groups, max_branches=4096)
    assert info["available"] is False
    assert "skipped" in info["reason"]


def test_v1_bdd_guard_skeleton_reports_payload_distinction_for_small_case():
    expr = registry.get("LTBA-1").make_family(2)
    groups = groups_from_expr(expr, "LTBA-1")
    info = bdd_guard_skeleton(groups, max_branches=16)

    # BDD package may or may not be installed locally. If unavailable, the benchmark
    # must report that cleanly instead of failing import-time.
    assert "available" in info
    if info["available"]:
        assert info["backend"] == "bdd_guard_skeleton"
        assert info["path_count"] == 4
        assert info["payload_records_materialized"] == 4
        assert info["factor_payload_records"] == 4
        assert info["node_count"] is not None
    else:
        assert "reason" in info
PY

echo "Regenerated LTBA general test cases under $TESTS"
echo "Run: PYTHONPATH=. pytest -q tests/conformance/test_ltba_general_imports.py tests/conformance/test_ltba_general_components.py tests/conformance/test_ltba_general_benchmark_v1.py"
