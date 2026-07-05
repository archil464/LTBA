from ltba import Guard, LocalBranch, LTBAExpr, LTBAComponent, registry
from ltba.piecewise_conversion import materialize_explicit
from hypothesis import given
from hypothesis import strategies as st


def test_basic_construction_and_metrics():
    e = LTBAExpr("x")
    e = e.add_branch_group("g1", [LocalBranch(Guard("g1"), "v1", "t1")])
    e = e.add_branch_group("g2", [LocalBranch(Guard("g2"), "v2", "t2")])
    assert e.local_branch_count == 2
    assert e.guard_count == 2
    assert e.representation_size > 0


def test_registry_and_components():
    names = registry.names()
    assert isinstance(names, list)
    # expect default demo components to be installed
    assert any(n.startswith("LTBA-") for n in names)


def _build_expr_from_arities(arities):
    e = LTBAExpr("base")
    for gi, arity in enumerate(arities):
        branches = []
        for bi in range(arity):
            branches.append(LocalBranch(Guard(f"g{gi}_b{bi}"), f"v{gi}_{bi}", f"t{gi}_{bi}"))
        e = e.add_branch_group(f"g{gi}", branches)
    return e


@given(st.lists(st.integers(min_value=1, max_value=4), min_size=1, max_size=6))
def test_explicit_upper_bound_matches_materialized_count(arities):
    e = _build_expr_from_arities(arities)

    expected = 1
    for arity in arities:
        expected *= arity

    assert e.explicit_branch_upper_bound == expected

    info = materialize_explicit(e, max_branches=max(1, expected))
    assert info["actual_branch_count"] == expected


@given(
    st.lists(st.integers(min_value=1, max_value=4), min_size=1, max_size=6),
    st.text(min_size=1, max_size=16),
)
def test_rewrite_local_only_touches_target_group(arities, rewritten_value):
    e = _build_expr_from_arities(arities)
    target = 0

    rewritten = e.rewrite_local(target, rewritten_value, "property-test")

    for gi, (before_group, after_group) in enumerate(zip(e.branch_groups, rewritten.branch_groups)):
        if gi == target:
            assert after_group.branches[0].value == rewritten_value
            assert after_group.group_id == before_group.group_id
            assert after_group.description == before_group.description
            assert after_group.branches[1:] == before_group.branches[1:]
        else:
            assert after_group == before_group

    assert len(rewritten.provenance) == len(e.provenance) + 1
    assert rewritten.provenance[-1].startswith("local_rewrite_group:0:")
