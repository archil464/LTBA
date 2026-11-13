"""Guard-preserving simplification of real-symbol arithmetic using SymPy.

Supported syntax is numbers, symbols, +, -, *, /, integer powers, abs and
sqrt. Division is parsed before cancellation. Division by zero is a no-op
on the evaluated numerator: a/0=a (therefore 0/0=0). Integer powers
use the project's separate convention 0**n=0, including n<=0. Square roots
use SymPy's principal square root. Conditional expressions remain factored.
"""
from __future__ import annotations

import ast
import operator
from dataclasses import dataclass
from functools import lru_cache

import sympy as sp

from .core import Guard, LocalBranch, LocalBranchGroup, LTBAExpr


_OPERATIONS = {
    "add": operator.add, "subtract": operator.sub, "multiply": operator.mul,
    "negate": operator.neg, "power": sp.Pow, "abs": sp.Abs, "sqrt": sp.sqrt,
}


@lru_cache(maxsize=4096)
def _algebra_value(operation, *arguments):
    return _OPERATIONS[operation](*arguments)


@lru_cache(maxsize=4096)
def _division_guards(denominator):
    nonzero = sp.Ne(denominator, 0)
    unit = sp.Eq(denominator, 1)
    return nonzero, tuple(Guard(sp.sstr(test)) for test in (
        sp.Not(nonzero), unit, sp.And(nonzero, sp.Not(unit)),
    ))


@lru_cache(maxsize=4096)
def _guarded_factor(denominator):
    nonzero, _ = _division_guards(denominator)
    return sp.Piecewise((denominator, nonzero), (1, True))


def division_case(denominator):
    """Resolve the provenance label for an exact, decidable divisor."""
    denominator = sp.sympify(denominator, strict=True)
    nonzero, guards = _division_guards(denominator)
    if nonzero is sp.false:
        return "zero-no-op"
    if guards[1].text == "True":
        return "positive-one"
    if guards[2].text == "True":
        return "regular"
    raise ValueError("Division case requires a decidable denominator")


def _rewrite(value, transform, collect):
    # Hide complete guarded values during ordinary polynomial/rational rewrites.
    opaque = {item: sp.Dummy() for item in value.atoms(sp.Piecewise)}
    bare = value.xreplace(opaque)
    if transform == "collect":
        bare = sp.collect(bare, collect)
    elif transform != "horner" or bare.is_polynomial():
        bare = {"factor": sp.factor, "expand": sp.expand, "together": sp.together,
                "horner": sp.horner}[transform](bare)
    return bare.xreplace({symbol: item for item, symbol in opaque.items()})


@lru_cache(maxsize=4096)
def _division_parts(numerator, denominator):
    """Share work; zero division preserves the evaluated numerator unchanged."""
    condition, _ = _division_guards(denominator)
    # Build the zero branch from the original evaluated numerator. The
    # ordinary quotient is only used on the nonzero guard.
    fallback = numerator
    if condition is sp.false:
        ordinary = sp.Mul(numerator, sp.Pow(denominator, -1, evaluate=False), evaluate=False)
    else:
        quotient = numerator / denominator
        # Distinct symbols have no common polynomial factor. Preserve the
        # original division guards while skipping the polynomial GCD setup.
        if (numerator.is_Symbol and denominator.is_Symbol and numerator != denominator
                or quotient.has(sp.Piecewise)):
            ordinary = quotient
        else:
            ordinary = sp.cancel(quotient)
        if condition is not sp.true:
            if denominator.is_Symbol:
                fallback = numerator.subs(denominator, 0)
            elif (numerator.is_polynomial() and denominator.is_polynomial()
                  and ordinary.is_polynomial()
                  and sp.expand(numerator - ordinary * denominator) == 0):
                # Exact polynomial identity proves the source numerator
                # already vanishes at the divisor's zeros.
                fallback = sp.Integer(0)
    return condition, ordinary, fallback


def groups_to_dict(groups):
    return [
        {"group_id": group.group_id, "description": group.description,
         "branches": [{"guard": branch.guard.text, "value": branch.value, "tag": branch.tag}
                      for branch in group.branches]}
        for group in groups
    ]


def result_dict(source, value, groups, history):
    return {
        "source": source,
        "value": sp.sstr(value),
        "groups": groups_to_dict(groups),
        "history": list(history),
    }


def _solve_by_exception_points(residual, variable):
    """Solve sums of constants with isolated, exact affine exceptions."""
    ordinary = sp.S.Zero
    corrections = {}
    for term in sp.Add.make_args(residual):
        if term.is_Rational:
            ordinary += term
            continue
        coefficient, piece = term.as_coeff_Mul(rational=True)
        if not isinstance(piece, sp.Piecewise) or len(piece.args) != 2:
            return None
        (regular, condition), (exception, otherwise) = piece.args
        if (otherwise is not sp.true or not isinstance(condition, sp.Ne)
                or not regular.is_Rational or not exception.is_Rational):
            return None
        affine = (condition.lhs - condition.rhs).as_poly(variable)
        if affine is None or affine.degree() != 1:
            return None
        slope, intercept = affine.all_coeffs()
        if not (slope.is_Rational and intercept.is_Rational):
            return None
        point = -intercept / slope
        ordinary += coefficient * regular
        # The exception payload was compiled from the source numerator on
        # the zero branch. The canceled quotient only supplies the regular value.
        corrections[point] = corrections.get(point, sp.S.Zero) + coefficient * (exception - regular)
    if ordinary:
        return sp.FiniteSet(*(point for point, change in corrections.items() if ordinary + change == 0))
    excluded = sp.FiniteSet(*(point for point, change in corrections.items() if change))
    if len(excluded) > 32:
        return sp.Complement(sp.S.Reals, excluded, evaluate=False)
    return sp.S.Reals - excluded


def _guarded_solve(residual, variable):
    """Intersect ordered guard domains before constructing each child expression."""
    fast = _solve_by_exception_points(residual, variable)
    if fast is not None:
        return fast
    unresolved = sp.ConditionSet(variable, sp.Eq(residual, 0), sp.S.Reals)
    pending = [(residual, sp.S.Reals)]
    guard_domains = {}
    solutions = []
    for _ in range(1024):
        if not pending:
            return sp.Union(*solutions)
        value, domain = pending.pop()
        if isinstance(domain, sp.FiniteSet):
            # Exact guard equalities provide concrete substitutions.
            for point in domain:
                check = sp.Eq(value.subs(variable, point), 0)
                if check is sp.true:
                    solutions.append(sp.FiniteSet(point))
                elif check is not sp.false:
                    solutions.append(sp.ConditionSet(variable, sp.Eq(value, 0), sp.FiniteSet(point)))
            continue
        pieces = value.atoms(sp.Piecewise)
        if not pieces:
            solutions.append(sp.solveset(value, variable, domain=domain))
            continue
        # Resolve inner conditions before converting an outer guard to a set.
        piece = min(pieces, key=lambda item: (sp.count_ops(item), sp.default_sort_key(item)))
        remaining = domain
        for branch, guard in piece.args:
            if guard.free_symbols - {variable} or guard.has(sp.Piecewise):
                return unresolved
            try:
                if guard not in guard_domains:
                    guard_domains[guard] = guard.as_set()
                active = remaining.intersect(guard_domains[guard])
                remaining = remaining - guard_domains[guard]
            except (NotImplementedError, ValueError, TypeError):
                return unresolved
            if active is not sp.S.EmptySet:
                pending.append((value.xreplace({piece: branch}), active))
            if remaining is sp.S.EmptySet:
                break
    # Bound branch exploration for expressions with many feasible combinations.
    return unresolved


@dataclass(frozen=True)
class SimplificationResult:
    value: sp.Expr
    records: LTBAExpr

    @property
    def guards(self):
        return tuple(branch.guard.text for group in self.records.branch_groups for branch in group.branches)

    @property
    def local_records(self):
        return self.records.branch_groups

    def evaluate(self, values):
        substitutions = {sp.Symbol(name, real=True): sp.sympify(value, strict=True) for name, value in values.items()}
        if any(value.is_real is not True for value in substitutions.values()):
            raise ValueError("External parameter values must be real")
        return self.value.subs(substitutions, simultaneous=True)

    def solve_equal(self, symbol, target=0):
        """Solve an equality over the reals with each value branch restricted to its guard."""
        if not isinstance(symbol, str) or not symbol.isidentifier():
            raise ValueError("solve_equal requires a symbol name")
        variable = sp.Symbol(symbol, real=True)
        target = sp.sympify(target, strict=True)
        residual = self.value - target
        return _guarded_solve(residual, variable)

    def to_dict(self):
        return result_dict(self.records.base, self.value, self.records.branch_groups, self.records.provenance)


class _Compiler:
    def __init__(self, source, bindings=(), *, combine=False):
        self.source = source
        self.bindings = dict(bindings)
        self.groups = []
        self.combine = combine

    def record_branches(self, node, kind, alternatives):
        location = f"{node.lineno}:{node.col_offset}:{node.end_lineno}:{node.end_col_offset}"
        source = ast.get_source_segment(self.source, node)
        self.groups.append(LocalBranchGroup(
            group_id=f"{kind}:{location}",
            branches=tuple(
                LocalBranch(guard if isinstance(guard, Guard) else Guard(sp.sstr(guard)), sp.sstr(value), f"{kind}:{tag}:{source}")
                for guard, value, tag in alternatives
            ),
            description=source,
        ))

    def record(self, node, kind, condition, ordinary, fallback):
        self.record_branches(node, kind, (
            (condition, ordinary, "regular"),
            (sp.Not(condition), fallback, "exception"),
        ))

    def divide(self, node, numerator, denominator, *, chain=False):
        condition, ordinary, fallback = _division_parts(numerator, denominator)
        _, (zero, unit, regular) = _division_guards(denominator)
        self.record_branches(node, "division", (
            (zero, fallback, "zero-no-op"),
            (unit, numerator, "positive-one"),
            (regular, ordinary, "regular"),
        ))
        if self.combine or chain:
            return numerator / _guarded_factor(denominator)
        return sp.Piecewise((ordinary, condition), (fallback, True))

    def division_chain(self, node):
        divisions = []
        while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            divisions.append(node)
            node = node.left
        value = self.visit(node)
        for division in reversed(divisions):
            value = self.divide(division, value, self.visit(division.right),
                                chain=len(divisions) > 1)
        return value

    def multiply(self, node):
        """Cancel a matching divisor only on its nonzero branch."""
        left, right = node.left, node.right
        for quotient, multiplier in ((left, right), (right, left)):
            if not (isinstance(quotient, ast.BinOp) and isinstance(quotient.op, ast.Div)):
                continue
            divisor = quotient.right
            if ast.dump(divisor) != ast.dump(multiplier):
                continue
            # Visit both source occurrences so any nested operations retain
            # their own provenance. The cached algebra shares their values.
            if multiplier is left:
                factor = self.visit(multiplier)
            numerator = self.visit(quotient.left)
            denominator = self.visit(divisor)
            self.divide(quotient, numerator, denominator)
            if multiplier is right:
                factor = self.visit(multiplier)
            nonzero, _ = _division_guards(factor)
            return sp.Piecewise((numerator, nonzero), (0, True))
        return _algebra_value("multiply", self.visit(left), self.visit(right))

    def power(self, node, base, exponent):
        if not exponent.is_Integer:
            raise ValueError("Only integer powers are defined by this arithmetic policy")
        if exponent > 0:
            return _algebra_value("power", base, exponent)
        condition = sp.Ne(base, 0)
        ordinary = _algebra_value("power", base, exponent)
        self.record(node, "power", condition, ordinary, sp.Integer(0))
        return sp.Piecewise((ordinary, condition), (0, True))

    def visit(self, node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return sp.Rational(ast.get_source_segment(self.source, node))
        if isinstance(node, ast.Name):
            return self.bindings.get(node.id, sp.Symbol(node.id, real=True))
        if isinstance(node, ast.UnaryOp):
            value = self.visit(node.operand)
            if isinstance(node.op, ast.USub):
                return _algebra_value("negate", value)
            if isinstance(node.op, ast.UAdd):
                return value
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Div):
                return self.division_chain(node)
            if isinstance(node.op, ast.Mult):
                return self.multiply(node)
            left, right = self.visit(node.left), self.visit(node.right)
            if isinstance(node.op, ast.Add):
                return _algebra_value("add", left, right)
            if isinstance(node.op, ast.Sub):
                return _algebra_value("subtract", left, right)
            if isinstance(node.op, ast.Pow):
                return self.power(node, left, right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and len(node.args) == 1 and not node.keywords:
            value = self.visit(node.args[0])
            if node.func.id in ("abs", "Abs"):
                return _algebra_value("abs", value)
            if node.func.id == "sqrt":
                result = _algebra_value("sqrt", value)
                # Record the real sign alternatives when sqrt(u**2) becomes |u|.
                if result.func is sp.Abs:
                    inner = result.args[0]
                    self.record(node, "radical", sp.Ge(inner, 0), inner, -inner)
                return result
        raise ValueError(f"Unsupported syntax: {ast.dump(node, include_attributes=False)}")


@lru_cache(maxsize=1024)
def _compile_cached(normalized, bindings, transform, collect):
    tree = ast.parse(normalized, mode="eval")
    compiler = _Compiler(normalized, bindings, combine=transform == "together")
    value = compiler.visit(tree.body)
    if transform is not None:
        value = _rewrite(value, transform, collect)
    return value, tuple(compiler.groups)


def clear_caches():
    """Clear LTBA's bounded immutable-result caches for cold benchmarks."""
    _compile_cached.cache_clear()
    _division_parts.cache_clear()
    _division_guards.cache_clear()
    _guarded_factor.cache_clear()
    _algebra_value.cache_clear()


def cache_info():
    return {"formulas": _compile_cached.cache_info()._asdict(),
            "divisions": _division_parts.cache_info()._asdict(),
            "guards": _division_guards.cache_info()._asdict(),
            "algebra": _algebra_value.cache_info()._asdict()}


def compile_text(source, *, bindings=None, transform=None, collect=None):
    """Parse source, simplify locally, and return a factored value and records.

    This common algebra kernel is also the conventional factored benchmark
    baseline. No Python eval or SymPy string parser is used.
    """
    normalized = source.strip().replace("^", "**")
    values = tuple(sorted((name, sp.sympify(value, strict=True)) for name, value in (bindings or {}).items()))
    if transform not in (None, "factor", "expand", "collect", "together", "horner"):
        raise ValueError("Unknown value transform")
    if transform == "collect":
        if not isinstance(collect, str) or not collect.isidentifier():
            raise ValueError("collect requires a symbol name")
        collect = dict(values).get(collect, sp.Symbol(collect, real=True))
    elif collect is not None:
        raise ValueError("collect is only valid with transform='collect'")
    return _compile_cached(normalized, values, transform, collect)


def simplify_text(source, *, storage="flat", bindings=None, transform=None, collect=None):
    """Simplify arithmetic while preserving every visited division occurrence."""
    if storage not in ("flat", "tree"):
        raise ValueError("storage must be 'flat' or 'tree'")
    value, groups = compile_text(source, bindings=bindings, transform=transform, collect=collect)
    records = LTBAExpr(source, groups, ["cas:simplify"])
    if storage == "tree":
        records = records.with_storage("tree")
    return SimplificationResult(value, records)


def solve_equal_text(source, symbol, target=0, *, bindings=None):
    """Solve source directly, avoiding symbolic compilation for supported root audits."""
    from .point_audit import compile_point_audit

    target = sp.sympify(target, strict=True)
    if not bindings and target.is_Rational:
        audit = compile_point_audit(source.replace('^', '**'), symbol)
        if audit is not None:
            return audit.solve_equal(target)
        from .polynomial_audit import compile_polynomial_audit

        polynomial = compile_polynomial_audit(source, symbol)
        if polynomial is not None:
            return polynomial.solve_equal(target)
    return simplify_text(source, bindings=bindings).solve_equal(symbol, target)
