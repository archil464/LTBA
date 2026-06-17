# LTBA — Locality-Preserving Tagged Branch Algebra

LTBA is a small research prototype that preserves local branch provenance
for symbolic algebraic expressions. It keeps guarded-local records attached
to algebraic factors rather than eagerly materializing a global Piecewise
product. The goal is reviewer-friendly, reproducible code that demonstrates
the representation tradeoffs.

Summary claim

LTBA preserves local branch provenance and avoids explicit global branch
materialization. In v4 benchmark families with nontrivial guarded symbolic
workloads, LTBA keeps representation size compact and often improves
build-time or fair-amortized runtime versus explicit Piecewise
materialization; results depend on workload family and rewrite pattern.

Installation

Clone the repository and (optionally) create a virtual environment. Then:

```bash
python -m pip install -r requirements.txt  # optional extras for full benchmarks
```

Quickstart

Start a Python REPL and import the package:

```python
from ltba import registry
print(registry.names())
```

Run tests

```bash
python -m pytest
```

Reproduce v4 benchmark results (writes to `results/v4/`)

```bash
python -m benchmarks.benchmark_v4 --reproduce-results
```

Repository layout

- `ltba/` — tracked source package (core model, components, conversion helpers)
- `benchmarks/` — reproducible benchmark runners (v4)
- `docs/` — human-readable semantics and notes
- `tests/` — pytest test-suite and smoke checks
- `results/` — benchmark outputs (generated via runner)
- `scripts/` — convenience scripts (not required for import or tests)
- `review_packet/` — supplementary reviewer materials (kept for context)

Limitations

- Guards are opaque labels in this prototype; we do not solve division-by-zero
  or general guard satisfiability. The `piecewise_conversion` helpers may
  grow exponentially and are intended for small examples and tests only.

If you are reviewing this project, prefer the tracked `ltba/` package and the
`benchmarks/benchmark_v4.py` runner; the `scripts/` helpers exist for
convenience but are not required to import or run the project.
