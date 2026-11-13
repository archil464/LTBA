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
]


def simplify_text(source, *, storage="flat", bindings=None, transform=None, collect=None):
    """Load the optional SymPy-backed, guard-preserving simplifier."""
    from .cas import simplify_text as simplify
    return simplify(source, storage=storage, bindings=bindings, transform=transform, collect=collect)

def solve_equal_text(source, symbol, target=0, *, bindings=None):
    """Solve an equality directly from source using the optional CAS."""
    from .cas import solve_equal_text as solve
    return solve(source, symbol, target, bindings=bindings)


# Install a standard set of demo components on import for convenience in examples/tests
try:
    install_default_components()
except Exception:
    # keep import lightweight for tests that only import symbols
    pass
