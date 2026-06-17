from ltba import Guard, LocalBranch, LTBAExpr, LTBAComponent, registry


def test_basic_construction_and_metrics():
    e = LTBAExpr("x")
    e.add_branch("g1", "v1", "t1")
    e.add_branch("g2", "v2", "t2")
    assert e.local_branch_count == 2
    assert e.guard_count == 2
    assert e.representation_size > 0


def test_registry_and_components():
    names = registry.names()
    assert isinstance(names, list)
    # expect default demo components to be installed
    assert any(n.startswith("LTBA-") for n in names)
