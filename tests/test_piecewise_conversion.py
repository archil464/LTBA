from ltba import LTBAExpr
from ltba.piecewise_conversion import materialize_explicit


def test_small_materialization():
    e = LTBAExpr("base")
    e.add_branch("g1", "a1", "t1")
    e.add_branch("g2", "a2", "t2")
    info = materialize_explicit(e, group_size=1, max_branches=16)
    assert info["available"] is True
    assert info["actual_branch_count"] == 2 * 2
