"""Compare compact division updates on a fixed shared-denominator graph."""
from dataclasses import asdict, dataclass
import gc
import json
from pathlib import Path
from random import Random
from statistics import median
from time import perf_counter_ns

import sympy as sp

from benchmarks.workbook_incremental import ConventionalDAG
from ltba.cas import division_case
from ltba.workbook import Workbook


BRANCH_INDEX = {'zero-no-op': 0, 'positive-one': 1}


@dataclass(frozen=True)
class GuardUpdate:
    cohort: str
    revision: int
    before: str
    after: str
    affected_sites: int


class TraceIndex:
    """A fixed site registry shared across revisions of this experiment."""

    def __init__(self, compiled, sites):
        self.sites = {name: compiled[name].local_records[0] for name in sites}

    def update(self, revision, before, after):
        return GuardUpdate('d', revision, division_case(before), division_case(after), len(self.sites))

    def lookup(self, update, name):
        group = self.sites[name]
        return (name, group.group_id, group.branches[BRANCH_INDEX[update.before]].tag,
                group.branches[BRANCH_INDEX[update.after]].tag)

    def expand(self, update):
        before, after = BRANCH_INDEX[update.before], BRANCH_INDEX[update.after]
        return tuple((name, group.group_id, group.branches[before].tag, group.branches[after].tag)
                     for name, group in self.sites.items())


def run(size, rng):
    sites = tuple(f'q{i}' for i in range(size))
    formulas = {'d': '0', **{name: f'x{i}/d' for i, name in enumerate(sites)}}
    states = {'ltba': Workbook.build(formulas), 'conventional_indexed_dag': ConventionalDAG(formulas)}
    states['conventional_indexed_dag'].identity_sensitive = states['ltba'].identity_sensitive
    indexes = {name: TraceIndex(state.compiled, sites) for name, state in states.items()}
    expected_values = {name: sp.Symbol(f'x{i}', real=True) for i, name in enumerate(sites)}
    operations = ('compact_edit', 'lookup', 'expand')
    samples = {name: {operation: [] for operation in operations} for name in states}
    compact_sizes, expanded_sizes = [], []
    previous_gc = gc.isenabled()
    gc.disable()
    try:
        for revision in range(1, 35):
            new = revision % 2
            before, after = ('zero-no-op', 'positive-one') if new else ('positive-one', 'zero-no-op')
            selected = rng.randrange(size)
            edits = {'d': str(new)}
            order = list(states)
            rng.shuffle(order)
            results = {}
            for name in order:
                old_state, index = states[name], indexes[name]
                start = perf_counter_ns()
                state = old_state.update_many(edits)
                update = index.update(revision, old_state.values['d'], state.values['d'])
                encoded = json.dumps(asdict(update), separators=(',', ':'))
                edit_ns = perf_counter_ns() - start
                # Batch independent lookups to reduce sub-microsecond timer noise.
                start = perf_counter_ns()
                for _ in range(128):
                    record = index.lookup(update, sites[selected])
                lookup_ns = (perf_counter_ns() - start) / 128
                start = perf_counter_ns()
                trace = index.expand(update)
                expand_ns = perf_counter_ns() - start
                if revision > 2:
                    for operation, duration in zip(operations, (edit_ns, lookup_ns, expand_ns)):
                        samples[name][operation].append(duration / 1000)
                results[name] = encoded, record, trace
                states[name] = state
                assert state.values['d'] == new and old_state.values['d'] == 1 - new
                assert all(state.values[cell] == value for cell, value in expected_values.items())
                assert state.changed == ('d',)
                if name == 'ltba':
                    assert state.recomputed == ('d',)
            assert results['ltba'] == results['conventional_indexed_dag']
            encoded, record, trace = results['ltba']
            expected = tuple(
                (site, 'division:1:0:1:' + str(len(f'x{i}/d')),
                 f'division:{before}:x{i}/d', f'division:{after}:x{i}/d')
                for i, site in enumerate(sites)
            )
            assert trace == expected and record == expected[selected]
            assert json.loads(encoded) == {
                'cohort': 'd', 'revision': revision, 'before': before, 'after': after,
                'affected_sites': size,
            }
            if revision > 2:
                compact_sizes.append(len(encoded.encode()))
                expanded_sizes.append(len(json.dumps(trace, separators=(',', ':')).encode()))
    finally:
        if previous_gc:
            gc.enable()
    return {
        'sites': size,
        'median_us': {name: {op: median(values) for op, values in timings.items()}
                      for name, timings in samples.items()},
        'samples_us': samples,
        'median_compact_json_bytes': median(compact_sizes),
        'median_expanded_trace_json_bytes': median(expanded_sizes),
    }


def main():
    rng = Random(1729)
    rows = []
    for size in (64, 256, 1024, 4096):
        row = run(size, rng)
        rows.append(row)
        print(size, row['median_us'], row['median_compact_json_bytes'],
              row['median_expanded_trace_json_bytes'], flush=True)
    report = {
        'verified_timed_edit_pairs': 32 * len(rows),
        'scope': 'Fixed graph, alternating exact 0/+1. Both engines use the same site index, '
                 'identity shortcut, and compact schema. Edit includes compact JSON encoding. '
                 'Lookup and full expansion return in-memory records. Setup and validation '
                 'are excluded; cyclic GC is paused during the run. Conventional DAG copies '
                 'its snapshot dictionaries on update. The cohort registry is pre-established.',
        'rows': rows,
    }
    path = Path('results/compact_guard_update/report.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
