"""Exact root partitioning for sums of univariate polynomial quotients."""
import ast
from dataclasses import dataclass
from types import MappingProxyType

import sympy as sp

from .point_audit import _signed_terms


def _polynomial(node, variable):
    if isinstance(node, ast.Name) and node.id == variable.name:
        return sp.Poly(variable, variable, domain=sp.QQ)
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return sp.Poly(node.value, variable, domain=sp.QQ)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _polynomial(node.operand, variable)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp):
        left = _polynomial(node.left, variable)
        if isinstance(node.op, ast.Pow):
            exponent = node.right
            if (isinstance(exponent, ast.Constant) and type(exponent.value) is int
                    and exponent.value > 0):
                return left ** exponent.value
        else:
            right = _polynomial(node.right, variable)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
    raise ValueError('Expected a univariate rational-coefficient polynomial')


@dataclass(frozen=True, slots=True)
class PolynomialDivisionSite:
    span: tuple
    numerator: sp.Poly
    denominator: sp.Poly

    def trace_at(self, point):
        point = sp.sympify(point, strict=True)
        numerator = self.numerator.eval(point)
        divisor = self.denominator.eval(point)
        if _is_zero(divisor):
            return 'zero-no-op', sp.S.Zero if _is_zero(numerator) else numerator
        if _is_zero(divisor - 1):
            return 'positive-one', numerator
        return 'regular', numerator / divisor


@dataclass(frozen=True, slots=True)
class PolynomialAudit:
    ordinary: sp.Poly
    corrections: MappingProxyType
    sites: tuple

    def solve_equal(self, target=0):
        target = sp.sympify(target, strict=True)
        if not target.is_Rational:
            raise ValueError('Expected an exact rational target')
        residual = self.ordinary - target
        if residual.is_zero:
            excluded = []
            for point, correction in self.corrections.items():
                if not _is_zero(correction):
                    excluded.append(point)
            return sp.S.Reals - sp.FiniteSet(*excluded)
        exception_points = sp.FiniteSet(*self.corrections)
        ordinary_roots = sp.FiniteSet(*residual.real_roots(radicals=False))
        matching = [point for point, correction in self.corrections.items()
                    if _is_zero(residual.eval(point) + correction)]
        return (ordinary_roots - exception_points) | sp.FiniteSet(*matching)


def _is_zero(value):
    if value.is_zero is not None:
        return value.is_zero
    return not any(sp.polys.numberfields.to_number_field(value).coeffs())


def compile_polynomial_audit(source, symbol):
    """Build a root partition, or return None if exact division is unavailable."""
    if not isinstance(symbol, str) or not symbol.isidentifier():
        raise ValueError('Expected a symbol name')
    variable = sp.Symbol(symbol, real=True)
    tree = ast.parse(source.strip().replace('^', '**'), mode='eval').body
    ordinary = sp.Poly(0, variable, domain=sp.QQ)
    corrections, sites = {}, []
    try:
        for node, sign, _ in _signed_terms(((tree, 0),)):
            if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Div):
                ordinary += sign * _polynomial(node, variable)
                continue
            numerator = _polynomial(node.left, variable)
            denominator = _polynomial(node.right, variable)
            if denominator.is_zero:
                return None
            quotient = numerator.exquo(denominator)
            ordinary += sign * quotient
            sites.append(PolynomialDivisionSite(
                (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset),
                numerator, denominator,
            ))
            for root, _ in denominator.real_roots(multiple=False, radicals=False):
                # Exact division proves the original numerator vanishes here.
                # The actual operation is 0/0, so remove the ordinary value.
                corrections[root] = corrections.get(root, 0) - sign * quotient.eval(root)
    except (ValueError, sp.ExactQuotientFailed, NotImplementedError):
        return None
    return PolynomialAudit(ordinary, MappingProxyType(corrections), tuple(sites))
