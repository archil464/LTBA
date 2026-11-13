import pytest
import sympy as sp

from ltba import piecewise_side_limit, refine_integer_piecewise


def test_issue_27627_refines_only_on_the_assumed_integer_domain():
    x = sp.Symbol('x', real=True)
    candidate = 1000 - x
    original = sp.Piecewise((1, x >= 999), (candidate, True))
    assert refine_integer_piecewise(original, x, x < 1000) == candidate
    assert refine_integer_piecewise(original, x, x <= 1000) == original
    real_counterexample = sp.Rational(1999, 2)
    assert original.subs(x, real_counterexample) == 1
    assert candidate.subs(x, real_counterexample) == sp.Rational(1, 2)


def test_integer_refinement_respects_branch_order():
    x = sp.Symbol('x', integer=True)
    expression = sp.Piecewise((x, x <= 1), (7, x <= 1), (x + 1, True), evaluate=False)
    assert refine_integer_piecewise(expression, x) == expression
    expression = sp.Piecewise((1, x >= 1), (99, x >= 2), (2 - x, True), evaluate=False)
    assert refine_integer_piecewise(expression, x, x < 2) == 2 - x


def test_issue_26313_uses_punctured_intervals():
    x = sp.Symbol('x', real=True)
    expression = sp.Piecewise((x**2, x <= 2), (5*x - 7, x > 2))
    assert piecewise_side_limit(expression, x, 2, direction='+') == 3
    assert piecewise_side_limit(expression, x, 2, direction='-') == 4
    assert expression.subs(x, 2) == 4


def test_limits_skip_isolated_points_and_detect_missing_side():
    x = sp.Symbol('x', real=True)
    expression = sp.Piecewise((99, sp.Eq(x, 0)), (1/x, x > 0))
    assert piecewise_side_limit(expression, x, 0, direction='+') is sp.oo
    with pytest.raises(ValueError, match='No branch'):
        piecewise_side_limit(expression, x, 0, direction='-')
