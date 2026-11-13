import copy
import json

import pytest
import sympy as sp
from hypothesis import given, settings, strategies as st

from ltba.cas import cache_info, clear_caches, simplify_text
from ltba.workbook import Workbook, equivalent


def assert_same_semantics(actual, expected):
    assert actual.formulas == expected.formulas
    assert actual.dependencies == expected.dependencies
    assert actual.reverse_dependencies == expected.reverse_dependencies
    for name in actual.formulas:
        assert equivalent(actual.values[name], expected.values[name])
        assert actual.compiled[name].local_records == expected.compiled[name].local_records
        assert actual.assumptions[name] == expected.assumptions[name]


def test_equal_value_edit_preserves_provenance_and_stops_propagation():
    original = Workbook.build({'a': 'x/x', 'b': 'a+1', 'c': 'b*b', 'other': 'y/y'})
    changed = original.update('a', '(x/x)+0')
    assert changed.recomputed == ('a',)
    assert changed.value_changed == ()
    assert changed.provenance_changed == ('a',)
    assert changed.compiled['b'] is original.compiled['b']
    assert changed.ranks is original.ranks
    delta = changed.delta()
    assert list(delta['cells']) == ['a']
    client = original.to_dict()
    client.update(delta['cells'])
    assert client == changed.to_dict()
    assert_same_semantics(changed, Workbook.build(dict(changed.formulas)))


def test_exact_polynomial_equivalence_stops_numeric_propagation():
    original = Workbook.build({'a': '(x+1)^2', 'b': 'a+2'})
    changed = original.update('a', 'x^2+2*x+1')
    assert changed.recomputed == ('a',)
    assert changed.values['a'] is original.values['a']
    assert changed.values['b'] is original.values['b']
    assert equivalent(changed.values['a'], Workbook.build(dict(changed.formulas)).values['a'])


def test_batch_recomputes_diamond_once_and_delta_roundtrips():
    original = Workbook.build({'a': '1', 'b': '2', 'c': 'a+b', 'd': 'c*c', 'other': 'x/x'})
    changed = original.update_many({'b': '4', 'a': '3'})
    assert changed.recomputed == ('a', 'b', 'c', 'd')
    assert changed.evaluate('d', {}) == 49
    assert changed.compiled['other'] is original.compiled['other']
    assert_same_semantics(changed, Workbook.build(dict(changed.formulas)))
    client = original.to_dict()
    client.update(json.loads(json.dumps(changed.delta()))['cells'])
    assert client == changed.to_dict()
    assert original.evaluate('d', {}) == 9


def test_dependency_rewiring_and_collectively_valid_transaction():
    original = Workbook.build({'a': '1', 'b': 'a+1', 'c': 'b+1'})
    changed = original.update_many({'a': 'b+1', 'b': '2'})
    assert changed.evaluate('a', {}) == 3
    assert changed.reverse_dependencies['a'] == frozenset()
    assert changed.reverse_dependencies['b'] == frozenset(('a', 'c'))
    assert_same_semantics(changed, Workbook.build(dict(changed.formulas)))
    again = changed.update('b', '4')
    assert set(again.recomputed) == {'a', 'b', 'c'}
    assert_same_semantics(again, Workbook.build(dict(again.formulas)))


@pytest.mark.parametrize('changes', (
    {'a': '7', 'b': 'unknown_function(x)'},
    {'a': 'b', 'b': 'a'},
    {'a': '3', 'missing': '4'},
    {'a': '3', 'b': '('},
))
def test_failed_batch_leaves_original_and_indices_intact(changes):
    original = Workbook.build({'a': '1', 'b': 'a+1', 'c': 'b+1'})
    before = copy.deepcopy(original.to_dict())
    with pytest.raises((ValueError, KeyError, SyntaxError)):
        original.update_many(changes)
    assert original.to_dict() == before
    assert original.reverse_dependencies['a'] == frozenset(('b',))
    assert original.revision == 0


def test_real_assumption_is_checked_before_reusing_template():
    original = Workbook.build({'a': '1', 'b': 'sqrt(a^2)', 'c': 'b*b'})
    changed = original.update('a', 'sqrt(-1)')
    assert changed.values['a'] == sp.I
    assert changed.values['b'] == sp.I
    assert changed.values['c'] == -1
    assert changed.assumptions['b'].rebound_dependencies == ('a',)
    assert changed.assumptions['b'].bound_before_simplification
    assert changed.compiled['b'].local_records == ()
    assert_same_semantics(changed, Workbook.build(dict(changed.formulas)))
    restored = changed.update('a', '2')
    assert restored.values['b'] == 2
    assert not restored.assumptions['b'].bound_before_simplification
    with pytest.raises(ValueError):
        original.evaluate('a', {'x': sp.I})


def test_named_integer_exponent_and_failure_are_atomic():
    original = Workbook.build({'power': '2', 'value': 'x^power'})
    assert original.evaluate('value', {'x': 3}) == 9
    assert original.update('power', '0').evaluate('value', {'x': 0}) == 0
    with pytest.raises(ValueError):
        original.update('power', '1/2')
    assert original.evaluate('value', {'x': 3}) == 9


def test_shared_caches_preserve_each_occurrence_and_separate_bindings():
    clear_caches()
    source = '(x^2-1)/(x-1) + (x^2-1)/(x-1)'
    first = simplify_text(source)
    info = cache_info()
    assert info['divisions']['misses'] == 1
    assert info['divisions']['hits'] == 1
    assert len(first.local_records) == 2
    assert len({group.group_id for group in first.local_records}) == 2
    second = simplify_text(source)
    assert cache_info()['formulas']['hits'] == 1
    first.records.provenance.append('caller change')
    assert second.records.provenance == ['cas:simplify']
    assert simplify_text('sqrt(a^2)', bindings={'a': sp.I}).value == sp.I
    assert simplify_text('sqrt(a^2)', bindings={'a': sp.Integer(2)}).value == 2
    book = Workbook.build({'first': source, 'second': source})
    assert len(book.to_dict()['first']['local_provenance']) == 2
    assert len(book.to_dict()['second']['local_provenance']) == 2


def test_noop_delta_and_repeated_edit_snapshots():
    original = Workbook.build({'a': '1', 'b': 'a+1'})
    for changes in ({}, {'a': '1'}):
        changed = original.update_many(changes)
        assert changed.delta()['cells'] == {}
        assert changed.recomputed == ()
        assert changed.to_dict() == original.to_dict()
    changed = original.update('a', '3')
    restored = changed.update('a', '1')
    assert restored.to_dict() == original.to_dict()
    assert changed.evaluate('b', {}) == 4


@given(st.lists(st.tuples(st.integers(-2, 2), st.integers(-2, 2)), min_size=1, max_size=8))
@settings(max_examples=40, deadline=None, derandomize=True)
def test_random_batch_sequences_match_fresh_rebuild(edits):
    book = Workbook.build({'a': '0', 'b': '1', 'c': 'a/b', 'd': '1/(c-1)', 'e': 'c+c'})
    snapshots = []
    for a, b in edits:
        snapshots.append((book, book.to_dict()))
        changed = book.update_many({'a': str(a), 'b': str(b)})
        assert_same_semantics(changed, Workbook.build(dict(changed.formulas)))
        client = book.to_dict()
        client.update(changed.delta()['cells'])
        assert client == changed.to_dict()
        book = changed
    for snapshot, expected in snapshots:
        assert snapshot.to_dict() == expected


def test_snapshot_generations_and_strategy_equivalence():
    from ltba.snapshot import SnapshotMap
    original = Workbook.build({'root': '1', **{f'c{i}': f'root+{i}' for i in range(30)}})
    states = [original]
    for index in range(1, 36):
        previous = states[-1]
        edits = {'root': str(index + 1)}
        results = [previous.update_many(edits, strategy=mode)
                   for mode in ('auto', 'incremental', 'rebuild')]
        expected = Workbook.build({**previous.formulas, **edits}).to_dict()
        assert all(result.to_dict() == expected for result in results)
        assert results[0].delta()['cells'] == results[1].delta()['cells']
        states.append(results[0])
    for index, state in enumerate(states):
        assert state.values['root'] == index + 1
        if isinstance(state.formulas, SnapshotMap):
            assert state.formulas.depth <= 16


def test_sparse_snapshot_sharing_and_invalid_strategy():
    original = Workbook.build({f'c{i}': str(i) for i in range(100)})
    updated = original.update('c0', '123')
    assert updated.dependencies is original.dependencies or dict(updated.dependencies) == dict(original.dependencies)
    assert updated.values._base is original.values
    assert original.values['c0'] == 0
    with pytest.raises(ValueError):
        original.update_many({'c0': '2'}, strategy='invalid')


def test_identity_divisor_shortcut_tracks_guard_and_eligibility():
    workbook = Workbook.build({'d': '0', 'q': 'x/d', 'uses_d': '(x+d)/d'})
    changed = workbook.update('d', '1')
    assert 'q' not in changed.recomputed
    assert 'uses_d' in changed.recomputed
    assert set(changed.delta()['cells']) == {'d', 'uses_d'}
    assert changed.compiled['q'] is workbook.compiled['q']
    assert_same_semantics(changed, Workbook.build(changed.formulas))

    outside = changed.update('d', '2')
    assert 'q' in outside.recomputed
    assert outside.evaluate('q', {'x': 6}) == 3

    rewritten = changed.update('q', '(x+d)/d').update('d', '0')
    assert 'q' in rewritten.recomputed
    assert_same_semantics(rewritten, Workbook.build(rewritten.formulas))

    batch = changed.update_many({'q': '(x+1)/d', 'd': '0'})
    assert 'q' in batch.recomputed
    assert_same_semantics(batch, Workbook.build(batch.formulas))


def test_forward_rewire_reuses_rank_order_and_backward_rewire_validates():
    original = Workbook.build({'a': '0', 'b': '1', 'q': 'x/a'})
    moved = original.update('q', 'x/b')
    assert moved.ranks is original.ranks
    assert_same_semantics(moved, Workbook.build(moved.formulas))

    backwards = moved.update('a', 'q + 1')
    assert backwards.ranks['q'] < backwards.ranks['a']
    assert_same_semantics(backwards, Workbook.build(backwards.formulas))
    with pytest.raises(ValueError, match='cycle'):
        backwards.update('q', 'x/a')


def test_snapshot_sizes_survive_new_keys_and_compaction():
    from types import MappingProxyType
    from ltba.snapshot import snapshot

    base = MappingProxyType({f'k{i}': i for i in range(8)})
    current = base
    for index in range(25):
        current = snapshot(current, {'k0': index, f'new{index}': index})
        assert len(current) == 9 + index
        assert len(dict(current)) == len(current)
    assert len(base) == 8
    assert current['k0'] == 24
    assert current['new0'] == 0
    assert len(snapshot(current, {f'dense{i}': i for i in range(40)})) == 73


def test_delta_serializes_records_without_rendering_template(monkeypatch):
    from ltba.cas import SimplificationResult

    workbook = Workbook.build({'d': '2', 'q': 'x/d'}).update('d', '0')
    expected = workbook.delta()
    assert expected['cells']['q']['local_provenance'] == workbook.compiled['q'].to_dict()['groups']

    def unexpected_template_render(_):
        pytest.fail('Workbook delta should serialize the division records directly')

    monkeypatch.setattr(SimplificationResult, 'to_dict', unexpected_template_render)
    assert workbook.delta() == expected
