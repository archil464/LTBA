"""Source-preserving cancellation for ordinary univariate real rationals."""

import ast
from dataclasses import dataclass
from functools import cached_property

import sympy as sp


@dataclass(frozen=True)
class DomainGuard:
    span: tuple[int, int, int, int]
    expression: sp.Expr
    excluded: sp.Set


@dataclass(frozen=True)
class DomainCancellation:
    variable: sp.Symbol
    expression: sp.Expr | None
    guards: tuple[DomainGuard, ...]

    @cached_property
    def domain(self):
        return sp.S.Reals - sp.Union(*(guard.excluded for guard in self.guards))

    def evaluate(self, point):
        """Return the canceled expression's value on the original domain."""
        point = sp.sympify(point, strict=True)
        if self.domain.contains(point) is not sp.true:
            raise ValueError('Point is outside the original real domain')
        return self.expression.subs(self.variable, point)


@dataclass(frozen=True)
class RewriteDomainAudit:
    original: DomainCancellation
    replacement: DomainCancellation
    equal_on: sp.Set

    @property
    def added_domain(self):
        return self.replacement.domain - self.original.domain

    @property
    def removed_domain(self):
        return self.original.domain - self.replacement.domain

    @property
    def preserves_domain_and_values(self):
        return self.original.domain == self.replacement.domain == self.equal_on


def _real_zeros(expr, variable):
    numerator, _ = sp.cancel(expr).as_numer_denom()
    poly = sp.Poly(numerator, variable, domain=sp.QQ)
    if poly.is_zero:
        return sp.S.Reals
    return sp.FiniteSet(*poly.real_roots(radicals=False))


def cancel_ordinary(source, symbol):
    """Cancel rational source over the reals and retain its original domain.

    Supports integer literals, one symbol, +, -, *, / and nonzero literal
    integer powers. A nowhere-defined input returns expression=None.
    """
    if not isinstance(symbol, str) or not symbol.isidentifier():
        raise ValueError('Expected a symbol name')
    variable = sp.Symbol(symbol, real=True)
    root = ast.parse(source.strip().replace('^', '**'), mode='eval').body
    guards = []

    def nonzero(node, expr):
        if expr is None:
            return False
        excluded = _real_zeros(expr, variable)
        if excluded is not sp.S.EmptySet:
            guards.append(DomainGuard(
                (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset),
                expr, excluded,
            ))
        return excluded is not sp.S.Reals

    def visit(node):
        if isinstance(node, ast.Name) and node.id == symbol:
            return variable
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return sp.Integer(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return -value if value is not None and isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            left = visit(node.left)
            if isinstance(node.op, ast.Pow):
                power = ast.literal_eval(node.right)
                if type(power) is not int or power == 0:
                    raise ValueError('Expected a nonzero literal integer power')
                if left is None or (power < 0 and not nonzero(node, left)):
                    return None
                return left ** power
            right = visit(node.right)
            if isinstance(node.op, ast.Div):
                valid = nonzero(node, right)
                return left / right if valid and left is not None else None
            if isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
                if left is None or right is None:
                    return None
                if isinstance(node.op, ast.Add):
                    return left + right
                if isinstance(node.op, ast.Sub):
                    return left - right
                return left * right
        raise ValueError('Expected a univariate rational expression')

    expression = visit(root)
    return DomainCancellation(variable, sp.cancel(expression) if expression is not None else None,
                              tuple(guards))


def audit_ordinary_rewrite(original, replacement, symbol):
    """Compare values on the common domain and expose changes to definedness."""
    left = cancel_ordinary(original, symbol)
    right = cancel_ordinary(replacement, symbol)
    common = left.domain.intersect(right.domain)
    equal_on = common if common is sp.S.EmptySet else common.intersect(
        _real_zeros(left.expression - right.expression, left.variable)
    )
    return RewriteDomainAudit(left, right, equal_on)
