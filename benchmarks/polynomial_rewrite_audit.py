"""Compare LTBA and root partitioning beyond proportional affine sums."""
import argparse
import ast
from fractions import Fraction
import json
from pathlib import Path
from random import Random
from statistics import median
import subprocess
import sys
from time import perf_counter

import sympy as sp

from benchmarks.guarded_dag_equivalence import oracle, span
from benchmarks.rewrite_audit_scale import balanced_sum
from ltba.cas import simplify_text
from ltba.polynomial_audit import compile_polynomial_audit


X = sp.Symbol('x', real=True)
REALS = sp.S.Reals


def fixture(family, size):
    if family == 'nonconstant_quotient':
        terms = [f'((x*x-{i*i})/(x-{i}))' for i in range(1, size + 1)]
        target = f'({size}*x+{size*(size+1)//2})'
        expected = list(range(1, size + 1))
    else:
        terms = [f'(((x-{i})*(x+{i}))/((x-{i})*(x+{i})))' for i in range(1, size + 1)]
        target = str(size)
        expected = list(range(-size, 0)) + list(range(1, size + 1))
    return f'{balanced_sum(terms)}-{target}', expected


def polynomial(node):
    if isinstance(node, ast.Name) and node.id == 'x':
        return X
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return sp.Integer(node.value)
    if isinstance(node, ast.BinOp):
        left, right = polynomial(node.left), polynomial(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
    raise ValueError('Expected a polynomial')


def partition(tree):
    # Each quotient is a polynomial off its real roots. Establish ordinary
    # equality and sum the exceptional contributions by point.
    pending, corrections, coefficients, sites = [(tree, 1)], {}, {}, set()
    while pending:
        node, sign = pending.pop()
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
            pending.append((node.left, sign))
            pending.append((node.right, sign if isinstance(node.op, ast.Add) else -sign))
            continue
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            sites.add(span(node))
            numerator = sp.Poly(polynomial(node.left), X, domain=sp.QQ)
            denominator = sp.Poly(polynomial(node.right), X, domain=sp.QQ)
            quotient = numerator.exquo(denominator)
            for point in set(denominator.real_roots()):
                correction = sign * (numerator.eval(point) - quotient.eval(point))
                corrections[point] = corrections.get(point, 0) + correction
        else:
            quotient = sp.Poly(polynomial(node), X, domain=sp.QQ)
        for power, coefficient in quotient.terms():
            coefficients[power] = coefficients.get(power, 0) + sign * coefficient
    if any(coefficients.values()):
        raise ValueError('Benchmark requires ordinary equality')
    return frozenset(point for point, delta in corrections.items() if delta), sites


def run(engine, family, size):
    source, expected = fixture(family, size)
    start = perf_counter()
    tree = ast.parse(source, mode='eval').body
    if engine == 'ltba_root':
        audit = compile_polynomial_audit(source, 'x')
        assert audit is not None
        domain = audit.solve_equal()
        assert domain == REALS - sp.FiniteSet(*expected)
        sites = {site.span for site in audit.sites}
        status = 'verified'
    elif engine == 'ltba':
        result = simplify_text(source)
        domain = result.solve_equal('x')
        sites = {tuple(map(int, group.group_id.split(':')[1:])) for group in result.local_records}
        excluded = sp.FiniteSet(*expected)
        if domain.has(sp.ConditionSet):
            status = 'conditional'
        else:
            assert domain == REALS - excluded, domain
            status = 'verified'
    else:
        excluded, sites = partition(tree)
        assert excluded == frozenset(expected)
        status = 'verified'
    assert len(sites) == size
    # Same source replay on both paths, including the exact 0 branch.
    records = {}
    residual = oracle(source, tree, {'x': expected[0]}, records)
    assert records.keys() == sites
    if engine == 'ltba_root':
        assert {site.span: site.trace_at(expected[0])[0] for site in audit.sites} == {
            location: label for location, (_, label) in records.items()
        }
    assert residual == (Fraction(-2) if family == 'nonconstant_quotient' else Fraction(-1))
    assert sum(label == 'zero-no-op' for _, label in records.values()) == 1
    return dict(status=status, seconds=perf_counter() - start, sites=len(sites),
                witness=expected[0], residual=str(residual),
                trace=[(location, divisor, label) for location, (divisor, label) in sorted(records.items())])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', choices=('ltba', 'partition', 'ltba_root'))
    parser.add_argument('--engines', default='ltba,partition')
    parser.add_argument('--output', type=Path, default=Path('results/polynomial_rewrite_audit/report.json'))
    parser.add_argument('--family', default='nonconstant_quotient')
    parser.add_argument('--size', type=int, default=4)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(run(args.worker, args.family, args.size)))
        return
    rng = Random(1729)
    rows = []
    for family in ('nonconstant_quotient', 'two_roots'):
        for size in (4, 16, 32, 64, 256):
            row = dict(family=family, guards=size, outcomes={})
            traces = []
            engines = args.engines.split(',')
            rng.shuffle(engines)
            for engine in engines:
                samples = []
                for _ in range(2):
                    try:
                        proc = subprocess.run([sys.executable, '-m', 'benchmarks.polynomial_rewrite_audit',
                                               '--worker', engine, '--family', family, '--size', str(size)],
                                              capture_output=True, text=True, check=True, timeout=10)
                    except subprocess.TimeoutExpired:
                        row['outcomes'][engine] = {'status': 'timeout', 'samples_s': samples}
                        break
                    record = json.loads(proc.stdout)
                    samples.append(record.pop('seconds'))
                    traces.append(record.pop('trace'))
                    row['outcomes'][engine] = {**record, 'median_s': median(samples), 'samples_s': samples}
                if row['outcomes'][engine]['status'] == 'timeout':
                    continue
            assert all(trace == traces[0] for trace in traces)
            rows.append(row)
            print(family, size, row['outcomes'], flush=True)
    path = args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(
        scope='Synthetic polynomial quotient sums over the reals under LTBA division. '
              'Baseline proves exact polynomial quotients and prunes by real denominator roots. '
              'LTBA exports a SymPy domain; baseline keeps excluded points. Both replay all source '
              'records at an identical supplied witness. The ltba_root path also verifies its own retained site traces. '
              'Timings include validation and replay; '
              'wall cap includes startup. No trace serialization is timed.',
        timeout_s=10, sympy=sp.__version__, rows=rows,
    ), indent=2) + '\n')


if __name__ == '__main__':
    main()
