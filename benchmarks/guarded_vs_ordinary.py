"""Compare incremental ordinary division and no-op division on exact chains."""
from fractions import Fraction
import json
from pathlib import Path
from random import Random
from statistics import median
from time import perf_counter_ns

from benchmarks.guarded_product_tree import Chain, RunningProduct, differences, exact_oracle


class OrdinaryProduct(Chain):
    """Track a zero count separately so edits can recover from singular states."""
    def __init__(self, values):
        super().__init__(values)
        self.denominator = 1
        self.zeros = 0
        for d in differences(values):
            if d == 0:
                self.zeros += 1
            else:
                self.denominator *= d

    def update_product(self, delta):
        old = new = 1
        zeros = self.zeros
        for _, before, after in delta:
            if before:
                old *= before
            else:
                zeros -= 1
            if after:
                new *= after
            else:
                zeros += 1
        if old != new:
            self.denominator = self.denominator // old * new
        self.zeros = zeros
        return self.denominator if zeros == 0 else None


class PiecewiseProduct(OrdinaryProduct):
    """Conventional guarded evaluation configured with the no-op rule."""
    def update_product(self, delta):
        super().update_product(delta)
        return self.denominator


def edit(engine, index, value):
    # Same delta construction and Fraction formatting for all three methods.
    start = max(0, index - 1)
    end = min(index + 1, len(engine.values) - 1)
    old = [engine.values[i + 1] - engine.values[i] for i in range(start, end)]
    engine.values[index] = value
    delta = tuple((i, before, after) for i, before in zip(range(start, end), old)
                  if before != (after := engine.values[i + 1] - engine.values[i]))
    denominator = engine.update_product(delta)
    result = None if denominator is None else Fraction(engine.values[0], denominator)
    return result, delta


def workload(size, mixed, rng):
    values = [24]
    for _ in range(size - 1):
        values.append(values[-1] + rng.choice((-3, -2, -1, 1, 2, 3)))
    current = values.copy()
    edits, expected = [], []
    for step in range(300):
        if mixed:
            # Introduce a zero, move its position, then restore the regular chain.
            if step % 3 == 0:
                index = rng.randrange(1, size - 1)
                original = current[index]
            if step % 3 == 2:
                value = original
            else:
                offset = -1 if step % 3 == 0 else 1
                value = current[index + offset]
        else:
            index = rng.randrange(1, size - 1)
            value = current[index] + rng.choice((-3, -2, -1, 1, 2, 3))
            while value in (current[index - 1], current[index + 1]):
                value += 1
        before = current.copy()
        current[index] = value
        delta = tuple((i, a, b) for i, (a, b) in enumerate(
            zip(differences(before), differences(current))) if a != b)
        result = exact_oracle(current)
        expected.append((result, delta, any(d == 0 for d in differences(current))))
        edits.append((index, value))
    return values, edits, expected


def run(size, mixed, rng):
    values, edits, expected = workload(size, mixed, rng)
    engines = {'ltba_running_product': RunningProduct, 'ordinary_incremental': OrdinaryProduct,
               'conventional_guarded': PiecewiseProduct}
    samples = {name: [] for name in engines}
    for _ in range(9):
        order = list(engines)
        rng.shuffle(order)
        for name in order:
            engine = engines[name](values)
            start = perf_counter_ns()
            actual = [edit(engine, *args) for args in edits]
            samples[name].append((perf_counter_ns() - start) / len(edits) / 1000)
            assert actual == [(None if singular and name == 'ordinary_incremental' else result, delta)
                              for result, delta, singular in expected]
    return dict(inputs=size, workload='zero_transitions' if mixed else 'nonzero',
                singular_edits=sum(singular for _, _, singular in expected),
                median_us={name: median(times) for name, times in samples.items()}, samples_us=samples)


def main():
    rng = Random(1729)
    rows = []
    for size in (64, 1024, 8192):
        for mixed in (False, True):
            row = run(size, mixed, rng)
            rows.append(row)
            print(size, row['workload'], row['singular_edits'], row['median_us'], flush=True)
    report = dict(validated_timed_edits=6*3*9*300,
                  scope='Exact integer chains, 9 batches of 300 edits per backend and workload. Times include value and adjacent-difference delta. Setup excluded. Ordinary division returns an undefined marker when any divisor is zero. The guarded comparator implements the no-op rule. Prototype comparators.',
                  rows=rows)
    path = Path('results/guarded_vs_ordinary/report.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
