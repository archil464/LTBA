"""Audit univariate rational rewrites under an explicit division-at-zero policy."""
import ast
import json
from pathlib import Path
from random import Random
from statistics import median
from time import perf_counter_ns

import sympy as sp
from sympy.core.cache import clear_cache

from benchmarks.guarded_dag_equivalence import oracle, span
from benchmarks.singular_interactions import conventional
from ltba.cas import clear_caches, simplify_text


X = sp.Symbol('x', real=True)
REALS = sp.S.Reals


def baseline_solve(tree):
    folded = sp.piecewise_fold(conventional(tree))
    if not isinstance(folded, sp.Piecewise):
        return sp.solveset(folded, X, domain=REALS)
    return sp.Union(*(sp.solveset(value, X, domain=domain)
                      for value, domain in folded.as_expr_set_pairs(domain=REALS)))


def audit(original, replacement, engine, witness):
    source = f'({original})-({replacement})'
    tree = ast.parse(source, mode='eval').body
    sites = {span(node) for node in ast.walk(tree)
             if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)}
    if engine == 'ltba':
        compiled = simplify_text(source)
        assert {tuple(map(int, group.group_id.split(':')[1:]))
                for group in compiled.local_records} == sites
        domain = compiled.solve_equal('x')
    else:
        domain = baseline_solve(tree)
    records = {}
    counterexample = None
    if witness is not None:
        left = oracle(source, tree.left, {'x': witness}, records)
        right = oracle(source, tree.right, {'x': witness}, records)
        assert left != right and domain.contains(witness) is sp.false
        counterexample = {'x': witness, 'original': str(left), 'replacement': str(right)}
        assert records.keys() == sites
    return {'valid_on': str(REALS if domain == REALS else domain), 'counterexample': counterexample,
            'division_sites': sorted(sites),
            'active_branches': [{'span': location, 'divisor': guard, 'branch': branch}
                                for location, (guard, branch) in sorted(records.items())]}


def cases():
    yield 'self cancellation', 'x/x', '1', [0], 0
    yield 'removable singularity', '(x*x-1)/(x-1)', 'x+1', [1], 1
    yield 'multiply away divisor', '(7/x)*x', '7', [0], 0
    yield 'nested division', '(6/x)/2', '6/(2*x)', [0], 0
    yield 'common denominator', '1/x+1/2', '(x+2)/(2*x)', [0], 0
    yield 'reciprocal of reciprocal', '1/(1/x)', 'x', [0], 0
    yield 'safe distributivity', '(x+1)*(x-1)', 'x*x-1', [], None
    yield 'safe same divisor', '1/x+2/x', '3/x', [], None
    for n in (2, 4, 8):
        original = '+'.join(f'(x-{i})/(x-{i})' for i in range(n))
        yield f'{n} interacting guards', original, str(n), list(range(n)), 0


def main():
    rng = Random(1729)
    rows = []
    for name, original, replacement, exceptions, witness in cases():
        samples = {'ltba': [], 'sympy_piecewise': []}
        expected_domain = REALS - sp.FiniteSet(*exceptions)
        outputs = {}
        # Check exact symbolic domain equality outside timing.
        source = f'({original})-({replacement})'
        assert simplify_text(source).solve_equal('x') == expected_domain, name
        assert baseline_solve(ast.parse(source, mode='eval').body) == expected_domain, name
        for _ in range(5):
            order = list(samples)
            rng.shuffle(order)
            for engine in order:
                clear_caches()
                clear_cache()
                start = perf_counter_ns()
                outputs[engine] = audit(original, replacement, engine, witness)
                samples[engine].append((perf_counter_ns() - start) / 1e6)
            assert outputs['ltba'] == outputs['sympy_piecewise'], (name, outputs)
        row = dict(case=name, original=original, replacement=replacement,
                   audit=outputs['ltba'], samples_ms=samples,
                   median_ms={engine: median(values) for engine, values in samples.items()})
        rows.append(row)
        print(name, row['median_ms'], flush=True)
    path = Path('results/rewrite_audit/report.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        'scope': 'Exact univariate real formulas with LTBA no-op division. Same equality '
                 'domain, supplied witness verification and per-site report. Witness discovery '
                 'is not timed or automated. Both use the same exact source replay for active '
                 'branches. LTBA additionally constructs its symbolic branch payloads. '
                 'Five cold runs, cache clearing outside timing.',
        'sympy': sp.__version__, 'verified_pairs': 5 * len(rows), 'rows': rows,
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
