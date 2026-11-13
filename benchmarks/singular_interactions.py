"""Independent conventional Piecewise compiler and exact rational oracle.

Construction timings are diagnostic: LTBA includes source provenance whereas
conventional Piecewise constructs only values. Neither compiler expands a global
case table. Every numeric comparison uses an independent Fraction evaluator.
"""
import ast
from fractions import Fraction
import itertools
import json
from pathlib import Path
import random
import statistics
import time
import sympy as sp
from sympy.core.cache import clear_cache
from ltba.cas import simplify_text, clear_caches


def conventional(node):
    if isinstance(node, ast.Constant):
        return sp.Rational(node.value)
    if isinstance(node, ast.Name):
        return sp.Symbol(node.id, real=True)
    if isinstance(node, ast.UnaryOp):
        return -conventional(node.operand)
    a, b = conventional(node.left), conventional(node.right)
    if isinstance(node.op, ast.Add): return a + b
    if isinstance(node.op, ast.Sub): return a - b
    if isinstance(node.op, ast.Mult): return a * b
    if isinstance(node.op, ast.Div):
        return sp.Piecewise((a, sp.Eq(b, 0)), (a / b, True))
    raise ValueError(ast.dump(node))


def oracle(node, values):
    if isinstance(node, ast.Constant): return Fraction(node.value)
    if isinstance(node, ast.Name): return Fraction(values[node.id])
    if isinstance(node, ast.UnaryOp): return -oracle(node.operand, values)
    a, b = oracle(node.left, values), oracle(node.right, values)
    if isinstance(node.op, ast.Add): return a + b
    if isinstance(node.op, ast.Sub): return a - b
    if isinstance(node.op, ast.Mult): return a * b
    if isinstance(node.op, ast.Div): return a if b == 0 else a / b
    raise ValueError(ast.dump(node))


def source_for(family, n):
    if family == 'coupled_product':
        return '*'.join(f'((x{i}-x{(i+1)%n})/(x{i}-x{(i+1)%n}))' for i in range(n))
    if family == 'interacting_sum':
        return '+'.join(f'(x{i}/(x{(i+1)%n}-x{i}))' for i in range(n))
    source = 'x0'
    for i in range(1, n):
        source = f'({source})/(x{i}-x{i-1})'
    return source


def main():
    rng = random.Random(1729)
    rows = []
    checks = 0
    for family in ('coupled_product', 'interacting_sum', 'nested_division'):
        for n in (2, 4, 8):
            source = source_for(family, n)
            tree = ast.parse(source, mode='eval').body
            samples = {'ltba_with_provenance': [], 'conventional_value_only': []}
            results = {}
            for repeat in range(3):
                order = list(samples)
                rng.shuffle(order)
                for backend in order:
                    clear_caches(); clear_cache()
                    start = time.perf_counter_ns()
                    result = simplify_text(source) if backend.startswith('ltba') else conventional(ast.parse(source, mode='eval').body)
                    samples[backend].append((time.perf_counter_ns()-start)/1e6)
                    results[backend] = result
            ltba = results['ltba_with_provenance']
            other = results['conventional_value_only']
            assignments = list(itertools.product((-1, 0, 1), repeat=n)) if n <= 4 else [tuple(rng.choice((-1,0,1)) for _ in range(n)) for _ in range(40)]
            assignments += [(0,)*n, (1,)*n]
            for assignment in assignments:
                values = dict(zip((f'x{i}' for i in range(n)), assignment))
                expected = oracle(tree, values)
                expected = sp.Rational(expected.numerator, expected.denominator)
                replacements = {sp.Symbol(k, real=True):v for k,v in values.items()}
                assert ltba.evaluate(values) == expected, (family,n,values)
                assert other.subs(replacements, simultaneous=True) == expected, (family,n,values)
                checks += 1
            row = dict(family=family, variables=n, cases=len(assignments),
                       median_ms={k:statistics.median(v) for k,v in samples.items()}, samples_ms=samples,
                       ltba_groups=len(ltba.local_records), ltba_value_nodes=sum(1 for _ in sp.preorder_traversal(ltba.value)),
                       conventional_value_nodes=sum(1 for _ in sp.preorder_traversal(other)))
            rows.append(row)
            print(family,n,row['median_ms'],flush=True)
    report = dict(policy='Division by zero returns the evaluated numerator unchanged. Multiplication by zero remains destructive.',
                  scope=__doc__, verified_assignments=checks, rows=rows)
    path = Path('results/singular_interactions/report.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+'\n')
    print('Verified assignments:', checks)


if __name__ == '__main__': main()
