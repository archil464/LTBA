"""Benchmark exact integer difference chains under the no-op division rule."""
from fractions import Fraction
from itertools import product
import json
from math import prod
from pathlib import Path
from random import Random
from statistics import median
from time import perf_counter_ns


def guarded_factor(difference):
    return difference if difference != 0 else 1


def differences(values):
    return (right - left for left, right in zip(values, values[1:]))


class Chain:
    def __init__(self, values):
        self.values = list(values)

    def edit(self, index, value):
        start = max(0, index - 1)
        end = min(index + 1, len(self.values) - 1)
        old = [self.values[leaf + 1] - self.values[leaf] for leaf in range(start, end)]
        self.values[index] = value
        delta = tuple((leaf, before, after) for leaf, before in zip(range(start, end), old)
                      if before != (after := self.values[leaf + 1] - self.values[leaf]))
        denominator = self.update_product(delta)
        return Fraction(self.values[0], denominator), delta


class FullScan(Chain):
    def update_product(self, delta):
        return prod(guarded_factor(d) for d in differences(self.values))


class RunningProduct(Chain):
    def __init__(self, values):
        super().__init__(values)
        self.denominator = prod(guarded_factor(d) for d in differences(values))

    def update_product(self, delta):
        old = prod(guarded_factor(before) for _, before, _ in delta)
        new = prod(guarded_factor(after) for _, _, after in delta)
        if old != new:
            self.denominator = (self.denominator // old) * new
        return self.denominator


class ProductTree(Chain):
    def __init__(self, values):
        super().__init__(values)
        self.base = 1 << max(0, (len(values) - 2).bit_length())
        self.nodes = [1] * (2 * self.base)
        for leaf, d in enumerate(differences(values), self.base):
            self.nodes[leaf] = guarded_factor(d)
        for node in range(self.base - 1, 0, -1):
            self.nodes[node] = self.nodes[2 * node] * self.nodes[2 * node + 1]
        self.nodes_updated = 0

    def update_product(self, delta):
        parents = set()
        for leaf, before, after in delta:
            factor = guarded_factor(after)
            if factor != guarded_factor(before):
                node = self.base + leaf
                self.nodes[node] = factor
                if node > 1:
                    parents.add(node // 2)
        self.nodes_updated = 0
        while parents:
            next_parents = set()
            for node in parents:
                value = self.nodes[2 * node] * self.nodes[2 * node + 1]
                self.nodes_updated += 1
                if value != self.nodes[node]:
                    self.nodes[node] = value
                    if node > 1:
                        next_parents.add(node // 2)
            parents = next_parents
        return self.nodes[1]


def exact_oracle(values):
    value = Fraction(values[0])
    for previous, current in zip(values, values[1:]):
        d = current - previous
        if d:
            value /= d
    return value


BACKENDS = {'full_scan': FullScan, 'running_product': RunningProduct, 'product_tree': ProductTree}


def exhaustive():
    checked = 0
    for size in (1, 2, 3, 4, 5):
        for values in product((-2, -1, 0, 1, 2), repeat=size):
            for index in range(size):
                for value in (-2, -1, 0, 1, 2):
                    edited = list(values)
                    edited[index] = value
                    delta = tuple((i, a, b) for i, (a, b) in enumerate(
                        zip(differences(values), differences(edited))) if a != b)
                    expected = exact_oracle(edited), delta
                    for engine in BACKENDS.values():
                        assert engine(values).edit(index, value) == expected
                    checked += 1
    return checked


def run(size, family, rng):
    values = [24]
    step_pool = (-1, 0, 0, 0, 1) if family == 'mostly_units' else (-3, -2, -1, 0, 0, 1, 2, 3)
    for _ in range(size - 1):
        values.append(values[-1] + rng.choice(step_pool))
    tree = ProductTree(values)
    reference = FullScan(values)
    expected, edits = [], []
    zero_transitions = 0
    max_tree_nodes = 0
    initial_bits = tree.nodes[1].bit_length()
    for _ in range(300):
        index = rng.randrange(1, size - 1)
        mode = rng.randrange(3)
        target = (reference.values[index - 1] if mode == 0 else reference.values[index + 1]
                  if mode == 1 else reference.values[index] + rng.choice((-1, 1)))
        edits.append((index, target))
        value, delta = reference.edit(index, target)
        zero_transitions += sum((a == 0) != (b == 0) for _, a, b in delta)
        assert tree.edit(index, target) == (value, delta)
        max_tree_nodes = max(max_tree_nodes, tree.nodes_updated)
        expected.append((value, delta))
    timings = {name: [] for name in BACKENDS}
    build_timings = {name: [] for name in BACKENDS}
    for _ in range(7):
        order = list(BACKENDS)
        rng.shuffle(order)
        for name in order:
            start = perf_counter_ns()
            engine = BACKENDS[name](values)
            build_timings[name].append((perf_counter_ns() - start) / 1_000)
            start = perf_counter_ns()
            actual = [engine.edit(*edit) for edit in edits]
            elapsed = perf_counter_ns() - start
            assert actual == expected
            timings[name].append(elapsed / (len(edits) * 1_000))
    return dict(inputs=size, family=family, initial_product_bits=initial_bits,
                final_product_bits=tree.nodes[1].bit_length(),
                zero_transitions=zero_transitions, max_tree_multiplications=max_tree_nodes,
                median_update_us={name: median(v) for name, v in timings.items()},
                update_samples_us=timings,
                median_build_us={name: median(v) for name, v in build_timings.items()})


def main():
    exhaustive_cases = exhaustive()
    rng = Random(1729)
    rows = []
    for size in (64, 1024, 8192):
        for family in ('mostly_units', 'mixed'):
            row = run(size, family, rng)
            rows.append(row)
            print(size, family, row['median_update_us'], flush=True)
    report = dict(exhaustive_edit_cases=exhaustive_cases, timed_edits=6 * 3 * 7 * 300,
                  scope='Exact integer inputs and Fraction outputs. Edits return final value and raw adjacent-difference delta. Seven batches of 300 successive edits per backend and workload. Construction timed separately. No symbolic rewriting or full provenance serialization.',
                  rows=rows)
    path = Path('results/guarded_product_tree/report.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n')
    print('Exhaustive edit cases:', exhaustive_cases)


if __name__ == '__main__':
    main()
