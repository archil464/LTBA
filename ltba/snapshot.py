"""Bounded immutable mapping overlays for sparse workbook transactions."""
from collections.abc import Mapping
from types import MappingProxyType


class SnapshotMap(Mapping):
    """Share unchanged entries, compact after 16 generations or dense edits."""
    __slots__ = ('_base', '_changes', '_size', 'depth')

    def __init__(self, base, changes):
        depth = getattr(base, 'depth', 0) + 1
        base_size = len(base)
        if depth > 16 or len(changes) > base_size // 2:
            layers = []
            while isinstance(base, SnapshotMap):
                layers.append(base._changes)
                base = base._base
            merged = dict(base)
            for layer in reversed(layers):
                merged.update(layer)
            merged.update(changes)
            base = MappingProxyType(merged)
            changes = {}
            depth = 0
            base_size = len(merged)
        self._base = base if isinstance(base, (SnapshotMap, MappingProxyType)) else MappingProxyType(dict(base))
        self._changes = MappingProxyType(dict(changes))
        self._size = base_size + sum(key not in self._base for key in self._changes)
        self.depth = depth

    def __getitem__(self, key):
        try:
            return self._changes[key]
        except KeyError:
            return self._base[key]

    def __iter__(self):
        yield from self._base
        yield from (key for key in self._changes if key not in self._base)

    def __len__(self):
        return self._size


def snapshot(base, changes):
    return SnapshotMap(base, changes) if changes else base
