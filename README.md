# LTBA — Locality-Preserving Tagged Branch Algebra

LTBA is a small research prototype demonstrating a locality-preserving
approach to tracking guarded local branch provenance for symbolic expressions.
It attaches guarded-local records to algebraic factors instead of eagerly
materializing a global piecewise product. The goal is a reviewer-friendly,
reproducible prototype that makes the representation tradeoffs explicit —
not a production CAS or a formally-verified theory.

Summary (honest tone)

This repository contains a working prototype that implements the demo
components `LTBA-0` through `LTBA-2`. If `LTBA-3` through `LTBA-7` are
restored in future commits they will be documented; currently those are not
available in the tracked `ltba/` package.

The `benchmarks/benchmark_v4.py` runner includes two simple baselines:

- an explicit-materialization baseline (construct and time the Cartesian
  product of local branches where feasible), and
- a light-weight BDD-based skeleton baseline that attempts to measure a
  path-counting style cost when the optional `dd` package is available.

These baselines are exploratory and intentionally simple. They are provided
to help reviewers quickly reproduce and inspect the instrumentation and to
illustrate the "fair-amortized" metric used in the project — they are not a
definitive comparison against optimized industrial BDD implementations.

Installation

Clone the repository and (optionally) create a virtual environment. Then:

```bash
python -m pip install -e .

# Optional developer/test tools
python -m pip install -e .[dev]

# Optional benchmark extras (BDD baseline)
python -m pip install -e .[benchmark]
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

Run Use Case Pack v1 comparisons (LTBA vs explicit vs BDD)

```bash
python -m benchmarks.use_case_pack_v1 --reproduce-results --repeats 7
```

Repository layout

- `ltba/` — tracked source package (core model, components, conversion helpers)
- `benchmarks/` — reproducible benchmark runners (v4)
- `docs/USE_CASE_PACK_V1.md` — scenario comparison pack and metrics definitions
- `docs/` — human-readable semantics and notes
- `tests/` — pytest test-suite and smoke checks
- `results/` — benchmark outputs (generated via runner)
- `scripts/` — convenience scripts (not required for import or tests)
- `review_packet/` — supplementary reviewer materials (kept for context)

Related ideas

LTBA overlaps with Piecewise expressions, guarded conditionals, symbolic
execution path conditions, CAS assumption systems, protected simplification,
expression DAGs, and decision diagrams. Its intended distinction is local
provenance: LTBA stores unresolved branch obligations near the algebraic
operation that introduced them, delaying global materialization until
explicitly requested. See `docs/related_ideas.md` for a longer discussion.

Limitations

- Guards are opaque labels in this prototype; we do not solve division-by-zero
  or general guard satisfiability. The `piecewise_conversion` helpers may
  grow exponentially and are intended for small examples and tests only.

If you are reviewing this project, prefer the tracked `ltba/` package and the
`benchmarks/benchmark_v4.py` runner; the `scripts/` helpers exist for
convenience but are not required to import or run the project.

BDD note

- The BDD-style baseline in `benchmarks/benchmark_v4.py` is optional and
  depends on the third-party `dd` package. If `dd` is not installed on your
  environment the BDD-related columns in benchmark CSV/JSON outputs may be
  empty or omitted. The explicit-materialization baseline and the
  `ltba`-tracked measurements remain available regardless.

For formalization collaborators

This repository is an idea-transfer prototype. It intentionally leaves several
formal questions open for collaborators who want to pursue a formal treatment:

- Guard satisfiability: guards are modeled as opaque labels; the repository
  does not provide a decision procedure for satisfiability or SMT-style
  reasoning about guards.
- Semantic equivalence: the prototype does not include a general-purpose
  semantic equivalence engine for algebraic expressions under guards.
- Rewrite correctness proofs: rewrites and `rewrite_local` operations are
  implemented as experimental helpers with unit tests, but the repository
  does not ship formal proofs of correctness or preservation theorems.

If you are interested in formalization work, please open an issue or a PR and
we can add pointers, formalization tasks, and a separate branch for proofs.

Packaging / creating a clean review zip

To produce a zipped reviewer artifact that excludes `.git` and common cache
files you can either use `git archive` (recommended when working from a
repository) or the provided helper script in `scripts/make_review_zip.sh`.

Example using `git archive` (produces `ltba-review.zip`):

```bash
git archive --format=zip --output=ltba-review.zip HEAD
```

Fall-back (no git):

```bash
# from repo root
scripts/make_review_zip.sh ltba-review.zip
```

The helper script will exclude `.git`, `__pycache__`, `.pytest_cache`, build
artifacts, and `dist/` so the produced zip is reviewer-friendly and small.
