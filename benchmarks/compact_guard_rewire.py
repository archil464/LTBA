"""Compare compact guard updates as formulas enter and leave shared groups."""
import argparse
import json
from pathlib import Path
from random import Random
from statistics import median
from time import perf_counter_ns
from types import MappingProxyType

from benchmarks.workbook_incremental import ConventionalDAG, serialized
from ltba.cas import division_case
from ltba.workbook import Workbook


def shared_dag(formulas, index):
    dag = ConventionalDAG(formulas)
    dag.share_snapshots = True
    dag.identity_sensitive = index
    for field in ('formulas', 'parents', 'children', 'compiled', 'values', 'assumptions'):
        setattr(dag, field, MappingProxyType(getattr(dag, field)))
    return dag


def update_payload(state, previous, revision, edited, ltba):
    reverse = state.reverse_dependencies if ltba else state.children
    payload = {'revision': revision}
    if edited in ('d', 'e'):
        payload['guard'] = {'divisor': edited,
                            'before': division_case(previous.values[edited]),
                            'after': division_case(state.values[edited]),
                            'sites': len(reverse[edited])}
    else:
        old_parents = previous.dependencies if ltba else previous.parents
        new_parents = state.dependencies if ltba else state.parents
        payload['move'] = {'site': edited, 'from': next(iter(old_parents[edited])),
                           'to': next(iter(new_parents[edited]))}
    return serialized(payload)


def run(size, rng):
    formulas = {'d': '0', 'e': '1', **{f'q{i}': f'x{i}/d' for i in range(size)}}
    ltba = Workbook.build(formulas)
    states = {'ltba': ltba, 'dag_shared_snapshots': shared_dag(formulas, ltba.identity_sensitive)}
    cohorts = {'d': set(formulas) - {'d', 'e'}, 'e': set()}
    parents = {site: 'd' for site in cohorts['d']}
    divisors = {'d': 0, 'e': 1}
    samples = {name: {'rewire': [], 'toggle': []} for name in states}
    wire_bytes = {'rewire': [], 'toggle': []}
    for revision in range(1, 73):
        if revision % 2:
            edit = 'rewire'
            site = f'q{rng.randrange(size)}'
            before = parents[site]
            after = 'e' if before == 'd' else 'd'
            source = f'x{site[1:]}/{after}'
            parents[site] = after
            cohorts[before].remove(site)
            cohorts[after].add(site)
            expected = {'revision': revision, 'move': {'site': site, 'from': before, 'to': after}}
        else:
            edit = 'toggle'
            site = rng.choice(('d', 'e'))
            before = divisors[site]
            after = divisors[site] = 1 - before
            source = str(after)
            labels = ('zero-no-op', 'positive-one')
            expected = {'revision': revision, 'guard': {'divisor': site, 'before': labels[before],
                         'after': labels[after], 'sites': len(cohorts[site])}}
        order = list(states)
        rng.shuffle(order)
        for name in order:
            previous = states[name]
            start = perf_counter_ns()
            state = previous.update_many({site: source})
            payload = update_payload(state, previous, revision, site, name == 'ltba')
            elapsed = perf_counter_ns() - start
            if revision > 8:
                samples[name][edit].append(elapsed / 1_000)
            states[name] = state
            assert json.loads(payload) == expected
            assert state.changed == (site,)
            assert state.ranks is previous.ranks
            if name == 'ltba':
                assert state.recomputed == (site,)
            reverse = state.reverse_dependencies if name == 'ltba' else state.children
            assert all(reverse[parent] == members for parent, members in cohorts.items())
            assert all(state.values[q] == previous.values[q] for q in parents)
            # Check occurrence-level provenance after the affected formula moves,
            # and after all affected sites observe the next divisor transition.
            affected = (site,) if edit == 'rewire' else cohorts[site]
            for q in affected:
                divisor = parents[q]
                assert state.compiled[q].local_records[0].branches[divisors[divisor]].tag == (
                    f'division:{("zero-no-op", "positive-one")[divisors[divisor]]}:x{q[1:]}/{divisor}'
                )
        if revision > 8:
            wire_bytes[edit].append(len(payload.encode()))
    assert states['ltba'].to_dict() == Workbook.build(states['ltba'].formulas).to_dict()
    assert states['ltba'].to_dict() == states['dag_shared_snapshots'].to_dict()
    return dict(sites=size, median_us={engine: {kind: median(times) for kind, times in kinds.items()}
                for engine, kinds in samples.items()}, samples_us=samples,
                median_json_bytes={kind: median(sizes) for kind, sizes in wire_bytes.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, help='Optional report from before rank reuse')
    args = parser.parse_args()
    rng = Random(1729)
    rows = []
    for size in (64, 1024, 4096):
        row = run(size, rng)
        rows.append(row)
        print(size, row['median_us'], row['median_json_bytes'], flush=True)
    path = Path('results/compact_guard_rewire/report.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        'verified_timed_edit_pairs': 64 * len(rows),
        'scope': 'Alternating one formula move between two shared divisors and an exact 0/+1 toggle. '
                 'Both engines maintain reverse edges, update the identity shortcut index, use '
                 'the same snapshots and compiler, and encode identical compact JSON. '
                 'The existing topological ranks remain valid for these moves. Setup and validation excluded.',
        'rows': rows,
    }
    if args.before:
        report['before_rank_reuse'] = json.loads(args.before.read_text())
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
