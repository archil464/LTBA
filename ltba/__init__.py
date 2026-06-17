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
]

# Install a standard set of demo components on import for convenience in examples/tests
try:
    install_default_components()
except Exception:
    # keep import lightweight for tests that only import symbols
    pass
