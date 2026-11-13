"""An immutable balanced sequence for optional LTBA branch storage.

Index replacement shares unaffected subtrees. Iteration and tuple conversion
visit all records. Appending rebuilds the tree, so construct groups in bulk.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from operator import index as integer_index


@dataclass(frozen=True)
class _Leaf:
    value: object
    size: int = 1


@dataclass(frozen=True)
class _Node:
    left: object
    right: object
    size: int


def _build(values, start, stop):
    if start == stop:
        return None
    if stop - start == 1:
        return _Leaf(values[start])
    middle = (start + stop) // 2
    return _Node(_build(values, start, middle), _build(values, middle, stop), stop - start)


def _iterate(node):
    if isinstance(node, _Leaf):
        yield node.value
    elif node is not None:
        yield from _iterate(node.left)
        yield from _iterate(node.right)


def _replace(node, index, value):
    if isinstance(node, _Leaf):
        return _Leaf(value)
    if index < node.left.size:
        return _Node(_replace(node.left, index, value), node.right, node.size)
    return _Node(node.left, _replace(node.right, index - node.left.size, value), node.size)


@dataclass(frozen=True, eq=False)
class BranchTree(Sequence):
    _root: object

    @classmethod
    def from_groups(cls, groups):
        values = tuple(groups)
        return cls(_build(values, 0, len(values)))

    def __len__(self):
        return 0 if self._root is None else self._root.size

    def __iter__(self):
        return _iterate(self._root)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return tuple(self)[index]
        index = integer_index(index)
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        node = self._root
        while isinstance(node, _Node):
            if index < node.left.size:
                node = node.left
            else:
                index -= node.left.size
                node = node.right
        return node.value

    def __eq__(self, other):
        if not isinstance(other, Sequence):
            return NotImplemented
        return len(self) == len(other) and all(a == b for a, b in zip(self, other))

    def set(self, index, value):
        index = integer_index(index)
        if not 0 <= index < len(self):
            raise IndexError(index)
        return BranchTree(_replace(self._root, index, value))

    def append(self, value):
        return BranchTree.from_groups((*self, value))
