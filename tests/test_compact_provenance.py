"""Semantic and persistence checks for the measured compact baselines."""
from fractions import Fraction

import pytest

from benchmarks.compact_provenance import (
    BACKENDS,
    FAMILIES,
    arithmetic,
    build,
    check_structure,
    parse,
    selected_records,
    specifications,
    validate_case,
)


@pytest.mark.parametrize("family", FAMILIES)
def test_exhaustive_values_and_provenance_after_repeated_updates(family):
    assert validate_case(family, 3, exhaustive=True) > 0


@pytest.mark.parametrize("backend", BACKENDS)
def test_middle_update_changes_values_and_preserves_prior_version(backend):
    before = build(backend, "division", 5)
    after = before.rewrite_local(2, "7", "value_change")
    values = {f"x{i}": 2 for i in range(1, 6)}
    old_records = selected_records(before, values)
    new_records = selected_records(after, values)
    assert arithmetic(parse(old_records[2].value), values) == Fraction(1)
    assert arithmetic(parse(new_records[2].value), values) == Fraction(7)
    assert old_records[:2] + old_records[3:] == new_records[:2] + new_records[3:]
    assert old_records[2].guard == new_records[2].guard
    assert old_records[2].tag == new_records[2].tag
    values["x3"] = 0
    assert selected_records(after, values)[2].value == "0"
    check_structure(before, specifications("division", 5))


@pytest.mark.parametrize("backend", BACKENDS)
def test_shared_guard_preserves_distinct_factor_provenance(backend):
    expression = build(backend, "shared_division", 5)
    for value, payload in ((0, "0"), (3, "1")):
        records = selected_records(expression, {"x1": value})
        assert len(records) == 5
        assert all(record.value == payload for record in records)
    check_structure(expression, specifications("shared_division", 5))


@pytest.mark.parametrize("backend", BACKENDS)
def test_invalid_update_index_is_rejected(backend):
    expression = build(backend, "division", 3)
    for index in (-1, 3):
        with pytest.raises(IndexError):
            expression.rewrite_local(index, "7", "invalid")
