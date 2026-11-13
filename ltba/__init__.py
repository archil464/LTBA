"""LTBA package — Locality-Preserving Tagged Branch Algebra prototype.

Public API: Guard, LocalBranch, LTBAExpr, LTBAComponent, registry
"""
from .core import Guard, LocalBranch, LocalBranchGroup, LTBAExpr, LTBAComponent, ComponentRegistry, registry  # re-export
from .components import install_default_components

__all__ = [
    "Guard",
    "LocalBranch",
    "LocalBranchGroup",
    "LTBAExpr",
    "LTBAComponent",
    "ComponentRegistry",
    "registry",
    "install_default_components",
    "simplify_text",
    "solve_equal_text",
    "cancel_ordinary",
    "audit_ordinary_rewrite",
    "refine_integer_piecewise",
    "piecewise_side_limit",
]


def simplify_text(source, *, storage="flat", bindings=None, transform=None, collect=None):
    """Load the optional SymPy-backed, guard-preserving simplifier."""
    from .cas import simplify_text as simplify
    return simplify(source, storage=storage, bindings=bindings, transform=transform, collect=collect)

def solve_equal_text(source, symbol, target=0, *, bindings=None):
    """Solve an equality directly from source using the optional CAS."""
    from .cas import solve_equal_text as solve
    return solve(source, symbol, target, bindings=bindings)


def cancel_ordinary(source, symbol):
    """Cancel a rational expression while carrying its original real domain."""
    from .ordinary_audit import cancel_ordinary as cancel
    return cancel(source, symbol)


def audit_ordinary_rewrite(original, replacement, symbol):
    """Check value equality and changes to the domain under ordinary division."""
    from .ordinary_audit import audit_ordinary_rewrite as audit
    return audit(original, replacement, symbol)


def refine_integer_piecewise(expression, symbol, assumption=True):
    """Refine a Piecewise under an explicit integer-domain assumption."""
    from .piecewise_analysis import refine_integer_piecewise as refine
    return refine(expression, symbol, assumption)


def piecewise_side_limit(expression, symbol, point, *, direction):
    """Compute a one-sided limit from the adjacent Piecewise branch."""
    from .piecewise_analysis import piecewise_side_limit as side_limit
    return side_limit(expression, symbol, point, direction=direction)


# Install a standard set of demo components on import for convenience in examples/tests
try:
    install_default_components()
except Exception:
    # keep import lightweight for tests that only import symbols
    pass
