"""Cold-cache unseen edits with exact output verification after every timed call."""
import hashlib
import json
import random
import statistics
import time
from pathlib import Path
import sympy as sp
from sympy.core.cache import clear_cache
from ltba.cas import clear_caches
from ltba.workbook import Workbook, symbol_names
from benchmarks.workbook_incremental import ConventionalDAG, serialized


def main():
    rows = []
    rng = random.Random(1729)
    for scenario in ('isolated', 'local_chain', 'all_dependents', 'zero_transition'):
        formulas = {f'c{i}': str(i + 1) for i in range(1000)}
        if scenario == 'all_dependents':
            formulas = {'root': '1', **{f'c{i}': f'root+{i}' for i in range(1000)}}
        else:
            formulas.update(root='2', out='10/root', tail='out+1')
        states = {mode: Workbook.build(formulas) for mode in ('auto', 'incremental', 'rebuild')}
        conventional = ConventionalDAG(formulas)
        samples = {mode: [] for mode in (*states, 'conventional', 'full_rebuild')}
        for index in range(7):
            key = 'c999' if scenario == 'isolated' else 'root'
            source = str(0 if scenario == 'zero_transition' and index % 2 == 0 else index + 3)
            edits = {key: source}
            old = states['auto'].to_dict()
            formulas = {**formulas, **edits}
            order = list(samples)
            rng.shuffle(order)
            payloads = {}
            for mode in order:
                clear_caches()
                clear_cache()
                symbol_names.cache_clear()
                start = time.perf_counter_ns()
                if mode == 'conventional':
                    result = conventional.update_many(edits)
                    payload = {name: result.cell(name) for name in result.changed}
                elif mode == 'full_rebuild':
                    result = Workbook.build(formulas)
                    full = result.to_dict()
                    payload = {name: cell for name, cell in full.items() if cell != old[name]}
                else:
                    result = states[mode].update_many(edits, strategy=mode)
                    payload = result.delta()['cells']
                encoded = serialized(payload)
                samples[mode].append((time.perf_counter_ns() - start) / 1e6)
                payloads[mode] = encoded
                if mode == 'conventional':
                    conventional = result
                elif mode in states:
                    states[mode] = result
            assert len(set(payloads.values())) == 1
            expected = Workbook.build(formulas).to_dict()
            assert all(state.to_dict() == expected for state in states.values())
            assert conventional.to_dict() == expected
        for mode, times in samples.items():
            rows.append(dict(scenario=scenario, backend=mode, median_ms=statistics.median(times), samples_ms=times))
        print(scenario, {mode: round(statistics.median(times), 3) for mode, times in samples.items()}, flush=True)
    paths = ('ltba/workbook.py', 'ltba/snapshot.py', 'ltba/cas.py', 'benchmarks/workbook_novel.py')
    report = dict(scope='Seven successive unseen numeric edits per scenario, 1000 independent cells or dependents. All arithmetic, syntax and SymPy caches cleared before each timed operation. Includes changed-cell JSON serialization. Initial construction excluded. Comparator shares the arithmetic kernel. Not a released-product comparison.',
                  validated_calls=140, sympy=sp.__version__, rows=rows,
                  source_sha256={p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths})
    path = Path('results/workbook_novel/report.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
