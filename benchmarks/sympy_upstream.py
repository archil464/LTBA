"""Compare LTBA expansion with SymPy using inputs from its upstream ASV suite."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import platform
from random import Random
from statistics import median
import subprocess
from time import perf_counter_ns

import sympy as sp
from sympy.core.cache import clear_cache

from ltba.cas import clear_caches, simplify_text


def cases(path):
    tree = ast.parse(path.read_text())
    assignments = {target.id: ast.unparse(node.value)
                   for node in tree.body if isinstance(node, ast.Assign)
                   for target in node.targets if isinstance(target, ast.Name)}
    yield 'time_expand_nothing_todo', assignments['p']
    yield 'bench_expand_32', assignments['e']
    expand = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == 'time_expand_arit')
    for index, statement in enumerate(expand.body, 1):
        yield f'time_expand_arit/{index}', ast.unparse(statement.value.func.value)


def compare(case, source, rng):
    symbols = {name: sp.Symbol(name, real=True) for name in ('x', 'y', 'z')}
    # Only expressions extracted from the pinned upstream Python fixture.
    def sympy_run():
        return sp.expand(sp.sympify(source, locals=symbols))

    def ltba_run():
        return simplify_text(source, transform='expand').value

    expected = sympy_run()
    assert ltba_run() == expected
    samples = {'sympy': [], 'ltba': []}
    runners = {'sympy': sympy_run, 'ltba': ltba_run}
    for _ in range(11):
        order = list(runners)
        rng.shuffle(order)
        for engine in order:
            clear_cache()
            clear_caches()
            start = perf_counter_ns()
            result = runners[engine]()
            elapsed = perf_counter_ns() - start
            assert result == expected, (case, engine)
            samples[engine].append(elapsed / 1_000)
    return {'upstream_case': case, 'input': source,
            'terms': len(sp.Add.make_args(expected)),
            'median_us': {name: median(times) for name, times in samples.items()},
            'samples_us': samples}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream_checkout', type=Path)
    args = parser.parse_args()
    checkout = args.upstream_checkout
    revision = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
    fixture = checkout / 'benchmarks/core/expand.py'
    rng = Random(1729)
    rows = []
    for case, source in cases(fixture):
        row = compare(case, source, rng)
        rows.append(row)
        print(case, row['terms'], row['median_us'], flush=True)
    report = {
        'upstream': 'https://github.com/sympy/sympy_benchmarks',
        'commit': revision,
        'fixture': 'benchmarks/core/expand.py',
        'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(),
        'python': platform.python_version(),
        'sympy': sp.__version__,
        'scope': 'Adapted upstream polynomial expansion inputs using real symbols on both sides. '
                 'Cold parse-to-result timings, 11 runs per engine, output equality checked '
                 'outside timing. No provenance-bearing input. These are not raw ASV timings.',
        'rows': rows,
    }
    path = Path('results/sympy_upstream/report.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
