import pytest
from hypothesis import given, strategies as st

from ltba import Guard, LocalBranch, LocalBranchGroup, LTBAExpr, registry
from ltba.persistent import BranchTree
from ltba.piecewise_conversion import materialize_explicit


@given(st.lists(st.integers(), max_size=100), st.integers())
def test_tree_sequence_and_replacement_match_tuple(values, replacement):
    original = tuple(values)
    tree = BranchTree.from_groups(values)
    assert tree == original
    assert original == tree
    assert tree[::-2] == original[::-2]
    if values:
        for index in (0, len(values) // 2, len(values) - 1):
            changed = tree.set(index, replacement)
            expected = list(values)
            expected[index] = replacement
            assert changed == tuple(expected)
            assert tree == original
        assert tree[-1] == original[-1]
    assert tree.append(replacement) == original + (replacement,)
    for index in (-len(values) - 1, len(values), 0.5):
        with pytest.raises((IndexError, TypeError)):
            tree[index]


@pytest.mark.parametrize("component", ("LTBA-0", "LTBA-1", "LTBA-2"))
def test_public_operations_preserve_records_and_history(component):
    original = registry.get(component).make_family(5)
    flat = original.with_storage("flat")
    tree = original.with_storage("tree")
    assert tree.metric_row(component, 5) == flat.metric_row(component, 5)
    assert materialize_explicit(tree) == materialize_explicit(flat)
    for index in range(len(original.branch_groups)):
        flat = flat.rewrite_local(index, "x + 7", "test")
        tree = tree.rewrite_local(index, "x + 7", "test")
        assert tuple(tree.branch_groups) == flat.branch_groups
        assert tree.provenance == flat.provenance
        assert isinstance(tree.branch_groups, BranchTree)
    tree = tree.add_branch("extra", "42", "test")
    flat = flat.add_branch("extra", "42", "test")
    assert tree.branch_groups == flat.branch_groups
    assert tree.provenance == flat.provenance
    assert original == registry.get(component).make_family(5)


def test_empty_group_and_nonempty_description_are_preserved():
    groups = (LocalBranchGroup("empty", (), "empty description"),
              LocalBranchGroup("full", (LocalBranch(Guard("g"), "v", "tag"),), "description"))
    original = LTBAExpr("base", groups, ["origin"])
    tree = original.with_storage("tree")
    assert tree.rewrite_local(0, "new", "ignored").provenance == ["origin"]
    changed = tree.rewrite_local(1, "new", "change")
    assert changed.branch_groups[1].description == "description"
    assert original.branch_groups[1].branches[0].value == "v"
