"""Compare transactional LTBA updates with a conventional cached dependency DAG.

Both incremental engines use copy-on-write snapshots, equality-based stopping,
identical arithmetic caches and assumption validation, and the same output schema.
The independent comparator uses Python's TopologicalSorter. Timings represent
repeated edits in a warm process, including changed-result or full serialization.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import heapq
import json
import platform
import random
import statistics
import time
from collections import ChainMap
from graphlib import TopologicalSorter
from types import MappingProxyType
from pathlib import Path

import sympy as sp

from ltba.cas import cache_info, clear_caches
from ltba.snapshot import snapshot
from ltba.workbook import Workbook, cell_dict, compute_cell, dependencies, equivalent, identity_divisor, reverse_for


class ConventionalDAG:
    """Conventional dirty-node propagation with cached results and snapshots."""

    def __init__(self, formulas):
        self.formulas = dict(formulas)
        self.parents = {name: dependencies(source, formulas) for name, source in formulas.items()}
        self.children = reverse_for(self.parents)
        order = tuple(TopologicalSorter(self.parents).static_order())
        self.ranks = {name: index for index, name in enumerate(order)}
        self.compiled, self.values, self.assumptions = {}, {}, {}
        for name in order:
            self.compiled[name], self.values[name], self.assumptions[name] = compute_cell(
                self.formulas[name], self.parents[name], self.values)
        self.changed = tuple(order)

    def update_many(self, changes):
        sharing = getattr(self, 'share_snapshots', False)
        unknown = [name for name in changes if name not in self.formulas]
        if unknown:
            raise KeyError(sorted(unknown)[0])
        edited = {name: source for name, source in changes.items() if source != self.formulas[name]}
        candidate = object.__new__(ConventionalDAG)
        fields = ('formulas', 'parents', 'children', 'compiled', 'values', 'assumptions')
        candidate.share_snapshots = sharing
        for field in fields:
            base = getattr(self, field)
            setattr(candidate, field, ChainMap({}, base) if sharing else dict(base))
        candidate.ranks = self.ranks
        candidate.identity_sensitive = getattr(self, "identity_sensitive", None)
        sensitivity = ChainMap({}, candidate.identity_sensitive) if sharing and candidate.identity_sensitive is not None else None
        rewired = False
        reorder_needed = False
        for name, source in edited.items():
            parents = dependencies(source, self.formulas)
            previous = self.parents[name]
            if sensitivity is not None:
                before = previous - {identity_divisor(self.formulas[name], previous)}
                after = parents - {identity_divisor(source, parents)}
                for parent in before - after:
                    sensitivity[parent] = sensitivity[parent] - {name}
                for parent in after - before:
                    sensitivity[parent] = sensitivity[parent] | {name}
            candidate.formulas[name] = source
            if parents != previous or not sharing:
                candidate.parents[name] = parents
            rewired |= parents != previous
            reorder_needed |= any(self.ranks[parent] >= self.ranks[name]
                                  for parent in parents - previous)
            for parent in previous - parents:
                candidate.children[parent] = candidate.children[parent] - {name}
            for parent in parents - previous:
                candidate.children[parent] = candidate.children[parent] | {name}
        if reorder_needed:
            order = tuple(TopologicalSorter(candidate.parents).static_order())
            ranks = {name: index for index, name in enumerate(order)}
            candidate.ranks = MappingProxyType(ranks) if sharing else ranks
        pending = [(candidate.ranks[name], name) for name in edited]
        heapq.heapify(pending)
        enqueued = set(edited)
        changed = []
        while pending:
            _, name = heapq.heappop(pending)
            compiled, value, assumption = compute_cell(candidate.formulas[name], candidate.parents[name], candidate.values)
            numeric_change = not equivalent(value, self.values[name])
            metadata_change = (name in edited or compiled.local_records != self.compiled[name].local_records
                               or assumption != self.assumptions[name])
            if metadata_change or not sharing:
                candidate.compiled[name] = compiled
                candidate.assumptions[name] = assumption
            if numeric_change or not sharing:
                candidate.values[name] = value if numeric_change else self.values[name]
            if numeric_change or metadata_change:
                changed.append(name)
            if numeric_change:
                children = candidate.children[name]
                if sensitivity is not None and value in (0, 1) and self.values[name] in (0, 1):
                    children = sensitivity[name]
                elif (candidate.identity_sensitive is not None and not rewired
                        and not any(cell in children for cell in edited)
                        and value in (0, 1) and self.values[name] in (0, 1)):
                    children = candidate.identity_sensitive[name]
                for child in children:
                    if child not in enqueued:
                        heapq.heappush(pending, (candidate.ranks[child], child))
                        enqueued.add(child)
        candidate.changed = tuple(changed)
        if sharing:
            for field in fields:
                changes_map, base = getattr(candidate, field).maps
                setattr(candidate, field, snapshot(base, changes_map))
            if sensitivity is not None:
                candidate.identity_sensitive = snapshot(sensitivity.maps[1], sensitivity.maps[0])
        elif rewired or any(candidate.parents[cell] for cell in edited):
            candidate.identity_sensitive = None
        return candidate

    def to_dict(self):
        return {name: self.cell(name) for name in sorted(self.formulas)}

    def cell(self, name):
        return cell_dict(self.formulas[name], self.parents[name], self.compiled[name],
                         self.values[name], self.assumptions[name])


def fixture(size, scenario):
    formulas = {f'f{i:04d}': f'(x{i}^2-1)/(x{i}-1)' for i in range(size)}
    formulas.update({'out': 'f0000+1', 'tail': 'out/out'})
    changes = {'f0000': '(x0^2-4)/(x0-2)'}
    if scenario == 'isolated':
        name = f'f{size-1:04d}'
        changes = {name: f'(x{size-1}^2-4)/(x{size-1}-2)'}
    elif scenario == 'equal_value':
        changes = {'f0000': '(x0^2-1)/(x0-1)+0'}
    elif scenario == 'batch_diamond':
        formulas['out'] = 'f0000+f0001'
        changes['f0001'] = '(x1^2-4)/(x1-2)'
    elif scenario == 'stopping_child':
        formulas['out'] = 'f0000-f0000'
        formulas['tail'] = 'out+1'
    elif scenario == 'rewire':
        changes = {'out': 'f0001+1'}
    elif scenario == 'all_dependents':
        formulas = {'root': '1', **{f'f{i:04d}': f'root+{i}' for i in range(size)}}
        changes = {'root': '2'}
    return formulas, changes


def serialized(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'))


def run_case(size, scenario, repeats, seed):
    formulas, edits = fixture(size, scenario)
    clear_caches()
    ltba = Workbook.build(formulas)
    conventional = ConventionalDAG(formulas)
    old_payload = ltba.to_dict()
    assert old_payload == conventional.to_dict()
    updated_formulas = {**formulas, **edits}
    rebuilt_payload = Workbook.build(updated_formulas).to_dict()
    changed_names = [name for name in rebuilt_payload if rebuilt_payload[name] != old_payload[name]]
    expected_delta = {name: rebuilt_payload[name] for name in changed_names}
    updated = ltba.update_many(edits)
    assert updated.to_dict() == rebuilt_payload
    assert updated.delta()['cells'] == expected_delta
    assert conventional.update_many(edits).to_dict() == rebuilt_payload

    def ltba_run(mode):
        result = ltba.update_many(edits)
        return serialized(result.delta()['cells'] if mode == 'delta' else result.to_dict())

    def conventional_run(mode):
        result = conventional.update_many(edits)
        payload = {name: result.cell(name) for name in result.changed} if mode == 'delta' else result.to_dict()
        return serialized(payload)

    def rebuild_run(mode):
        result = Workbook.build(updated_formulas).to_dict()
        payload = {name: record for name, record in result.items() if record != old_payload[name]} if mode == 'delta' else result
        return serialized(payload)

    jobs = {'ltba_incremental': ltba_run, 'conventional_cached_dag': conventional_run, 'full_rebuild': rebuild_run}
    rows = []
    rng = random.Random(seed)
    for mode in ('delta', 'full'):
        expected = serialized(expected_delta if mode == 'delta' else rebuilt_payload)
        for job in jobs.values():
            assert job(mode) == expected
        samples = {name: [] for name in jobs}
        for _ in range(repeats):
            order = list(jobs)
            rng.shuffle(order)
            for name in order:
                start = time.perf_counter_ns()
                result = jobs[name](mode)
                elapsed = (time.perf_counter_ns() - start) / 1e6
                assert result == expected
                samples[name].append(elapsed)
        for name, values in samples.items():
            quartiles = statistics.quantiles(values, n=4)
            rows.append({'scenario': scenario, 'formulas': len(formulas), 'backend': name, 'output': mode,
                         'median_ms': statistics.median(values), 'q1_ms': quartiles[0], 'q3_ms': quartiles[2],
                         'samples_ms': values, 'output_bytes': len(expected.encode()),
                         'ltba_recomputed': len(updated.recomputed), 'changed_cells': len(expected_delta)})
    assert ltba.to_dict() == old_payload
    assert conventional.to_dict() == old_payload
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', default='100,1000')
    parser.add_argument('--repeats', type=int, default=9)
    parser.add_argument('--seed', type=int, default=1729)
    parser.add_argument('--output', type=Path, default=Path('results/workbook_incremental'))
    args = parser.parse_args()
    sizes = [int(item) for item in args.sizes.split(',')]
    if min(sizes) < 2 or args.repeats < 3:
        parser.error('Use sizes >= 2 and repeats >= 3')
    rows = []
    scenarios = ('isolated', 'local_chain', 'equal_value', 'batch_diamond', 'stopping_child', 'rewire', 'all_dependents')
    for size in sizes:
        for scenario in scenarios:
            rows.extend(run_case(size, scenario, args.repeats, args.seed))
            print(f'measured {scenario}, size={size}', flush=True)
    repository = Path(__file__).resolve().parents[1]
    paths = ('ltba/workbook.py', 'ltba/cas.py', 'benchmarks/workbook_incremental.py')
    report = {
        'benchmark': 'Transactional incremental workbook v2',
        'configuration': {**vars(args), 'output': str(args.output)},
        'environment': {'python': platform.python_version(), 'sympy': sp.__version__, 'platform': platform.platform()},
        'source_sha256': {name: hashlib.sha256((repository / name).read_bytes()).hexdigest() for name in paths},
        'correctness': 'All timed results equal fresh rebuild output, including complete provenance and assumptions. Original snapshots preserved.',
        'scope': 'Repeated edits with warm bounded LTBA and SymPy caches. Both incremental backends use conservative equality stopping, cached graphs, copy-on-write snapshots, and shared arithmetic and rendering. Delta timing includes computing changed cells and serializing their payloads. Full rebuild computes changes by comparing all output records. Application imports and initial construction are outside timing. Conventional comparator is an independently implemented standard dependency-DAG prototype, not a benchmark of a released competitor product.',
        'cache_info_at_end': cache_info(),
        'rows': rows,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    with (args.output / 'summary.csv').open('w', newline='') as stream:
        columns = [name for name in rows[0] if name != 'samples_ms']
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'rows': len(rows), 'validated_timed_calls': len(rows)*args.repeats}))


if __name__ == '__main__':
    main()
