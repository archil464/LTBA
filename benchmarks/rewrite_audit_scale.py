"""Stress the distinct-root rewrite audit under per-process resource limits."""

import argparse
import ast
from fractions import Fraction
from itertools import chain
import json
from pathlib import Path
import resource
from statistics import median
import subprocess
import sys
from time import perf_counter

import sympy as sp

from benchmarks.rewrite_audit import REALS, baseline_solve
from ltba.cas import simplify_text
from ltba.point_audit import compile_point_audit, compile_point_audit_terms


MIB = 1024 * 1024


def balanced_sum(terms):
    if len(terms) == 1:
        return terms[0]
    middle = len(terms) // 2
    return f'({balanced_sum(terms[:middle])}+{balanced_sum(terms[middle:])})'


def affine(node):
    """Return exact coefficients for the affine terms in this workload."""
    if isinstance(node, ast.Name) and node.id == 'x':
        return 1, 0
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return 0, node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub):
        a, b = affine(node.left)
        c, d = affine(node.right)
        return a - c, b - d
    raise ValueError('Expected an integer affine term')


def root_events(tree, target, selected=None):
    """Group proportional affine quotients by their exceptional root."""
    events = {}
    ordinary = Fraction(0)
    pending = [tree]
    while pending:
        node = pending.pop()
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            pending.extend((node.left, node.right))
            continue
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Div):
            raise ValueError('Expected a sum of quotients')
        a, b = affine(node.left)
        c, d = affine(node.right)
        if not c or a * d != b * c:
            raise ValueError('Expected proportional affine terms with a nonconstant divisor')
        regular = Fraction(a, c)
        root = Fraction(-d, c)
        if selected is not None and root in selected:
            selected[root] = tuple(
                ('zero-no-op' if not divisor else 'positive-one' if divisor == 1 else 'regular',
                 a * x + b if not divisor else (a * x + b) / divisor)
                for x in (root, root + 1) for divisor in (c * x + d,)
            )
        ordinary += regular
        events[root] = events.get(root, 0) + a * root + b - regular
    if ordinary != target:
        raise ValueError('This benchmark expects equality away from the roots')
    return sorted(root for root, change in events.items() if change)


def worker(engine, size, memory_mib):
    limit = memory_mib * MIB
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    stream = engine in ('ltba_stream', 'ltba_stream_sympy')
    if not stream:
        original = balanced_sum([f'((x-{i})/(x-{i}))' for i in range(size)])
        source = f'{original}-{size}'
    start = perf_counter()
    compile_s = None
    checks = (0, size // 2, size - 1)
    if stream:
        terms = (f'((x-{i})/(x-{i}))' for i in range(size))
        audit = compile_point_audit_terms(chain(terms, (f'-{size}',)), 'x')
        assert audit is not None
        compile_s = perf_counter() - start
        compact = audit.equality()
        result = compact.to_sympy() if engine == 'ltba_stream_sympy' else None
        roots = compact.points
        assert compact.default
        sites = len(audit.sites)
        traces = {i: (audit.sites[i].trace_at(i), audit.sites[i].trace_at(i + 1))
                  for i in checks}
    elif engine == 'ltba_source':
        audit = compile_point_audit(source, 'x')
        assert audit is not None
        compile_s = perf_counter() - start
        result = audit.solve_equal()
        sites = len(audit.sites)
        traces = {i: (audit.sites[i].trace_at(i), audit.sites[i].trace_at(i + 1))
                  for i in checks}
    elif engine == 'root_with_trace':
        traces = dict.fromkeys(checks)
        roots = root_events(ast.parse(original, mode='eval').body, size, traces)
        excluded = sp.FiniteSet(*(sp.Rational(r.numerator, r.denominator) for r in roots))
        result = (sp.Complement(REALS, excluded, evaluate=False)
                  if size > 32 else REALS - excluded)
        sites = len(roots)
    elif engine == 'root_events':
        roots = root_events(ast.parse(original, mode='eval').body, size)
        result = None
        sites = size
    elif engine == 'ltba':
        compiled = simplify_text(source)
        sites = len(compiled.local_records)
        compile_s = perf_counter() - start
        result = compiled.solve_equal('x')
    else:
        tree = ast.parse(source, mode='eval').body
        sites = sum(isinstance(node, ast.Div) for node in ast.walk(tree))
        result = baseline_solve(tree)
    elapsed = perf_counter() - start
    if stream or engine in ('ltba_source', 'root_with_trace'):
        assert all(trace == (('zero-no-op', 0), ('positive-one', 1)) for trace in traces.values())
    if result is None:
        if stream:
            assert len(roots) == size and all(i in roots for i in range(size))
        else:
            assert roots == list(range(size))
        status = 'verified'
    elif result.has(sp.ConditionSet):
        status = 'conditional'
    else:
        excluded = sp.FiniteSet(*range(size))
        expected = (sp.Complement(REALS, excluded, evaluate=False)
                    if isinstance(result, sp.Complement) else REALS - excluded)
        assert result == expected, (engine, size, result)
        status = 'verified'
    assert sites == size
    print(json.dumps(dict(status=status, seconds=elapsed, compile_s=compile_s,
                          peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)))


def run(engine, size, args):
    samples = []
    for _ in range(args.repeats):
        try:
            proc = subprocess.run(
                [sys.executable, '-m', __spec__.name, '--worker', engine,
                 '--sizes', str(size), '--memory-mib', str(args.memory_mib)],
                capture_output=True, text=True, timeout=args.timeout,
            )
        except subprocess.TimeoutExpired:
            return {'status': 'timeout', 'timeout_s': args.timeout, 'samples': samples}
        if proc.returncode:
            error = proc.stderr.strip().splitlines()
            status = 'memory_limit' if any('MemoryError' in line for line in error) else 'error'
            return {'status': status, 'exit_code': proc.returncode, 'error': error[-4:]}
        sample = json.loads(proc.stdout)
        samples.append(sample)
        if sample['status'] != 'verified':
            break
    return dict(status=samples[-1]['status'], median_s=median(s['seconds'] for s in samples),
                peak_rss_kib=max(s['peak_rss_kib'] for s in samples), samples=samples)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sizes', default='8,12,16,32,64,128,256,512,1024,4096,16384,65536')
    parser.add_argument('--timeout', type=float, default=12)
    parser.add_argument('--memory-mib', type=int, default=768)
    parser.add_argument('--repeats', type=int, default=2)
    parser.add_argument('--engines', default='fold_first,ltba,root_events')
    parser.add_argument('--output', type=Path, default=Path('results/rewrite_audit_scale/report.json'))
    parser.add_argument('--worker', choices=('ltba', 'fold_first', 'root_events', 'ltba_source', 'root_with_trace', 'ltba_stream', 'ltba_stream_sympy'))
    args = parser.parse_args()
    sizes = [int(size) for size in args.sizes.split(',')]
    if args.worker:
        worker(args.worker, sizes[0], args.memory_mib)
        return
    rows = {}
    # Stop the fold-first sweep after the first capped point. Test LTBA again
    # at 512 and 4,096 to distinguish its observed cutoff from a transient.
    for engine in args.engines.split(','):
        if engine not in ('fold_first', 'ltba', 'root_events', 'ltba_source', 'root_with_trace', 'ltba_stream', 'ltba_stream_sympy'):
            parser.error(f'Unknown engine: {engine}')
        capped = False
        for size in sizes:
            if capped and (engine == 'fold_first' or engine == 'ltba' and size not in (512, 4096)):
                continue
            result = run(engine, size, args)
            rows.setdefault(size, {})[engine] = result
            print(engine, size, result['status'], result.get('median_s', ''), flush=True)
            capped |= result['status'] != 'verified'
    path = args.output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(
        workload='Sum of (x-i)/(x-i), i=0..n-1, rewritten as n under no-op division.',
        expected='All reals except 0 through n-1. Root-events returns the excluded points directly.',
        scope='Calculation time includes input parsing and symbolic construction. '
              'Wall timeout covers child startup and verification too. Peak RSS includes imports. '
              'LTBA compiles source records. Other paths return the validity domain without source '
              'records. The root_with_trace path computes the same domain and the same three selected site traces '
              'as ltba_source, while LTBA keeps all sites available for later lookup. No trace serialization. '
              'Root-events is specialized to proportional affine terms. Streaming engines generate one '
              'line at a time inside the timed interval; the compact variant skips SymPy set export.',
        timeout_s=args.timeout, memory_mib=args.memory_mib, repeats=args.repeats,
        sympy=sp.__version__, rows=rows,
    ), indent=2) + '\n')


if __name__ == '__main__':
    main()
