"""Compare compiled LTBA with an independent exact arithmetic DAG.

The two engines use the same formula dependency routing and output protocol.
Each division site points to a shared denominator and keeps its own source span.
"""
import ast
from collections import defaultdict
from fractions import Fraction
import json
import operator
from pathlib import Path
from random import Random
from statistics import median
from time import perf_counter_ns
import tracemalloc

import sympy as sp
from sympy.core.cache import clear_cache

from benchmarks.workbook_incremental import serialized
from ltba.cas import _Compiler, clear_caches


OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.UAdd: operator.pos, ast.USub: operator.neg}


def category(value):
    return 'zero-no-op' if value == 0 else 'positive-one' if value == 1 else 'regular'


def span(node):
    return node.lineno, node.col_offset, node.end_lineno, node.end_col_offset


class TraceCompiler(_Compiler):
    def __init__(self, source, register):
        super().__init__(source)
        self.register = register

    def divide(self, node, numerator, denominator, *, chain=False):
        self.register(node, denominator)
        return super().divide(node, numerator, denominator, chain=chain)


class LTBA:
    def __init__(self, inputs):
        self.symbols = {name: sp.Symbol(name, real=True) for name in inputs}
        self.records = []

    def compile(self, source, tree, register):
        compiler = TraceCompiler(source, register)
        result = compiler.visit(tree)
        self.records.append(tuple(compiler.groups))
        return result

    def session(self, inputs):
        bindings = {self.symbols[key]: sp.Integer(value) for key, value in inputs.items()}
        memo = {}

        def evaluate(expression):
            if expression not in memo:
                result = expression.xreplace(bindings)
                memo[expression] = Fraction(int(result.p), int(result.q))
            return memo[expression]

        return evaluate


class GuardedDAG:
    """Hash-consed arithmetic nodes and memoized exact DAG evaluation per edit."""
    def __init__(self, inputs):
        self.nodes = {}

    def intern(self, key):
        return self.nodes.setdefault(key, len(self.nodes))

    def compile(self, source, node, register):
        if isinstance(node, ast.Name):
            return self.intern(('input', node.id))
        if isinstance(node, ast.Constant):
            return self.intern(('constant', Fraction(ast.get_source_segment(source, node))))
        if isinstance(node, ast.UnaryOp):
            return self.intern((OPS[type(node.op)], self.compile(source, node.operand, register)))
        left = self.compile(source, node.left, register)
        right = self.compile(source, node.right, register)
        if isinstance(node.op, ast.Div):
            register(node, right)
            return self.intern(('division', left, right))
        return self.intern((OPS[type(node.op)], left, right))

    def session(self, inputs):
        memo = self.memo if hasattr(self, 'memo') else {}
        if not hasattr(self, 'keys'):
            self.keys = tuple(self.nodes)
            self.parents = defaultdict(list)
            self.input_ids = {}
            for index, (operation, *args) in enumerate(self.keys):
                if operation == 'input':
                    self.input_ids[args[0]] = index
                elif operation != 'constant':
                    for child in args:
                        self.parents[child].append(index)
        else:
            # Only invalidate cached nodes that depend on changed inputs.
            pending = [index for key, index in self.input_ids.items()
                       if inputs[key] != self.previous[key]]
            while pending:
                index = pending.pop()
                if index in memo:
                    del memo[index]
                    pending.extend(self.parents[index])
        self.previous = inputs.copy()
        self.memo = memo

        def evaluate(index):
            if index in memo:
                return memo[index]
            operation, *args = self.keys[index]
            if operation == 'input':
                result = Fraction(inputs[args[0]])
            elif operation == 'constant':
                result = args[0]
            elif operation == 'division':
                numerator, denominator = map(evaluate, args)
                result = numerator / denominator if denominator else numerator
            else:
                result = operation(*map(evaluate, args))
            memo[index] = result
            return result

        return evaluate


def source_names(node):
    return {part.id for part in ast.walk(node) if isinstance(part, ast.Name)}


class Runner:
    def __init__(self, backend, formulas, inputs):
        self.backend = backend(inputs)
        self.inputs = inputs.copy()
        self.outputs, self.guards = {}, {}
        self.sites = {}
        self.value_users, self.guard_users = defaultdict(set), defaultdict(set)
        for name, source in formulas.items():
            root = ast.parse(source, mode='eval').body

            def register(site, denominator):
                key = ast.unparse(site.right)
                self.sites[(name, span(site))] = key
                if key not in self.guards:
                    self.guards[key] = denominator
                    for dependency in source_names(site.right):
                        self.guard_users[dependency].add(key)

            self.outputs[name] = self.backend.compile(source, root, register)
            if backend is LTBA:
                compiled_spans = {
                    tuple(map(int, group.group_id.split(':')[1:]))
                    for group in self.backend.records[-1]
                }
                assert compiled_spans == {span(site) for site in ast.walk(root)
                                          if isinstance(site, ast.BinOp)
                                          and isinstance(site.op, ast.Div)}
            for dependency in source_names(root):
                self.value_users[dependency].add(name)
        evaluate = self.backend.session(self.inputs)
        self.values = {name: evaluate(node) for name, node in self.outputs.items()}
        self.cases = {key: category(evaluate(node)) for key, node in self.guards.items()}

    def edit(self, changes):
        self.inputs.update(changes)
        evaluate = self.backend.session(self.inputs)
        affected_values = set().union(*(self.value_users[key] for key in changes))
        affected_guards = set().union(*(self.guard_users[key] for key in changes))
        values, guards = {}, {}
        for name in affected_values:
            result = evaluate(self.outputs[name])
            if result != self.values[name]:
                self.values[name] = result
                values[name] = str(result)
        for key in affected_guards:
            result = category(evaluate(self.guards[key]))
            if result != self.cases[key]:
                self.cases[key] = result
                guards[key] = result
        return serialized({'values': values, 'guards': guards})

    def trace(self):
        return tuple((name, coords, guard, self.cases[guard])
                     for (name, coords), guard in sorted(self.sites.items()))


def oracle(source, node, inputs, trace):
    if isinstance(node, ast.Name):
        return Fraction(inputs[node.id])
    if isinstance(node, ast.Constant):
        return Fraction(ast.get_source_segment(source, node))
    if isinstance(node, ast.UnaryOp):
        return OPS[type(node.op)](oracle(source, node.operand, inputs, trace))
    left = oracle(source, node.left, inputs, trace)
    right = oracle(source, node.right, inputs, trace)
    if isinstance(node.op, ast.Div):
        trace[span(node)] = (ast.unparse(node.right), category(right))
        return left if right == 0 else left / right
    return OPS[type(node.op)](left, right)


def expected(formulas, inputs):
    values, trace = {}, []
    for name, source in formulas.items():
        records = {}
        values[name] = oracle(source, ast.parse(source, mode='eval').body, inputs, records)
        trace.extend((name, coords, guard, branch) for coords, (guard, branch) in records.items())
    return values, tuple(sorted(trace))


def measure(fn):
    start = perf_counter_ns()
    result = fn()
    return result, (perf_counter_ns() - start) / 1e6


def run(size, rng):
    inputs = {'d': 0, 'a': 1, **{f'x{i}': i % 3 for i in range(size)}}
    formulas = {f'q{i}': f'(7*(x{i}-a))/(2*(x{i}-a)) + ((x{i}-a)/d)/(x{i}-a) + x{i}/(d+(x{i}-a))'
                for i in range(size)}
    backends = {'ltba': LTBA, 'guarded_dag': GuardedDAG}
    cold_ms, peak_bytes = {}, {}
    for name, backend in backends.items():
        trials = []
        for _ in range(3):
            clear_caches()
            clear_cache()
            _, elapsed = measure(lambda: Runner(backend, formulas, inputs))
            trials.append(elapsed)
        cold_ms[name] = trials
        clear_caches()
        clear_cache()
        tracemalloc.start()
        measured = Runner(backend, formulas, inputs)
        peak_bytes[name] = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        del measured
    states = {name: Runner(backend, formulas, inputs) for name, backend in backends.items()}
    initial_values, initial_trace = expected(formulas, inputs)
    assert all(state.values == initial_values and state.trace() == initial_trace for state in states.values())
    samples = {name: {'local_edit': [], 'shared_edit': [], 'trace': []} for name in states}
    bytes_by_edit = defaultdict(list)
    changed_guards = defaultdict(list)
    for i in range(24):
        if i % 2:
            mode = 'shared_edit'
            edits = {'d': 1 - inputs['d']}
        else:
            mode = 'local_edit'
            name = f'x{rng.randrange(size)}'
            edits = {name: (inputs[name] + 1) % 3}
        inputs.update(edits)
        values, trace = expected(formulas, inputs)
        previous = states['ltba']
        expected_delta = {
            'values': {name: str(value) for name, value in values.items() if previous.values[name] != value},
            'guards': {guard: branch for _, _, guard, branch in trace if previous.cases[guard] != branch},
        }
        order = list(states)
        rng.shuffle(order)
        for name in order:
            engine = states[name]
            payload, elapsed = measure(lambda: engine.edit(edits))
            samples[name][mode].append(elapsed)
            full, elapsed = measure(lambda: serialized(engine.trace()))
            samples[name]['trace'].append(elapsed)
            assert payload == serialized(expected_delta)
            assert engine.values == values and full == serialized(trace)
        changed_guards[mode].append(len(expected_delta['guards']))
        bytes_by_edit[mode].append(len(payload))
    return dict(formulas=size, sites=len(initial_trace), unique_guards=len(states['ltba'].guards),
                cold_compile_samples_ms=cold_ms,
                cold_compile_median_ms={name: median(times) for name, times in cold_ms.items()},
                cold_compile_python_peak_bytes=peak_bytes, samples_ms=samples,
                median_ms={name: {mode: median(times) for mode, times in modes.items()}
                           for name, modes in samples.items()},
                changed_guards=changed_guards, compact_bytes=bytes_by_edit)


def main():
    rng = Random(1729)
    rows = []
    for size in (32, 128, 512):
        row = run(size, rng)
        rows.append(row)
        print(size, row['cold_compile_median_ms'], row['median_ms'], flush=True)
    path = Path('results/guarded_dag_equivalence/report.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        'scope': 'Exact integer input updates; identical evaluated outputs, compact JSON and complete '
                 'active traces checked by an independent Fraction traversal. Cold setup includes parsing, '
                 'compilation, indexes and initial evaluation. Peak memory is Python allocations only. '
                 'LTBA additionally compiles symbolic values and branch payloads; the independent DAG '
                 'compiles exact evaluation and retains equivalent active trace information. '
                 'Shared formula routing belongs to this harness, not the workbook engines.',
        'verified_edit_pairs': 24 * len(rows),
        'rows': rows,
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
