"""Time a shared symbolic denominator edit with exact value and trace checks."""
import json
from pathlib import Path
from random import Random
from statistics import median
from time import perf_counter_ns

import sympy as sp

from benchmarks.workbook_incremental import ConventionalDAG, serialized
from ltba.workbook import Workbook


def run(size, rng):
    formulas = {'d': '0', **{f'q{i}': f'x{i}/d' for i in range(size)}}
    # Warm both systems with both directions before measuring successive edits.
    states = {'ltba_workbook': Workbook.build(formulas), 'conventional_dag': ConventionalDAG(formulas)}
    indexed = ConventionalDAG(formulas)
    # The comparison grants the DAG the same proven edge classification.
    indexed.identity_sensitive = states['ltba_workbook'].identity_sensitive
    states['conventional_dag_with_shortcut'] = indexed
    names = tuple(name for name in formulas if name != 'd')
    expected_values = {name: sp.Symbol(f'x{i}', real=True) for i, name in enumerate(names)}
    samples = {name: [] for name in states}
    for iteration in range(26):
        denominator = 1 - iteration % 2
        edits = {'d': str(denominator)}
        order = list(states)
        rng.shuffle(order)
        outputs = []
        for name in order:
            start = perf_counter_ns()
            state = states[name].update_many(edits)
            if name == 'ltba_workbook':
                payload = state.delta()['cells']
            else:
                payload = {cell: state.cell(cell) for cell in state.changed}
            outputs.append(serialized(payload))
            elapsed = (perf_counter_ns() - start) / 1_000_000
            if iteration >= 2:
                samples[name].append(elapsed)
            states[name] = state
            assert set(payload) == {'d'}
            if name == 'ltba_workbook':
                assert state.recomputed == ('d',)
            assert state.values['d'] == denominator
            for i, cell in enumerate(names):
                assert state.values[cell] == expected_values[cell]
                # Resolve the active guard for the shared denominator.
                # This audit stays outside timing. The delta ships the shared d.
                group = state.compiled[cell].local_records[0]
                assert group.description == f'x{i}/d'
                zero, unit, _ = group.branches
                assert zero.guard.text == 'Eq(d, 0)' and unit.guard.text == 'Eq(d, 1)'
                active = (zero, unit)[int(state.values['d'])]
                tag = 'positive-one' if denominator else 'zero-no-op'
                assert active.tag == f'division:{tag}:x{i}/d'
        assert len(set(outputs)) == 1
    return {'sites': size, 'median_ms': {name: median(times) for name, times in samples.items()},
            'samples_ms': samples, 'changed_payload_cells': 1, 'active_trace_changes_per_edit': size}


def main():
    rng = Random(1729)
    rows = []
    for size in (64, 256, 1024):
        row = run(size, rng)
        rows.append(row)
        print(size, row['median_ms'], flush=True)
    path = Path('results/shared_division_provenance/report.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        'validated_timed_edits': 216,
        'scope': 'Warm alternating shared denominator 0 and +1 with independent symbolic numerators. '
                 'Time includes update and changed-cell JSON. Active trace resolution is checked '
                 'outside timing. Both implementations share the same CAS compiler and use '
                 'dependency references to resolve the active guard. The indexed DAG receives the same '
                 'identity-sensitive edge index at setup. Conventional comparators are prototypes.',
        'rows': rows,
    }
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
