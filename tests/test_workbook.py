import pytest
from ltba.workbook import Workbook


def test_update_matches_full_rebuild_and_preserves_snapshot():
    formulas = {'a': '(x^2-1)/(x-1)', 'b': '1/(a-2)', 'c': 'b/b', 'other': 'y/y'}
    original = Workbook.build(formulas)
    for source in ('x/x', 'x/0', '(x^2-4)/(x-2)'):
        changed = original.update('a', source)
        assert changed.to_dict() == Workbook.build({**formulas, 'a': source}).to_dict()
        assert changed.recomputed == ('a', 'b', 'c')
        assert changed.compiled['other'] is original.compiled['other']
        for x in (-2, 0, 1, 2):
            assert changed.evaluate('c', {'x': x}) == Workbook.build({**formulas, 'a': source}).evaluate('c', {'x': x})
    assert original.to_dict() == Workbook.build(formulas).to_dict()


def test_failed_edit_is_atomic_and_new_dependencies_are_used():
    original = Workbook.build({'a': 'x/x', 'b': 'a+1', 'c': 'y/y'})
    with pytest.raises(ValueError):
        original.update('a', 'b')
    changed = original.update('b', 'c+1')
    assert changed.update('c', '3').evaluate('b', {}) == 4
    assert original.evaluate('b', {'x': 0}) == 1
