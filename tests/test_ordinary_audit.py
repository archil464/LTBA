import pytest
import sympy as sp

from ltba import audit_ordinary_rewrite, cancel_ordinary, simplify_text


def test_issue_5344_keeps_original_domain():
    source = '(x**2-3*x+2)/(x-1)'
    result = cancel_ordinary(source, 'x')
    assert result.expression == result.variable - 2
    assert result.domain == sp.S.Reals - sp.FiniteSet(1)
    assert len(result.guards) == 1
    assert result.guards[0].excluded == sp.FiniteSet(1)
    assert result.evaluate(3) == 1
    with pytest.raises(ValueError, match='outside'):
        result.evaluate(1)
    assert simplify_text(source).evaluate({'x': 1}) == 0


def test_rewrite_reports_both_directions_of_domain_change():
    result = audit_ordinary_rewrite('x/x', '(x-1)/(x-1)', 'x')
    assert result.equal_on == sp.S.Reals - sp.FiniteSet(0, 1)
    assert result.added_domain == sp.FiniteSet(0)
    assert result.removed_domain == sp.FiniteSet(1)
    assert not result.preserves_domain_and_values


def test_nested_division_keeps_intermediate_exclusions():
    result = cancel_ordinary('1/(1/x-1)', 'x')
    assert result.domain == sp.S.Reals - sp.FiniteSet(0, 1)
    assert result.evaluate(2) == -2


def test_zero_multiplier_does_not_erase_undefined_subexpression():
    result = cancel_ordinary('0*(1/x)', 'x')
    assert result.expression == 0
    assert result.domain == sp.S.Reals - sp.FiniteSet(0)
    assert cancel_ordinary('0*(1/(x-x))', 'x').domain is sp.S.EmptySet


def test_audit_distinguishes_value_mismatch_from_domain_change():
    result = audit_ordinary_rewrite('x/x', 'x+1', 'x')
    assert result.equal_on is sp.S.EmptySet
    assert result.added_domain == sp.FiniteSet(0)
    assert audit_ordinary_rewrite('x/x', '2*x/(2*x)', 'x').preserves_domain_and_values


def test_negative_power_guard_and_unsupported_input():
    assert cancel_ordinary('(x-1)**(-1)', 'x').domain == sp.S.Reals - sp.FiniteSet(1)
    with pytest.raises(ValueError):
        cancel_ordinary('x/y', 'x')
