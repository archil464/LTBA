"""Exact guard-domain checks for supported univariate Piecewise expressions."""

import sympy as sp


def _branch_domains(expression, symbol):
    """Return the domains of the ordered branches, after earlier guards win."""
    if not isinstance(expression, sp.Piecewise) or not isinstance(symbol, sp.Symbol):
        raise TypeError('Expected a Piecewise expression and a Symbol')
    remaining = sp.S.Reals
    for value, guard in expression.args:
        if guard.free_symbols - {symbol} or value.has(sp.Piecewise):
            raise NotImplementedError('Expected univariate guards and non-nested branches')
        domain = guard.as_set()
        active = remaining & domain
        yield value, active
        remaining -= domain
        if remaining is sp.S.EmptySet:
            break


def refine_integer_piecewise(expression, symbol, assumption=sp.true):
    """Use the default branch if it agrees throughout the assumed integer domain.

    The returned expression is valid under the supplied assumption on integers.
    The proof accepts univariate polynomial branches over the rationals.
    """
    assumption = sp.sympify(assumption, strict=True)
    if assumption.free_symbols - {symbol}:
        raise NotImplementedError('Expected a univariate assumption')
    if not isinstance(expression, sp.Piecewise) or expression.args[-1].cond is not sp.true:
        return expression

    candidate = expression.args[-1].expr
    try:
        allowed = assumption.as_set() & sp.S.Integers
        for value, domain in _branch_domains(expression, symbol):
            active = allowed & domain
            if active is sp.S.EmptySet or value == candidate:
                continue
            left = sp.Poly(value, symbol, domain=sp.QQ)
            right = sp.Poly(candidate, symbol, domain=sp.QQ)
            difference = left - right
            if difference.is_zero:
                continue
            roots = sp.FiniteSet(*difference.real_roots(radicals=False))
            if active.is_subset(roots) is not True:
                return expression
    except (NotImplementedError, ValueError, TypeError, sp.PolynomialError, sp.CoercionFailed):
        return expression
    return candidate


def piecewise_side_limit(expression, symbol, point, *, direction):
    """Select the punctured real branch on one side and compute its usual limit."""
    if direction not in ('+', '-'):
        raise ValueError("Expected direction '+' or '-'")
    point = sp.sympify(point, strict=True)
    if point.is_real is not True or point.is_finite is not True or point.free_symbols:
        raise ValueError('Expected a concrete finite real point')
    if not isinstance(symbol, sp.Symbol) or symbol.is_integer is True or symbol.is_real is False:
        raise ValueError('Expected a continuous real variable')
    for value, domain in _branch_domains(expression, symbol):
        parts = domain.args if isinstance(domain, sp.Union) else (domain,)
        for part in parts:
            if part is sp.S.EmptySet or isinstance(part, sp.FiniteSet):
                continue
            if not isinstance(part, sp.Interval):
                raise NotImplementedError('Expected real intervals or isolated points')
            if direction == '+':
                adjacent = sp.And(part.start <= point, point < part.end)
            else:
                adjacent = sp.And(part.start < point, point <= part.end)
            if adjacent is sp.true:
                return sp.limit(value, symbol, point, dir=direction)
            if adjacent is not sp.false:
                raise NotImplementedError('Cannot establish which interval approaches the point')
    raise ValueError('No branch is defined arbitrarily close on the requested side')
