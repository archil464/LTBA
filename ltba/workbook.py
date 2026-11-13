"""Persistent workbook snapshots with transactional incremental recalculation.

Real external symbols are the simplification contract. Dependency values that
are not provably real are bound into the source before simplification. Source
provenance is local to each cell and linked through dependency edges.
"""
from __future__ import annotations

import ast
import heapq
from dataclasses import dataclass, field, replace
from functools import lru_cache
from types import MappingProxyType

import sympy as sp

from .cas import groups_to_dict, simplify_text
from .snapshot import snapshot
from collections import ChainMap


@lru_cache(maxsize=2048)
def symbol_names(source):
    tree = ast.parse(source.strip().replace('^', '**'), mode='eval')
    functions = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    return frozenset(node.id for node in ast.walk(tree)
                     if isinstance(node, ast.Name) and id(node) not in functions)


def dependencies(source, names):
    return frozenset(name for name in symbol_names(source) if name in names)



def identity_divisor(source, parents):
    """Identify a quotient whose sole workbook input is its bare divisor."""
    if len(parents) != 1:
        return None
    parent, = parents
    node = ast.parse(source.strip().replace('^', '**'), mode='eval').body
    if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
            and isinstance(node.right, ast.Name) and node.right.id == parent
            and all(not isinstance(part, ast.Name) or part.id != parent
                    for part in ast.walk(node.left))):
        return parent
    return None

def reverse_for(dependencies_by_name):
    reverse = {name: set() for name in dependencies_by_name}
    for name, parents in dependencies_by_name.items():
        for parent in parents:
            reverse[parent].add(name)
    return {name: frozenset(children) for name, children in reverse.items()}


def order_for(dependencies_by_name, reverse=None):
    reverse = reverse_for(dependencies_by_name) if reverse is None else reverse
    remaining = {name: len(parents) for name, parents in dependencies_by_name.items()}
    ready = [name for name, count in remaining.items() if count == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        name = heapq.heappop(ready)
        order.append(name)
        for child in reverse[name]:
            remaining[child] -= 1
            if remaining[child] == 0:
                heapq.heappush(ready, child)
    if len(order) != len(dependencies_by_name):
        raise ValueError('Formula dependency cycle')
    return tuple(order)


@dataclass(frozen=True)
class Assumptions:
    real_external_symbols: tuple
    validated_real_dependencies: tuple
    rebound_dependencies: tuple
    bound_before_simplification: bool

    def to_dict(self):
        return {
            'real_external_symbols': list(self.real_external_symbols),
            'validated_real_dependencies': list(self.validated_real_dependencies),
            'rebound_dependencies': list(self.rebound_dependencies),
            'bound_before_simplification': self.bound_before_simplification,
        }


def compute_cell(source, parents, values):
    bindings = {parent: values[parent] for parent in sorted(parents)}
    unsafe = tuple(name for name, value in bindings.items() if value.is_real is not True)
    bound = bool(unsafe)
    if not bound:
        try:
            compiled = simplify_text(source)
        except ValueError:
            if not bindings:
                raise
            # A named integer exponent can become supported after binding.
            bound = True
    if bound:
        compiled = simplify_text(source, bindings=bindings)
        value = compiled.value
    else:
        replacements = {sp.Symbol(name, real=True): value for name, value in bindings.items()}
        value = compiled.value.xreplace(replacements)
    assumptions = Assumptions(
        tuple(sorted(symbol_names(source) - parents)),
        tuple(name for name in bindings if name not in unsafe), unsafe, bound,
    )
    return compiled, value, assumptions


def equivalent(left, right):
    """Conservative equality, with an exact polynomial check when applicable."""
    if left == right:
        return True
    if left.is_polynomial() and right.is_polynomial():
        return sp.expand(left - right) == 0
    return False


def cell_dict(source, parents, compiled, value, assumptions):
    return {
        'formula': source, 'value': sp.sstr(value),
        'dependencies': sorted(parents),
        'local_provenance': groups_to_dict(compiled.local_records),
        'assumptions': assumptions.to_dict(),
    }


@dataclass(frozen=True)
class Workbook:
    formulas: object
    dependencies: object
    compiled: object
    values: object
    recomputed: tuple
    reverse_dependencies: object
    ranks: object
    assumptions: object
    edited: tuple
    value_changed: tuple
    provenance_changed: tuple
    changed: tuple
    revision: int = 0
    identity_sensitive: object = field(default=None, repr=False)

    @classmethod
    def build(cls, formulas):
        formulas = dict(formulas)
        if any(not name.isidentifier() or name in ('sqrt', 'abs', 'Abs') for name in formulas):
            raise ValueError('Formula names must be identifiers outside the function names')
        deps = {name: dependencies(source, formulas) for name, source in formulas.items()}
        reverse = reverse_for(deps)
        order = order_for(deps, reverse)
        sensitive = {
            name: frozenset(child for child in children
                            if identity_divisor(formulas[child], deps[child]) != name)
            for name, children in reverse.items()
        }
        compiled, values, assumptions = {}, {}, {}
        for name in order:
            compiled[name], values[name], assumptions[name] = compute_cell(formulas[name], deps[name], values)
        return cls(
            MappingProxyType(formulas), MappingProxyType(deps), MappingProxyType(compiled),
            MappingProxyType(values), order, MappingProxyType(reverse),
            MappingProxyType({name: rank for rank, name in enumerate(order)}),
            MappingProxyType(assumptions), order, order, order, order,
            identity_sensitive=MappingProxyType(sensitive),
        )

    def update(self, name, source):
        return self.update_many({name: source})

    def update_many(self, changes, *, strategy="auto"):
        """Commit all edits together, or raise without changing this snapshot.

        Numeric propagation stops at proven equal values. Provenance stays local
        and is linked through dependency names, so upstream provenance changes
        can be resolved without copying their contents through all descendants.
        """
        if strategy not in ("auto", "incremental", "rebuild"):
            raise ValueError("Unknown update strategy")
        changes = dict(changes)
        unknown = [name for name in changes if name not in self.formulas]
        if unknown:
            raise KeyError(sorted(unknown)[0])
        edits = {name: source for name, source in changes.items() if source != self.formulas[name]}
        if not edits:
            return replace(self, recomputed=(), edited=(), value_changed=(),
                           provenance_changed=(), changed=(), revision=self.revision + 1)
        formula_edits, dependency_edits, reverse_edits = {}, {}, {}
        formulas = ChainMap(formula_edits, self.formulas)
        deps = ChainMap(dependency_edits, self.dependencies)
        reverse = ChainMap(reverse_edits, self.reverse_dependencies)
        sensitive_edits = {}
        sensitive = ChainMap(sensitive_edits, self.identity_sensitive or self.reverse_dependencies)
        reorder_needed = False
        for name, source in edits.items():
            new_parents = dependencies(source, formulas)
            old_parents = deps[name]
            # Removing edges cannot invalidate an order. New edges only
            # require validation when they point backward or to themselves.
            reorder_needed |= any(self.ranks[parent] >= self.ranks[name]
                                  for parent in new_parents - old_parents)
            for parent in old_parents - new_parents:
                reverse[parent] = reverse[parent] - {name}
            for parent in new_parents - old_parents:
                reverse[parent] = reverse[parent] | {name}
            previous_identity = identity_divisor(self.formulas[name], old_parents) if self.identity_sensitive is not None else None
            next_identity = identity_divisor(source, new_parents)
            previous_sensitive = old_parents - {previous_identity}
            next_sensitive = new_parents - {next_identity}
            for parent in previous_sensitive - next_sensitive:
                sensitive[parent] = sensitive[parent] - {name}
            for parent in next_sensitive - previous_sensitive:
                sensitive[parent] = sensitive[parent] | {name}
            formulas[name] = source
            if new_parents != old_parents:
                deps[name] = new_parents
        ranks = self.ranks
        if reorder_needed:
            ranks = MappingProxyType({name: index for index, name in enumerate(order_for(deps, reverse))})
        # All candidate maps remain private until the complete transaction succeeds.
        compiled_edits, value_edits, assumption_edits = {}, {}, {}
        compiled = ChainMap(compiled_edits, self.compiled)
        values = ChainMap(value_edits, self.values)
        assumptions = ChainMap(assumption_edits, self.assumptions)
        # The measured fan-out heuristic did not beat incremental scheduling.
        # Keep auto conservative until a validated cost model is available.
        dense = strategy == "rebuild"
        initial = formulas if dense else edits
        queue = [(ranks[name], name) for name in initial]
        heapq.heapify(queue)
        queued = set(initial)
        visited, changed_values, changed_provenance, changed_cells = [], [], [], []
        while queue:
            _, name = heapq.heappop(queue)
            visited.append(name)
            candidate, value, assumption = compute_cell(formulas[name], deps[name], values)
            value_changed = not equivalent(value, self.values[name])
            provenance_changed = (
                name in edits or candidate.local_records != self.compiled[name].local_records
                or assumption != self.assumptions[name]
            )
            if provenance_changed:
                compiled[name], assumptions[name] = candidate, assumption
            # Keep the previous representative of an equivalent value. Consumers
            # can retain their cached expressions and stable rendering.
            if value_changed:
                values[name] = value
            if provenance_changed:
                changed_provenance.append(name)
            if value_changed:
                changed_values.append(name)
                # Both divisors act as the multiplicative identity. The guard
                # still points at this cell, so the client sees the trace change.
                identity_transition = (value in (0, 1) and self.values[name] in (0, 1))
                children = sensitive[name] if identity_transition else reverse[name]
                for child in children:
                    if child not in queued:
                        queued.add(child)
                        heapq.heappush(queue, (ranks[child], child))
            if value_changed or provenance_changed:
                changed_cells.append(name)
        return Workbook(
            snapshot(self.formulas, formula_edits), snapshot(self.dependencies, dependency_edits),
            snapshot(self.compiled, compiled_edits), snapshot(self.values, value_edits), tuple(visited),
            snapshot(self.reverse_dependencies, reverse_edits), ranks,
            snapshot(self.assumptions, assumption_edits), tuple(sorted(edits)), tuple(changed_values),
            tuple(changed_provenance), tuple(changed_cells), self.revision + 1,
            snapshot(self.identity_sensitive or self.reverse_dependencies, sensitive_edits),
        )

    def evaluate(self, name, values):
        substitutions = {}
        for key, value in values.items():
            value = sp.sympify(value, strict=True)
            if value.is_real is not True:
                raise ValueError('External parameter values must be real')
            substitutions[sp.Symbol(key, real=True)] = value
        return self.values[name].subs(substitutions, simultaneous=True)

    def _cell_dict(self, name):
        return cell_dict(self.formulas[name], self.dependencies[name], self.compiled[name],
                         self.values[name], self.assumptions[name])

    def to_dict(self):
        return {name: self._cell_dict(name) for name in sorted(self.formulas)}

    def delta(self):
        """Changed local payloads plus roots of changed provenance for a client DAG."""
        return {
            'base_revision': self.revision - 1 if self.revision else None, 'revision': self.revision,
            'cells': {name: self._cell_dict(name) for name in self.changed},
            'value_changed': list(self.value_changed),
            'provenance_changed': list(self.provenance_changed),
            'recomputed': list(self.recomputed),
        }
