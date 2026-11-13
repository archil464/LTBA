import ast
import itertools
from fractions import Fraction

import pytest
import sympy as sp
from hypothesis import given, settings, strategies as st

from ltba import simplify_text
from ltba.cas import compile_text, result_dict


def original_value(source, values):
    """Independent exact evaluator for original rational arithmetic syntax."""
    def visit(node):
        if isinstance(node, ast.Constant):
            return Fraction(node.value)
        if isinstance(node, ast.Name):
            return Fraction(values[node.id])
        if isinstance(node, ast.UnaryOp):
            return -visit(node.operand) if isinstance(node.op, ast.USub) else visit(node.operand)
        left, right = visit(node.left), visit(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left if right == 0 else left / right
        if isinstance(node.op, ast.Pow):
            return Fraction(0) if left == 0 else left ** int(right)
        raise AssertionError(type(node))
    return visit(ast.parse(source.replace("^", "**"), mode="eval").body)


RATIONAL_CASES = (
    "x/x", "(x^2-y^2)/(x-y)", "1/(x/x-1)", "x/(y-y)",
    "(x/y)*y", "(x/0)/y", "x/(y/0)", "(x/y)/(x/y)",
    "0*(x/y)", "x/x-x/x", "1/((x/y)-(x/y))", "(x/y)^0",
    "x^(-2)", "0^0", "0^-1", "1/0", "0/0", "(x^2)/(x*y)",
)


@pytest.mark.parametrize("source", RATIONAL_CASES)
def test_singular_and_nested_cases_against_original_arithmetic(source):
    flat = simplify_text(source)
    tree = simplify_text(source, storage="tree")
    assert flat.to_dict() == tree.to_dict()
    for x, y in itertools.product((-2, 0, 1, 2), repeat=2):
        expected = original_value(source, {"x": x, "y": y})
        assert flat.evaluate({"x": x, "y": y}) == sp.Rational(expected)


leaves = st.sampled_from(("x", "y", "0", "1", "-1", "2"))
expressions = st.recursive(
    leaves,
    lambda children: st.tuples(children, st.sampled_from(("+", "-", "*", "/")), children)
        .map(lambda items: f"({items[0]}{items[1]}{items[2]})"),
    max_leaves=6,
)


@given(expressions, st.integers(-2, 2), st.integers(-2, 2))
@settings(max_examples=150, deadline=None, derandomize=True)
def test_generated_rational_expressions_preserve_exact_values(source, x, y):
    expected = original_value(source, {"x": x, "y": y})
    result = simplify_text(source)
    assert result.evaluate({"x": x, "y": y}) == sp.Rational(expected)


@given(expressions, st.integers(-2, 2), st.integers(-2, 2), st.integers(-2, 2))
@settings(max_examples=75, deadline=None, derandomize=True)
def test_integer_powers_of_guarded_values(source, exponent, x, y):
    powered = f"({source})**({exponent})"
    expected = original_value(powered, {"x": x, "y": y})
    assert simplify_text(powered).evaluate({"x": x, "y": y}) == sp.Rational(expected)


def test_repeated_guards_keep_source_occurrences_after_scalar_collapse():
    result = simplify_text("0*(x/x) + x/x - x/x")
    assert result.value == 0
    assert len(result.local_records) == 3
    assert len({group.group_id for group in result.local_records}) == 3
    assert all(group.description == "x/x" for group in result.local_records)


def test_actual_algebraic_simplification_and_zero_branch():
    x = sp.Symbol("x", real=True)
    result = simplify_text("(x^2-1)/(x-1)")
    assert result.value == sp.Piecewise((x+1, sp.Ne(x, 1)), (0, True))
    assert result.evaluate({"x": 1}) == 0
    assert simplify_text("sqrt(x^2)").value == sp.Abs(x)
    assert simplify_text("(x+1)*(x-1) - x^2").evaluate({"x": 2}) == -1
    assert simplify_text("0.1/0.2").value == sp.Rational(1, 2)


def test_conventional_factored_baseline_retains_the_same_information():
    source = "(x^2-y^2)/(x-y) + sqrt(x^2) + 1/(x/x-1)"
    value, groups = compile_text(source)
    expected = result_dict(source, value, groups, ["cas:simplify"])
    assert simplify_text(source, storage="tree").to_dict() == expected


@pytest.mark.parametrize("source", ("f(x)", "x.attr", "x[0]", "x**y", "[x]", "__import__('os')"))
def test_unsupported_syntax_has_an_explicit_error(source):
    with pytest.raises(ValueError):
        simplify_text(source)
