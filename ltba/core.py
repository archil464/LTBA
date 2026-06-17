"""Core LTBA model types and simple invariants.

This module keeps a compact, well-documented in-memory representation used by
the prototype. It is intentionally small and explicit so reviewers can inspect
semantics without running generation scripts.

Invariants (informal):
- `Guard` is an atomic, opaque label identifying a Boolean condition.
- `LocalBranch` pairs a `Guard` with an algebraic `value` and an optional `tag`.
- `LTBAExpr` stores a base algebraic `base` string plus a flat list of local
  branches attached to that algebraic term. Local branches are not expanded
  into a global product until materialized by explicit conversion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List


@dataclass(frozen=True)
class Guard:
    """Atomic guard label.

    Guards are treated as opaque identifiers for provenance and grouping. They
    are not evaluated by this prototype; satisfiability and arithmetic
    semantics are out of scope.
    """
    text: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.text


@dataclass(frozen=True)
class LocalBranch:
    """A single local branch record attached to an algebraic factor.

    Attributes:
    - guard: Guard labeling the condition for this branch.
    - value: string representing the algebraic payload for this branch.
    - tag: optional short provenance tag used by components.
    """
    guard: Guard
    value: str
    tag: str = ""


@dataclass
class LTBAExpr:
    """A minimal LTBA expression.

    The prototype keeps `base` (human-readable algebraic text) and a flat list
    of `LocalBranch` records. This intentionally avoids any global product
    construction; callers may materialize explicitly via helpers.
    """
    base: str
    branches: List[LocalBranch] = field(default_factory=list)
    provenance: List[str] = field(default_factory=list)

    def add_branch(self, guard: str, value: str, tag: str = "") -> "LTBAExpr":
        """Append a local branch and return self for convenience."""
        self.branches.append(LocalBranch(Guard(guard), value, tag))
        return self

    @property
    def guard_count(self) -> int:
        return len({b.guard for b in self.branches})

    @property
    def local_branch_count(self) -> int:
        return len(self.branches)

    @property
    def explicit_branch_upper_bound(self) -> int:
        """Conservative upper bound on full explicit branches (2^guards).

        This is a coarse metric used in benchmarks; real branch counts depend
        on local groupings and arities.
        """
        return 2 ** self.guard_count

    @property
    def representation_size(self) -> int:
        return len(self.base) + sum(len(str(b.guard)) + len(b.value) + len(b.tag) for b in self.branches)

    def rewrite_local(self, index: int, new_value: str, reason: str) -> "LTBAExpr":
        """Return a new LTBAExpr with one local branch value changed.

        The prototype models locality by allowing O(1)-style replacement of a
        single local branch record; provenance records such operations.
        """
        if index < 0 or index >= len(self.branches):
            raise IndexError("branch index out of range")
        new = LTBAExpr(self.base, list(self.branches), list(self.provenance))
        old = new.branches[index]
        new.branches[index] = LocalBranch(old.guard, new_value, old.tag)
        new.provenance.append(f"local_rewrite:{index}:{reason}")
        return new

    def metric_row(self, family: str, n: int, backend: str = "ltba") -> Dict[str, object]:
        return {
            "family": family,
            "n": n,
            "backend": backend,
            "repr_size": self.representation_size,
            "guard_count": self.guard_count,
            "local_branch_count": self.local_branch_count,
            "explicit_branch_upper_bound": self.explicit_branch_upper_bound,
            "provenance_len": len(self.provenance),
        }


@dataclass(frozen=True)
class LTBAComponent:
    """Named component producing LTBAExpr instances for benchmarks/examples."""

    name: str
    layer: str
    description: str
    make_family: Callable[[int], LTBAExpr]


class ComponentRegistry:
    """Simple registry for demo components.

    This is intentionally minimal; reviewers can inspect what families exist
    and how they are constructed.
    """

    def __init__(self) -> None:
        self._items: Dict[str, LTBAComponent] = {}

    def register(self, component: LTBAComponent) -> None:
        self._items[component.name] = component

    def get(self, name: str) -> LTBAComponent:
        return self._items[name]

    def names(self) -> List[str]:
        return sorted(self._items)

    def values(self) -> Iterable[LTBAComponent]:
        return [self._items[k] for k in self.names()]


registry = ComponentRegistry()
