"""Exact source-level audit for signed sums of proportional affine quotients."""

import ast
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType

import sympy as sp


def _affine(node, variable):
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return 0, node.value
    if isinstance(node, ast.Name) and node.id == variable:
        return 1, 0
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        slope, intercept = _affine(node.operand, variable)
        return (-slope, -intercept) if isinstance(node.op, ast.USub) else (slope, intercept)
    if isinstance(node, ast.BinOp):
        a, b = _affine(node.left, variable)
        c, d = _affine(node.right, variable)
        if isinstance(node.op, ast.Add):
            return a + c, b + d
        if isinstance(node.op, ast.Sub):
            return a - c, b - d
        if isinstance(node.op, ast.Mult) and (not a or not c):
            return a * d + b * c, b * d
    raise ValueError('Expected an affine expression in the requested variable')


@dataclass(frozen=True, slots=True)
class DivisionSite:
    span: tuple
    numerator: tuple
    denominator: tuple

    def trace_at(self, point):
        point = Fraction(point)
        a, b = self.numerator
        c, d = self.denominator
        numerator, divisor = a * point + b, c * point + d
        if divisor == 0:
            return 'zero-no-op', numerator
        if divisor == 1:
            return 'positive-one', numerator
        return 'regular', numerator / divisor


@dataclass(frozen=True, slots=True)
class PointEquality:
    """An exact set: include all reals by default, or only the listed points."""

    default: bool
    points: frozenset

    def to_sympy(self):
        points = sp.FiniteSet(*(sp.Rational(point.numerator, point.denominator)
                               for point in self.points))
        if not self.default:
            return points
        if len(points) > 32:
            return sp.Complement(sp.S.Reals, points, evaluate=False)
        return sp.S.Reals - points


@dataclass(frozen=True, slots=True)
class PointAudit:
    ordinary: Fraction
    corrections: MappingProxyType
    sites: tuple

    def equality(self, target=0):
        """Return a finite or cofinite result without creating SymPy objects per point."""
        if not isinstance(target, (int, Fraction)):
            target = sp.sympify(target, strict=True)
            if not target.is_Rational:
                raise ValueError('Point audit requires an exact rational target')
            target = Fraction(int(target.p), int(target.q))
        default = self.ordinary == target
        if default:
            points = frozenset(point for point, delta in self.corrections.items() if delta)
        else:
            difference = target - self.ordinary
            points = frozenset(point for point, delta in self.corrections.items() if delta == difference)
        return PointEquality(default, points)

    def solve_equal(self, target=0):
        return self.equality(target).to_sympy()


def compile_point_audit(source, symbol):
    """Return a compact audit plan or None when the source needs general compilation."""
    return _compile_roots(((ast.parse(source.strip(), mode='eval').body, 0),), symbol)


def compile_point_audit_terms(terms, symbol):
    """Audit an iterable of single-line addends, with spans indexed by input line.

    Each entry is a complete expression in the affine audit grammar. Entries
    are added together, and a negative addend can be written as `-(...)`.
    Only the current addend's AST is held. A result of None indicates an
    unsupported expression. Syntax errors are propagated.
    """
    def roots():
        for line, term in enumerate(terms):
            if '\n' in term or '\r' in term:
                raise SyntaxError('Expected one expression per input line')
            yield ast.parse(term, mode='eval').body, line

    return _compile_roots(roots(), symbol)


def _compile_roots(roots, symbol):
    if not isinstance(symbol, str) or not symbol.isidentifier():
        raise ValueError('Expected a symbol name')
    return _accumulate(roots, symbol)


def _signed_terms(roots):
    for root, shift in roots:
        pending = [(root, 1)]
        while pending:
            node, sign = pending.pop()
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                pending.append((node.operand, -sign if isinstance(node.op, ast.USub) else sign))
            elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
                pending.append((node.right, -sign if isinstance(node.op, ast.Sub) else sign))
                pending.append((node.left, sign))
            else:
                yield node, sign, shift


def _accumulate(roots, symbol):
    ordinary, corrections, sites = 0, {}, []
    try:
        for node, sign, shift in _signed_terms(roots):
            if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Div):
                slope, constant = _affine(node, symbol)
                if slope:
                    return None
                ordinary += sign * constant
                continue
            a, b = _affine(node.left, symbol)
            c, d = _affine(node.right, symbol)
            if not c or a * d != b * c:
                return None
            # Proportionality proves the original numerator is zero at
            # this root. The entire ordinary contribution is removed there.
            contribution = sign * (a // c) if a % c == 0 else Fraction(sign * a, c)
            point = -d // c if d % c == 0 else Fraction(-d, c)
            ordinary += contribution
            corrections[point] = corrections.get(point, 0) - contribution
            sites.append(DivisionSite((node.lineno + shift, node.col_offset,
                                       node.end_lineno + shift, node.end_col_offset),
                                      (a, b), (c, d)))
    except ValueError:
        return None
    return PointAudit(Fraction(ordinary), MappingProxyType(corrections), tuple(sites))
