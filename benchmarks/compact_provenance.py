"""Measured updates of LTBA and conventional factored conditional expressions.

All backends keep the same immutable branch records and preserve old versions.
The benchmark starts after a valid local algebraic rewrite has been identified.
It measures representation construction and replacement of that branch payload.
Run with ``python -m benchmarks.compact_provenance --output results/compact``.
"""
from __future__ import annotations

import argparse
import ast
import csv
import datetime
import gc
import hashlib
import itertools
import json
import math
import os
import platform
import random
import statistics
import subprocess
import time
import tracemalloc
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

from ltba import registry
from ltba.core import Guard, LocalBranch, LocalBranchGroup, LTBAExpr


FAMILIES = ("division", "radical", "shared_division")
BACKENDS = ("ltba", "factored_tuple", "factored_tree", "explicit")
REASON = "add_zero"


def specifications(family, n):
    """Generate identical payloads for every representation, without a CAS parser."""
    groups = []
    terms = []
    for index in range(1, n + 1):
        variable = "x1" if family == "shared_division" else f"x{index}"
        if family == "radical":
            terms.append(f"sqrt({variable}^2)")
            groups.append(LocalBranchGroup(f"radical_sign:{index}", (
                LocalBranch(Guard(f"{variable} >= 0"), variable, f"sqrt_square_pos:{variable}"),
                LocalBranch(Guard(f"{variable} < 0"), f"-{variable}", f"sqrt_square_neg:{variable}"),
            )))
        else:
            terms.append(f"({variable}/{variable})")
            groups.append(LocalBranchGroup(f"division_guard:{index}", (
                LocalBranch(Guard(f"{variable} != 0"), "1", f"cancel:{variable}/{variable}"),
                LocalBranch(Guard(f"{variable} == 0"), "0", f"singular:{variable}/{variable}"),
            )))
    separator = " + " if family == "radical" else " * "
    origin = "LTBA-2:radicals_abs" if family == "radical" else "LTBA-1:guarded_division"
    return separator.join(terms), tuple(groups), [origin]


def revised_group(group, value):
    first = group.branches[0]
    return LocalBranchGroup(
        group.group_id,
        (LocalBranch(first.guard, value, first.tag),) + group.branches[1:],
        group.description,
    )


def revised_history(history, index, reason):
    result = list(history)
    result.append(f"local_rewrite_group:{index}:{reason}")
    return result


@dataclass
class TupleExpression:
    base: str
    factors: tuple
    provenance: list

    def rewrite_local(self, index, value, reason):
        if not 0 <= index < len(self.factors):
            raise IndexError(index)
        factors = list(self.factors)
        factors[index] = revised_group(factors[index], value)
        return TupleExpression(self.base, tuple(factors), revised_history(self.provenance, index, reason))


@dataclass(frozen=True)
class Node:
    left: object
    right: object
    size: int


def tree_from_groups(groups, start=0, stop=None):
    if stop is None:
        stop = len(groups)
    if stop - start == 1:
        return groups[start]
    middle = (start + stop) // 2
    return Node(tree_from_groups(groups, start, middle), tree_from_groups(groups, middle, stop), stop - start)


def tree_size(node):
    return node.size if isinstance(node, Node) else 1


def tree_replace(node, index, value):
    if isinstance(node, LocalBranchGroup):
        return revised_group(node, value)
    left_size = tree_size(node.left)
    if index < left_size:
        return Node(tree_replace(node.left, index, value), node.right, node.size)
    return Node(node.left, tree_replace(node.right, index - left_size, value), node.size)


def tree_groups(node):
    if isinstance(node, LocalBranchGroup):
        yield node
    else:
        yield from tree_groups(node.left)
        yield from tree_groups(node.right)


@dataclass
class TreeExpression:
    base: str
    root: object
    provenance: list

    def rewrite_local(self, index, value, reason):
        if not 0 <= index < tree_size(self.root):
            raise IndexError(index)
        return TreeExpression(self.base, tree_replace(self.root, index, value), revised_history(self.provenance, index, reason))


@dataclass
class ExplicitExpression:
    base: str
    metadata: tuple
    cases: tuple
    provenance: list

    def rewrite_local(self, index, value, reason):
        if not 0 <= index < len(self.metadata):
            raise IndexError(index)
        target_guard = self.metadata[index][2]
        new_cases = []
        first = self.cases[0][index]
        replacement = LocalBranch(first.guard, value, first.tag)
        for case in self.cases:
            if case[index].guard == target_guard:
                case = case[:index] + (replacement,) + case[index + 1:]
            new_cases.append(case)
        return ExplicitExpression(self.base, self.metadata, tuple(new_cases), revised_history(self.provenance, index, reason))


def build(backend, family, n):
    if family not in FAMILIES or n < 1:
        raise ValueError((family, n))
    if backend == "ltba" and family != "shared_division":
        component = "LTBA-2" if family == "radical" else "LTBA-1"
        return registry.get(component).make_family(n)
    base, groups, history = specifications(family, n)
    if backend == "ltba":
        expression = LTBAExpr(base, provenance=history)
        for group in groups:
            expression = expression.add_branch_group(group.group_id, list(group.branches), group.description)
        return expression
    if backend == "ltba_bulk":
        return LTBAExpr(base, groups, history)
    if backend == "factored_tuple":
        return TupleExpression(base, groups, history)
    if backend == "factored_tree":
        return TreeExpression(base, tree_from_groups(groups), history)
    if backend == "explicit":
        metadata = tuple((group.group_id, group.description, group.branches[0].guard) for group in groups)
        cases = tuple(itertools.product(*(group.branches for group in groups)))
        return ExplicitExpression(base, metadata, cases, history)
    raise ValueError(backend)


def groups_of(expression):
    if isinstance(expression, LTBAExpr):
        return expression.branch_groups
    if isinstance(expression, TupleExpression):
        return expression.factors
    if isinstance(expression, TreeExpression):
        return tuple(tree_groups(expression.root))
    raise TypeError(type(expression))


def check_structure(expression, expected):
    """Check every stored field, including inactive branches and old snapshots."""
    base, groups, history = expected
    assert expression.base == base
    assert expression.provenance == history
    if isinstance(expression, ExplicitExpression):
        assert expression.metadata == tuple((g.group_id, g.description, g.branches[0].guard) for g in groups)
        assert expression.cases == tuple(itertools.product(*(g.branches for g in groups)))
    else:
        assert groups_of(expression) == groups


@lru_cache(maxsize=131072)
def parse(text):
    return ast.parse(text, mode="eval").body


def arithmetic(node, values):
    """Small independent exact evaluator for the benchmark's payload grammar."""
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return Fraction(node.value)
    if isinstance(node, ast.Name):
        return Fraction(values[node.id])
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -arithmetic(node.operand, values)
    if isinstance(node, ast.BinOp):
        left, right = arithmetic(node.left, values), arithmetic(node.right, values)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Mult):
            return left * right
    raise ValueError(ast.dump(node))


def guard_holds(guard, values):
    node = parse(guard.text)
    left = arithmetic(node.left, values)
    right = arithmetic(node.comparators[0], values)
    operation = node.ops[0]
    if isinstance(operation, ast.Eq):
        return left == right
    if isinstance(operation, ast.NotEq):
        return left != right
    if isinstance(operation, ast.GtE):
        return left >= right
    if isinstance(operation, ast.Lt):
        return left < right
    raise ValueError(ast.dump(node))


def selected_records(expression, values):
    if isinstance(expression, ExplicitExpression):
        matches = [case for case in expression.cases if all(guard_holds(branch.guard, values) for branch in case)]
        assert len(matches) == 1
        return matches[0]
    records = []
    for group in groups_of(expression):
        matches = [branch for branch in group.branches if guard_holds(branch.guard, values)]
        assert len(matches) == 1
        records.append(matches[0])
    return tuple(records)


def update_schedule(family, n, count, seed):
    rng = random.Random(seed)
    active = set()
    schedule = []
    for _ in range(count):
        index = rng.randrange(n)
        variable = "x1" if family == "shared_division" else f"x{index + 1}"
        original = variable if family == "radical" else "1"
        value = original if index in active else f"({original} + 0)"
        active.symmetric_difference_update((index,))
        schedule.append((index, value))
    return schedule


def apply_updates(expression, schedule):
    for index, value in schedule:
        expression = expression.rewrite_local(index, value, REASON)
    return expression


def validate_case(family, n, exhaustive, seed=1729):
    rng = random.Random(seed)
    backends = list(BACKENDS) if n <= 12 else list(BACKENDS[:-1])
    expressions = {backend: build(backend, family, n) for backend in backends}
    expected = specifications(family, n)
    snapshots = [(expressions, expected)]
    schedule = update_schedule(family, n, 8, seed)
    for index, value in schedule:
        base, groups, history = expected
        updated_groups = list(groups)
        group = groups[index]
        # Independent oracle uses dataclass replacement, without backend helpers.
        branches = (replace(group.branches[0], value=value),) + group.branches[1:]
        updated_groups[index] = replace(group, branches=branches)
        expected = (base, tuple(updated_groups), history + [f"local_rewrite_group:{index}:{REASON}"])
        expressions = {name: expr.rewrite_local(index, value, REASON) for name, expr in expressions.items()}
        snapshots.append((expressions, expected))
    dimensions = 1 if family == "shared_division" else n
    if exhaustive:
        assignments = list(itertools.product((-2, 0, 3), repeat=dimensions))
    else:
        assignments = [tuple([value] * dimensions) for value in (-2, 0, 3)]
        assignments.extend(tuple(rng.choice((-2, 0, 3)) for _ in range(dimensions)) for _ in range(5))
    checks = 0
    # Query initial, intermediate, and final versions after all updates have run.
    for version, expected in snapshots:
        for expression in version.values():
            check_structure(expression, expected)
        for assignment in assignments:
            values = {f"x{i + 1}": value for i, value in enumerate(assignment)}
            direct_values = [values["x1" if family == "shared_division" else f"x{i + 1}"] for i in range(n)]
            direct_result = sum(abs(value) for value in direct_values) if family == "radical" else int(all(direct_values))
            expected_records = tuple(group.branches[0 if (value >= 0 if family == "radical" else value != 0) else 1]
                                     for group, value in zip(expected[1], direct_values))
            for expression in version.values():
                records = selected_records(expression, values)
                assert records == expected_records
                payloads = [arithmetic(parse(branch.value), values) for branch in records]
                result = sum(payloads) if family == "radical" else math.prod(payloads)
                assert result == direct_result
                checks += 1
    return checks


def elapsed_batch(function, iterations):
    enabled = gc.isenabled()
    gc.disable()
    try:
        start = time.perf_counter_ns()
        for _ in range(iterations):
            result = function()
        elapsed = time.perf_counter_ns() - start
    finally:
        if enabled:
            gc.enable()
    # The final result remains live through the final timestamp for each backend.
    return elapsed / iterations


def measurements(jobs, repeats, target_ms, seed):
    """Calibrated batches, with shuffled backend order on every trial."""
    rng = random.Random(seed)
    iterations = {}
    samples = {name: [] for name in jobs}
    for name, function in jobs.items():
        function()
        estimate = elapsed_batch(function, 3)
        iterations[name] = max(1, min(10000, math.ceil(target_ms * 1e6 / max(1, estimate))))
    for _ in range(repeats):
        order = list(jobs)
        rng.shuffle(order)
        for name in order:
            samples[name].append(elapsed_batch(jobs[name], iterations[name]) / 1000)
    return {
        name: {
            "median_us": statistics.median(data),
            "min_us": min(data),
            "max_us": max(data),
            "q1_us": statistics.quantiles(data, n=4)[0],
            "q3_us": statistics.quantiles(data, n=4)[2],
            "samples_us": data,
            "iterations_per_sample": iterations[name],
        }
        for name, data in samples.items()
    }


def memory_measurement(function):
    gc.collect()
    tracemalloc.start()
    result = function()
    retained, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"retained_bytes": retained, "peak_bytes": peak}


def benchmark(family, n, repeats, target_ms, update_count, seed, explicit_max_n):
    backends = list(BACKENDS) if n <= explicit_max_n else list(BACKENDS[:-1])
    states = {name: build(name, family, n) for name in backends}
    schedule = update_schedule(family, n, update_count, seed)
    single = update_schedule(family, n, 1, seed)
    factories = {name: (lambda name=name: build(name, family, n)) for name in backends}
    # Bulk construction is a diagnostic using LTBA's existing public constructor.
    factories["ltba_bulk"] = lambda: build("ltba_bulk", family, n)
    operations = {
        "build": factories,
        "rewrite_one": {name: (lambda name=name: apply_updates(states[name], single)) for name in backends},
        "updates": {name: (lambda name=name: apply_updates(states[name], schedule)) for name in backends},
        "build_plus_updates": {name: (lambda name=name: apply_updates(build(name, family, n), schedule)) for name in factories},
    }
    rows = []
    for operation, jobs in operations.items():
        timing = measurements(jobs, repeats, target_ms, seed)
        for name in jobs:
            row = {"family": family, "n": n, "backend": name, "operation": operation,
                   "update_count": update_count, **timing[name]}
            if operation in ("build", "rewrite_one"):
                row.update(memory_measurement(jobs[name]))
            rows.append(row)
    # Check the exact final records and histories for the timed update schedule.
    reference = apply_updates(states["ltba"], schedule)
    expected = (reference.base, reference.branch_groups, reference.provenance)
    for state in states.values():
        check_structure(apply_updates(state, schedule), expected)
        check_structure(state, specifications(family, n))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", default="8,12,32,128,512,2048,8192")
    parser.add_argument("--families", default=",".join(FAMILIES))
    parser.add_argument("--repeats", type=int, default=11)
    parser.add_argument("--target-ms", type=float, default=5)
    parser.add_argument("--updates", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--explicit-max-n", type=int, default=12)
    parser.add_argument("--output", type=Path, default=Path("results/compact_provenance"))
    args = parser.parse_args()
    sizes = [int(item) for item in args.sizes.split(",")]
    families = args.families.split(",")
    if args.repeats < 3 or args.target_ms <= 0 or args.updates < 1 or min(sizes) < 1:
        parser.error("Use repeats >= 3, target-ms > 0, updates >= 1, and positive sizes")
    if any(family not in FAMILIES for family in families):
        parser.error(f"Families must be drawn from {FAMILIES}")
    checks = 0
    for family in families:
        for n in range(1, 6):
            checks += validate_case(family, n, exhaustive=True, seed=args.seed)
        for n in sizes:
            checks += validate_case(family, n, exhaustive=False, seed=args.seed)
        print(f"validated {family}", flush=True)
    rows = []
    for family in families:
        for n in sizes:
            rows.extend(benchmark(family, n, args.repeats, args.target_ms, args.updates, args.seed, args.explicit_max_n))
            print(f"measured {family}, n={n}", flush=True)
    source = Path(__file__)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    report = {
        "benchmark": "compact provenance updates v1",
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_commit": commit,
        "benchmark_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "core_sha256": hashlib.sha256(Path("ltba/core.py").read_bytes()).hexdigest(),
        "configuration": {**vars(args), "output": str(args.output)},
        "environment": {"python": platform.python_version(), "implementation": platform.python_implementation(),
                        "platform": platform.platform(), "cpu_count": os.cpu_count(),
                        "affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
                        "timer": str(time.get_clock_info("perf_counter"))},
        "correctness": {"evaluation_and_provenance_checks": checks, "failures": 0,
                        "exhaustive_sizes": [1, 2, 3, 4, 5], "values": [-2, 0, 3],
                        "snapshots_per_case": 9, "large_size_assignments": 8},
        "scope": "Preselected branch payload updates with all guards, tags, group metadata, and copied histories preserved. Arithmetic guards are evaluated only during validation. Explicit cases are capped by n. Timing samples use repeated warm allocations in one Python process with GC disabled during timing. tracemalloc runs separately.",
        "rows": rows,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    with (args.output / "summary.csv").open("w", newline="") as stream:
        columns = [key for key in rows[0] if key != "samples_us"]
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"correctness_checks": checks, "rows": len(rows), "output": str(args.output)}))


if __name__ == "__main__":
    main()
