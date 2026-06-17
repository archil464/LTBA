from ltba import LTBAExpr, LocalBranch, Guard
from ltba.piecewise_conversion import materialize_explicit


def test_two_groups_two_branches_materialize_to_four_cases():
    e = LTBAExpr("base")
    # group 1
    e = e.add_branch_group("g1", [LocalBranch(Guard("a"), "A"), LocalBranch(Guard("not a"), "B")])
    # group 2
    e = e.add_branch_group("g2", [LocalBranch(Guard("b"), "C"), LocalBranch(Guard("not b"), "D")])
    info = materialize_explicit(e, max_branches=16)
    assert info["available"] is True
    assert info["actual_branch_count"] == 4


def test_materialize_respects_max_branches():
    e = LTBAExpr("base")
    e = e.add_branch_group("g1", [LocalBranch(Guard("a1"), "A1"), LocalBranch(Guard("a2"), "A2")])
    e = e.add_branch_group("g2", [LocalBranch(Guard("b1"), "B1"), LocalBranch(Guard("b2"), "B2")])
    try:
        _ = materialize_explicit(e, max_branches=2)
        assert False, "Expected ValueError due to max_branches exceeded"
    except ValueError:
        pass
