"""Full text-to-JSON simplification and before/after storage measurements.

The conventional factored baseline and LTBA share the same SymPy-backed
arithmetic kernel and retain identical output information. End-to-end time
includes parsing, algebra, guards, provenance construction, and serialization.
"""
from __future__ import annotations

import argparse
import cProfile
import csv
import hashlib
import importlib.util
import itertools
import json
import platform
import pstats
import random
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import sympy as sp
from sympy.core.cache import clear_cache

from ltba import registry, simplify_text
from ltba.cas import clear_caches, compile_text, result_dict
from benchmarks.compact_provenance import measurements, memory_measurement


BASELINE_COMMIT = "7e083dbae15edb1865587ced235671ca1b465853"
FAMILIES = ("cancel_product", "shifted_sum", "radicals", "shared_guard", "nested")
BACKENDS = ("ltba_flat", "ltba_tree", "sympy_factored")


def source_for(family, n):
    terms = []
    for index in range(n):
        variable = f"x{index}"
        if family == "cancel_product":
            terms.append(f"({variable}/{variable})")
        elif family == "shifted_sum":
            terms.append(f"(({variable}^2-1)/({variable}-1))")
        elif family == "radicals":
            terms.append(f"sqrt({variable}^2)")
        elif family == "shared_guard":
            terms.append("(x0/x0)")
        elif family == "nested":
            terms.append(f"(1/({variable}/{variable}-1))")
        else:
            raise ValueError(family)
    operator = " * " if family in ("cancel_product", "shared_guard") else " + "
    return operator.join(terms)


def pipeline(source, backend):
    if backend == "sympy_factored":
        value, groups = compile_text(source)
        payload = result_dict(source, value, groups, ["cas:simplify"])
    else:
        storage = "tree" if backend == "ltba_tree" else "flat"
        payload = simplify_text(source, storage=storage).to_dict()
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def expected_value(family, values):
    if family == "cancel_product":
        return int(all(values))
    if family == "shared_guard":
        return int(values[0] != 0)
    if family == "shifted_sum":
        return sum(0 if value == 1 else value + 1 for value in values)
    if family == "radicals":
        return sum(abs(value) for value in values)
    return sum(-1 if value == 0 else 1 for value in values)


def validate(family, n, exhaustive, seed):
    source = source_for(family, n)
    baseline = pipeline(source, "sympy_factored")
    result = simplify_text(source)
    assert pipeline(source, "ltba_flat") == baseline
    assert pipeline(source, "ltba_tree") == baseline
    dimensions = 1 if family == "shared_guard" else n
    if exhaustive:
        assignments = itertools.product((-1, 0, 1, 2), repeat=dimensions)
    else:
        rng = random.Random(seed)
        assignments = [tuple([value] * dimensions) for value in (-1, 0, 1, 2)]
        assignments.extend(tuple(rng.choice((-1, 0, 1, 2)) for _ in range(dimensions)) for _ in range(4))
    checks = 0
    for assignment in assignments:
        substitutions = {f"x{index}": value for index, value in enumerate(assignment)}
        assert result.evaluate(substitutions) == expected_value(family, assignment)
        checks += 1
    return checks


def summarize(samples):
    quartiles = statistics.quantiles(samples, n=4)
    return {"median_ms": statistics.median(samples), "q1_ms": quartiles[0],
            "q3_ms": quartiles[2], "min_ms": min(samples), "max_ms": max(samples),
            "samples_ms": samples}


def measure_pipeline(family, n, repeats, seed):
    source = source_for(family, n)
    expected = pipeline(source, "sympy_factored")
    rng = random.Random(seed)
    rows = []
    for cache in ("cleared", "warm"):
        samples = {backend: [] for backend in BACKENDS}
        for backend in BACKENDS:
            pipeline(source, backend)
        for _ in range(repeats):
            order = list(BACKENDS)
            rng.shuffle(order)
            for backend in order:
                if cache == "cleared":
                    clear_cache()
                    clear_caches()
                start = time.perf_counter_ns()
                output = pipeline(source, backend)
                elapsed_ms = (time.perf_counter_ns() - start) / 1e6
                assert output == expected
                samples[backend].append(elapsed_ms)
        for backend, times in samples.items():
            rows.append({"family": family, "n": n, "backend": backend, "cache": cache,
                         "serialized_bytes": len(expected.encode()),
                         "records": len(json.loads(expected)["groups"]), **summarize(times)})
    return rows


def load_legacy(repository):
    """Import the exact earlier core and factories from a fixed Git commit."""
    with tempfile.TemporaryDirectory(prefix="ltba-original-") as directory:
        path = Path(directory)
        for filename in ("__init__.py", "core.py", "components.py"):
            contents = subprocess.check_output(["git", "show", f"{BASELINE_COMMIT}:ltba/{filename}"], cwd=repository)
            (path / filename).write_bytes(contents)
        name = "_ltba_original_benchmark"
        spec = importlib.util.spec_from_file_location(name, path / "__init__.py", submodule_search_locations=[str(path)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module


def record_data(expression):
    return (expression.base, tuple(expression.provenance), tuple(
        (group.group_id, group.description,
         tuple((branch.guard.text, branch.value, branch.tag) for branch in group.branches))
        for group in expression.branch_groups))


def apply_updates(expression, indices):
    for index in indices:
        expression = expression.rewrite_local(index, "(1 + 0)", "measured_update")
    return expression


def measure_storage(legacy, n, repeats, seed):
    def current():
        return registry.get("LTBA-1").make_family(n)
    factories = {
        "original_ltba": lambda: legacy.registry.get("LTBA-1").make_family(n),
        "improved_flat": current,
        "improved_tree": lambda: current().with_storage("tree"),
    }
    states = {name: factory() for name, factory in factories.items()}
    expected_initial = record_data(states["original_ltba"])
    assert all(record_data(state) == expected_initial for state in states.values())
    rng = random.Random(seed)
    indices = [rng.randrange(n) for _ in range(100)]
    expected_final = record_data(apply_updates(states["original_ltba"], indices))
    assert all(record_data(apply_updates(state, indices)) == expected_final for state in states.values())
    assert all(record_data(state) == expected_initial for state in states.values())
    operations = {
        "build": factories,
        "rewrite_one": {name: (lambda name=name: apply_updates(states[name], indices[:1])) for name in factories},
        "updates_100": {name: (lambda name=name: apply_updates(states[name], indices)) for name in factories},
        "build_plus_updates_100": {name: (lambda name=name: apply_updates(factories[name](), indices)) for name in factories},
    }
    rows = []
    for operation, jobs in operations.items():
        timings = measurements(jobs, repeats, 5, seed)
        for name, timing in timings.items():
            row = {"n": n, "backend": name, "operation": operation, **timing}
            if operation in ("build", "rewrite_one"):
                row.update(memory_measurement(jobs[name]))
            rows.append(row)
    return rows


def profile_pipeline():
    clear_cache()
    clear_caches()
    profiler = cProfile.Profile()
    profiler.runcall(pipeline, source_for("shifted_sum", 32), "ltba_flat")
    stats = pstats.Stats(profiler)
    top = sorted(stats.stats.items(), key=lambda item: item[1][3], reverse=True)[:15]
    return [{"file": key[0], "line": key[1], "function": key[2], "calls": value[1],
             "self_seconds": value[2], "cumulative_seconds": value[3]} for key, value in top]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", default="1,4,8,16,32")
    parser.add_argument("--storage-sizes", default="8,512,8192")
    parser.add_argument("--repeats", type=int, default=9)
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--output", type=Path, default=Path("results/cas_pipeline"))
    args = parser.parse_args()
    sizes = [int(value) for value in args.sizes.split(",")]
    storage_sizes = [int(value) for value in args.storage_sizes.split(",")]
    if args.repeats < 3 or min(sizes + storage_sizes) < 1:
        parser.error("Use at least three repeats and positive sizes")
    repository = Path(__file__).resolve().parents[1]
    checks = 0
    for family in FAMILIES:
        for n in range(1, 4):
            checks += validate(family, n, True, args.seed)
        for n in sizes:
            checks += validate(family, n, False, args.seed)
        print(f"validated {family}", flush=True)
    rows = []
    for family in FAMILIES:
        for n in sizes:
            rows.extend(measure_pipeline(family, n, args.repeats, args.seed))
            print(f"measured {family} n={n}", flush=True)
    legacy = load_legacy(repository)
    storage_rows = []
    for n in storage_sizes:
        storage_rows.extend(measure_storage(legacy, n, args.repeats, args.seed))
        print(f"measured original/improved storage n={n}", flush=True)
    paths = ("ltba/core.py", "ltba/components.py", "ltba/persistent.py", "ltba/cas.py", "benchmarks/cas_pipeline.py")
    report = {
        "benchmark": "LTBA text-to-JSON CAS simplification and storage improvements",
        "baseline_commit": BASELINE_COMMIT,
        "source_sha256": {path: hashlib.sha256((repository / path).read_bytes()).hexdigest() for path in paths},
        "environment": {"python": platform.python_version(), "sympy": sp.__version__, "platform": platform.platform()},
        "configuration": {**vars(args), "output": str(args.output)},
        "numeric_validation_checks": checks,
        "serialization_equality": "All backends matched complete JSON payloads on every timed call",
        "semantics": "Real symbols, numerator-preserving division by zero, zero at every integer power, principal square root",
        "scope": "All three pipeline backends share compile_text and SymPy arithmetic. The baseline keeps factored SymPy values and a tuple of complete provenance records. Timing includes parsing through JSON serialization. Imports and cache clearing are outside timing. Cleared cache clears SymPy caches before each timed call. These timings characterize the implemented arithmetic grammar and workloads.",
        "pipeline_rows": rows,
        "storage_rows": storage_rows,
        "profile": profile_pipeline(),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    for filename, data in (("pipeline.csv", rows), ("storage.csv", storage_rows)):
        fields = list(dict.fromkeys(key for row in data for key in row if not key.startswith("samples_")))
        with (args.output / filename).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            writer.writerows(data)
    print(json.dumps({"checks": checks, "pipeline_rows": len(rows), "storage_rows": len(storage_rows)}))


if __name__ == "__main__":
    main()
