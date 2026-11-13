"""Benchmark the dependency-closed arithmetic subset of the published EENRON archive."""
import argparse
import ast
from collections import Counter, deque
import cProfile
from fractions import Fraction
import hashlib
from io import BytesIO
import json
from pathlib import Path
import pstats
from random import Random
import re
from statistics import median
from time import perf_counter_ns
from types import MappingProxyType
from zipfile import ZipFile

from openpyxl import load_workbook
import sympy as sp

from benchmarks.workbook_incremental import ConventionalDAG, serialized
from ltba.workbook import Workbook


CELL = re.compile(r'\b[A-Z]{1,3}[1-9][0-9]*\b')


def parse_cell(source):
    if not re.fullmatch(r'[A-Z0-9.$ +*/()\-]+', source):
        raise ValueError
    source = source.replace('$', '').strip()
    tree = ast.parse(source, mode='eval').body
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and CELL.fullmatch(node.id):
            continue
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            continue
        if isinstance(node, (ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub,
                             ast.Mult, ast.Div, ast.UAdd, ast.USub, ast.Load)):
            continue
        raise ValueError
    return source, tree, {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def sheets(archive):
    for name in sorted(archive.namelist()):
        if not name.lower().endswith('.xlsx') or '/~$' in name:
            continue
        workbook = load_workbook(BytesIO(archive.read(name)), read_only=True, data_only=False)
        try:
            for sheet_index, sheet in enumerate(workbook.worksheets):
                candidates, counts, literals = {}, Counter(), {}
                for row in sheet.iter_rows():
                    for cell in row:
                        if cell.data_type == 'f':
                            counts['formula_cells'] += 1
                            try:
                                if not isinstance(cell.value, str):
                                    raise ValueError
                                candidates[cell.coordinate] = parse_cell(cell.value[1:])
                            except (SyntaxError, ValueError):
                                counts['unsupported_syntax'] += 1
                        elif cell.data_type == 'n' and type(cell.value) in (int, float):
                            literals[cell.coordinate] = str(cell.value)
                if not counts['formula_cells']:
                    continue
                # An unresolved dependency stays unresolved. Never replace a
                # formula, text cell, blank, or external reference with zero.
                waiting, edges = {}, {}
                for cell, (_, _, parents) in candidates.items():
                    waiting[cell] = len(parents - literals.keys())
                    for parent in parents:
                        edges.setdefault(parent, []).append(cell)
                ready = deque(sorted(cell for cell, n in waiting.items() if not n))
                formulas, trees, inputs = {}, {}, set()
                while ready:
                    cell = ready.popleft()
                    source, tree, parents = candidates[cell]
                    formulas[cell], trees[cell] = source, tree
                    inputs.update(parents & literals.keys())
                    for child in edges.get(cell, ()):
                        waiting[child] -= 1
                        if not waiting[child]:
                            ready.append(child)
                counts['supported'] = len(formulas)
                counts['unresolved_dependency'] = len(candidates) - len(formulas)
                yield (Path(name).name, sheet_index, counts,
                       {key: literals[key] for key in sorted(inputs)}, formulas, trees)
        finally:
            workbook.close()


def evaluate(node, source, values, zero_sites):
    if isinstance(node, ast.Name):
        return values[node.id]
    if isinstance(node, ast.Constant):
        return Fraction(ast.get_source_segment(source, node))
    if isinstance(node, ast.UnaryOp):
        value = evaluate(node.operand, source, values, zero_sites)
        return -value if isinstance(node.op, ast.USub) else value
    a = evaluate(node.left, source, values, zero_sites)
    b = evaluate(node.right, source, values, zero_sites)
    if isinstance(node.op, ast.Add):
        return a + b
    if isinstance(node.op, ast.Sub):
        return a - b
    if isinstance(node.op, ast.Mult):
        return a * b
    if not b:
        zero_sites.append(None)
        return a
    return a / b


def run(item, rng):
    file, sheet, _, inputs, formulas, trees = item
    original = {**inputs, **formulas}
    ltba = Workbook.build(original)
    dag = ConventionalDAG(original)
    dag.share_snapshots = True
    dag.identity_sensitive = ltba.identity_sensitive
    for field in ('formulas', 'parents', 'children', 'compiled', 'values', 'assumptions'):
        setattr(dag, field, MappingProxyType(getattr(dag, field)))
    states = {'ltba': ltba, 'dag': dag, 'dag_default': ConventionalDAG(original)}
    visits, samples, zero_counts, edits = [], {name: [] for name in states}, [], []
    baseline_order = Random(1730)
    delta_digest = hashlib.sha256()
    current = {name: Fraction(value) for name, value in inputs.items()}
    targets = list(inputs)
    for _ in range(40):
        name = rng.choice(targets)
        current[name] += rng.choice((-1, 1))
        value = current[name]
        changes = {name: str(value) if value.denominator == 1
                   else f'{value.numerator}/{value.denominator}'}
        edits.append(changes)
        oracle, zero_sites = current.copy(), []
        for cell, source in formulas.items():
            oracle[cell] = evaluate(trees[cell], source, oracle, zero_sites)
        zero_counts.append(len(zero_sites))
        expected = {key: sp.Rational(v.numerator, v.denominator) for key, v in oracle.items()}
        order = ['ltba', 'dag']
        rng.shuffle(order)
        order.insert(baseline_order.randrange(3), 'dag_default')
        outputs = {}
        for engine in order:
            start = perf_counter_ns()
            state = states[engine].update_many(changes)
            delta = (state.delta()['cells'] if engine == 'ltba'
                     else {key: state.cell(key) for key in state.changed})
            outputs[engine] = serialized(delta)
            samples[engine].append((perf_counter_ns() - start) / 1e6)
            states[engine] = state
            assert state.values == expected, (file, sheet, engine)
            if engine == 'ltba':
                visits.append(len(state.recomputed))
        assert len(set(outputs.values())) == 1, (file, sheet)
        delta_digest.update(outputs['ltba'].encode() + b'\n')
    assert states['ltba'].to_dict() == Workbook.build(states['ltba'].formulas).to_dict()

    def replay():
        state = ltba
        for change in edits:
            state = state.update_many(change)
            serialized(state.delta()['cells'])

    profile = cProfile.Profile()
    profile.runcall(replay)
    timings = pstats.Stats(profile)
    top = sorted(timings.stats.items(), key=lambda item: item[1][3], reverse=True)
    return dict(file=file, sheet=sheet, inputs=len(inputs), formulas=len(formulas),
                median_ms={name: median(times) for name, times in samples.items()},
                samples_ms=samples, delta_sha256=delta_digest.hexdigest(), median_recomputed=median(visits), max_recomputed=max(visits),
                zero_divisions_seen=max(zero_counts),
                profile=[{'file': Path(key[0]).name, 'function': key[2], 'cumulative_s': stats[3],
                          'self_s': stats[2]} for key, stats in top[:25]])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    with ZipFile(args.archive) as archive:
        inventory = list(sheets(archive))
        file_count = sum(name.lower().endswith('.xlsx') and '/~$' not in name
                         for name in archive.namelist())
    counts = sum((entry[2] for entry in inventory), Counter())
    print('coverage', file_count, len(inventory), dict(counts), flush=True)
    # Rank sheets by eligible formula count, then take one per workbook.
    ranked = sorted(inventory, key=lambda item: (-len(item[4]), item[0], item[1]))
    seen, rows, rng = set(), [], Random(1729)
    for item in ranked:
        if item[0] in seen or not item[3] or len(item[4]) < 10:
            continue
        seen.add(item[0])
        row = run(item, rng)
        rows.append(row)
        print(row['file'], row['formulas'], row['median_ms'], flush=True)
        if len(rows) == 5:
            break
    report = dict(
        source='https://spreadsheet-research.github.io/Metric-based-Fault-Prediction-for-Spreadsheets/datasets/used_for_evaluation/EENRON.zip',
        sha256=hashlib.sha256(args.archive.read_bytes()).hexdigest(),
        xlsx_files=file_count, formula_sheets=len(inventory), coverage=dict(counts), rows=rows,
        scope='Same-sheet numeric cells and + - * / only, dependency closed. Five largest eligible '
              'sheets from distinct files. Forty seeded successive +/-1 edits each. Same exact '
              'LTBA division semantics and changed-cell JSON in all three configurations. The default DAG '
              'copies dictionaries and has no identity-transition index. Independent Fraction '
              'oracle checks all values. Generated edits and adapter are ours; no Excel timing.',
    )
    path = Path('results/enron_workbook/report.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
