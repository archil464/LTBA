"""Measure active division trace materialization with shared guard resolution."""
import gc
import json
from pathlib import Path
from random import Random
from statistics import median
from time import perf_counter_ns

import sympy as sp

from ltba.cas import division_case
from ltba.workbook import Workbook


BRANCHES = {'zero-no-op': 0, 'positive-one': 1, 'regular': 2}


def classify(value):
    if value == 0:
        return 0
    if value == 1:
        return 1
    return 2


def run(size, rng):
    formulas = {'d': '0', **{f'q{i}': f'x{i}/d' for i in range(size)}}
    workbook = Workbook.build(formulas)
    sites = tuple(name for name in formulas if name != 'd')
    groups = tuple(workbook.compiled[name].local_records[0] for name in sites)
    assert all(branch.guard is groups[0].branches[i].guard
               for group in groups for i, branch in enumerate(group.branches))
    samples = {'per_site': [], 'shared': []}
    edits = []
    for iteration in range(33):
        divisor = 1 - iteration % 2
        start = perf_counter_ns()
        workbook = workbook.update('d', str(divisor))
        if iteration:
            edits.append((perf_counter_ns() - start) / 1e6)
        assert workbook.recomputed == ('d',)
        assert tuple(workbook.delta()['cells']) == ('d',)
        denominator = workbook.values['d']
        order = list(samples)
        rng.shuffle(order)
        results = {}
        for mode in order:
            gc.disable()
            try:
                start = perf_counter_ns()
                if mode == 'shared':
                    branch = BRANCHES[division_case(denominator)]
                    trace = tuple((group.group_id, group.branches[branch].tag) for group in groups)
                else:
                    trace = tuple((group.group_id, group.branches[classify(denominator)].tag)
                                  for group in groups)
                elapsed = (perf_counter_ns() - start) / 1e6
            finally:
                gc.enable()
            if iteration:
                samples[mode].append(elapsed)
            results[mode] = trace
        assert results['shared'] == results['per_site']
        label = 'positive-one' if divisor else 'zero-no-op'
        assert all(tag.startswith(f'division:{label}:') for _, tag in results['shared'])
        assert all(workbook.values[name] == sp.Symbol(f'x{i}', real=True)
                   for i, name in enumerate(sites))
    return dict(sites=size, median_trace_ms={mode: median(times) for mode, times in samples.items()},
                median_edit_ms=median(edits), trace_samples_ms=samples, edit_samples_ms=edits,
                guard_resolutions_per_trace={'per_site': size, 'shared': 1})


def main():
    rng = Random(1729)
    rows = [run(size, rng) for size in (64, 256, 1024, 4096)]
    for row in rows:
        print(row['sites'], row['median_trace_ms'], row['median_edit_ms'], flush=True)
    path = Path('results/shared_guard_computation/report.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    report = dict(
        verified_timed_trace_pairs=32 * len(rows),
        scope='Warm in-process exact 0/+1 edits. Both trace paths materialize the same '
              'per-site (ID, tag) tuples. The per-site baseline uses direct equality checks. '
              'The shared path resolves the guard once. Workbook edits are timed separately. '
              'Cyclic GC paused during trace timing. No serialization or released-CAS comparison.',
        rows=rows,
    )
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
