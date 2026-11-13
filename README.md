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

The optional arithmetic simplifier uses SymPy for local algebra while retaining
each visited division occurrence and its zero case. Install it with
`python -m pip install -e '.[cas]'`.

```python
from ltba import simplify_text

result = simplify_text("(x^2-1)/(x-1)")
print(result.value)               # Piecewise((x + 1, Ne(x, 1)), (0, True))
print(result.evaluate({"x": 1}))  # 0
print(result.to_dict())           # value and source-specific guarded records
```

This entry point accepts arithmetic, integer powers, `abs`, and `sqrt` with
real symbols. It uses `a/0 = a` and the project's separate integer-power rule
`0**n = 0`, including zero and negative exponents. Square roots use the principal
branch. Conditional values remain factored. General equation solving and
calculus are outside this entry point's implemented grammar.

Existing component factories now construct branch groups in bulk. For repeated
indexed updates, `expr.with_storage("tree")` creates a persistent balanced tree.
Default storage remains a tuple. The tree supports sequence indexing, slicing,
iteration, and value equality. Conversion and iteration cost O(n). Indexed
replacement copies O(log n) tree nodes, plus the copied rewrite history. Appending
rebuilds the tree, so initial groups should be constructed in bulk.

Run the complete text-to-JSON and original-versus-improved storage comparison with
`python -m benchmarks.cas_pipeline`. Its factored SymPy baseline uses the same
algebra kernel and preserves identical guard and provenance output.

The incremental workbook supports named formulas and atomic batches of edits.

```python
from ltba.workbook import Workbook

book = Workbook.build({"a": "x/x", "b": "a+1", "c": "b*b"})
edited = book.update_many({"a": "x/x+0", "c": "b*b+1"})
print(edited.recomputed)
print(edited.delta())
print(edited.evaluate("c", {"x": 0}))
```

`update_many` accepts existing formula names and replacement source. It returns a
new snapshot after every edit succeeds. Syntax errors, unsupported operations,
and dependency cycles leave the prior snapshot usable. Reverse dependency links
locate affected formulas. A priority queue orders their recalculation, and an
equal value stops further numeric propagation. Equality uses structural equality
and an exact polynomial check. Cases without a proof of equality propagate.
An equivalent value keeps its previous representative, so rendering can differ
from a fresh rebuild while the values agree.

`delta()` returns changed cell payloads, value and provenance change lists, and
the recalculated names. Clients can patch an existing `to_dict()` result with the
delta's `cells`. Provenance is local to a formula and linked through dependency
names. An upstream source edit can therefore change a dependent's explanation
without requiring a new numeric value for that dependent. Revision numbers are
local to a snapshot branch.

Each cell reports its simplification assumptions. External parameters are real.
Intermediate dependency values that are not provably real are bound before
simplification, so a dependent formula can handle complex intermediate results
without reusing a real-only simplification. Named integer exponents are also
bound when required. Unsupported exponents fail the complete transaction.

Bounded caches share immutable formula results and algebraic subexpressions.
Source occurrences keep distinct local provenance records. `ltba.cas.cache_info()`
reports cache statistics, and `ltba.cas.clear_caches()` clears these caches for
cold measurements. Workbook snapshots still copy their state dictionaries, and
dependency rewiring validates the whole graph. These costs remain proportional
to workbook size even when only a small region needs algebraic recalculation.

`python -m benchmarks.workbook_incremental` compares warm repeated edits against
both full rebuilding and an independent implementation of a conventional cached
dependency DAG. Both incremental engines preserve snapshots, validate assumptions,
stop on equal values, and return equivalent provenance. It measures changed-cell
and full serialization separately. Comparisons against released calculator or
spreadsheet applications remain future work.

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

Published findings snapshot:

- `docs/USE_CASE_PACK_V1_FINDINGS.md`

Repository layout

- `ltba/` — tracked source package (core model, components, conversion helpers)
- `benchmarks/` — reproducible benchmark runners (v4)
- `docs/USE_CASE_PACK_V1.md` — scenario comparison pack and metrics definitions
- `docs/USE_CASE_PACK_V1_FINDINGS.md` — current published comparison outcomes
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

- Core `Guard` objects are opaque labels. The optional `ltba.cas` module constructs
  and evaluates SymPy conditions for its supported arithmetic grammar. General
  guard satisfiability remains outside the implementation. The `piecewise_conversion` helpers may
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

### Sparse snapshots and cold-cache trials

Workbook transactions now use bounded immutable mapping overlays. Unchanged
entries are shared across snapshots, with compaction after 16 overlay generations
or when more than half the entries change. Compaction still costs O(n), and
rewiring still validates the dependency graph. A small edit therefore avoids
ordinary full-map copying, but this is not a worst-case O(1) update guarantee.

`update_many(edits, strategy="incremental")` propagates changed values.
`strategy="rebuild"` forces all cells through recalculation while retaining the
same value-equivalence and provenance rules. The default `"auto"` currently uses
incremental scheduling. An experimental direct-fan-out threshold did not improve
measured broad-update performance, so automatic switching was disabled.

Run `python -m benchmarks.workbook_novel` for successive edits with LTBA,
syntax, and SymPy caches cleared before each timed operation. Results include
changed-cell JSON serialization and are checked against fresh rebuilds. These
numeric workloads complement the earlier symbolic warm-cache workloads and must
not be used as a direct before/after speed comparison.

The project tracks two distinct goals:

1. **Speed:** equivalent answers, assumptions and provenance, measured end to
   end against optimized conventional implementations and eventually released tools.
2. **Capability:** a specified problem with independently verifiable answers
   that a stated conventional method cannot obtain. A tool timing out is a
   practical limit, not proof of mathematical impossibility. Defining a value
   at division by zero does not alone establish additional solving capability.

Neither goal has yet been established against released competing software.
Conventional guarded expressions can encode the division fallback used here.
The latest comparison remains an implementation experiment using a shared
arithmetic kernel, not evidence that conventional mathematics cannot express LTBA.

### Division by zero as a no-op

The division operator evaluates its operands and applies

```
D(a, b) = a / b  if b != 0
D(a, b) = a      if b == 0
```

“No-op” means that the zero-denominator division leaves the evaluated numerator
unchanged. Thus `7/0 = 7`, `0/0 = 0`, and `(3+4)/(x-x) = 7`.
Multiplication still destroys a value at zero: `(7*0)/0 = 0` and `(7/0)*0 = 0`.
This rule was already active in the CAS kernel; it is now explicit and covered by
focused regression examples. Source division occurrences retain local provenance.

The rule applies to the written expression before cancellation. At `x=1`,
`(x*x-1)/(x-1)` evaluates to `0/0`, hence zero. Replacing the expression
unconditionally by `x+1` would lose that behavior. Its ordinary limit remains 2.
Likewise `(x/y)*y` cannot be replaced unconditionally by `x` at `y=0`.
The separate integer-power policy remains `0**n = 0`, including nonpositive n;
negative powers therefore must not be silently rewritten as no-op division.

`python -m benchmarks.singular_interactions` checks coupled products, interacting
rational sums, and nested divisions against an independent conventional SymPy
Piecewise compiler and an exact Fraction evaluator. Construction timings are
explicitly unequal-output diagnostics: LTBA also records provenance. Both retain
local conditions instead of forcing a global case expansion. These results do not
establish an impossibility for conventional methods.

Division provenance records three distinct guards: denominator zero
(`zero-no-op`), denominator positive one (`positive-one`), and other nonzero
denominators (`regular`). Zero and positive one keep separate source records
when the simplified values coincide. In a workbook, a template guard can refer
to a named dependency. A delta for that dependency can change which guard
applies at many division sites without resending each site's formula.

Run `python -m benchmarks.shared_division_provenance` to compare shared
denominator edits with a conventional dependency DAG using the same compiler.

The workbook skips value recomputation on a shared denominator's exact
`0 ↔ +1` transition for an unchanged quotient whose sole workbook dependency
is its bare denominator. Both cases return the same numerator. The division
guards still resolve separately through the shared dependency. Edits to the
quotient itself and transitions to other denominators follow ordinary
recalculation. The shared-denominator benchmark also measures a conventional
DAG supplied with the same shortcut.

For explicit algebraic rewrites, pass `transform="factor"`, `"expand"`,
`"collect"` (with `collect="x"`), or `"together"` to `simplify_text`.
Polynomial rewrites treat guarded values as whole subexpressions. Fraction
combination uses each divisor's guarded factor, which equals one at exact zero.
Left-nested division chains use those factors by default and keep one source
record per division. Ordinary cancellation remains inside the nonzero branch.
Equal denominator expressions share cached guard objects, with separate records
for each source occurrence.

Run `python -m benchmarks.shared_guard_computation` to compare per-site and
shared guard resolution while materializing the same complete division trace.

For a quotient multiplied by the same written divisor, the CAS returns the
numerator on the nonzero branch and zero on the zero branch. Nested source
operations retain their separate records. Negative powers retain their own
zero policy, so `x**(-1)` and `1/x` remain distinct at zero.

Use `simplify_text("1/(x-1)").solve_equal("x", 1)` for guarded real equality
solving. This returns `{1, 2}`: the zero branch yields 1 at `x=1`, and the
ordinary branch yields 1 at `x=2`. The solver restricts each branch to its
guard domain. When a guard depends on another symbol or cannot be converted
to a set, it returns the exact conditional equation as a SymPy ConditionSet.

For signed sums of proportional affine quotients, use
`ltba.solve_equal_text(source, "x", target)` to solve directly from source.
It groups exact denominator roots without constructing a symbolic sum.
The original numerator supplies the value at a zero divisor. Other expressions
fall back to the general CAS. To inspect the compact audit, use
`ltba.point_audit.compile_point_audit(source, "x")`. Each entry in `audit.sites`
keeps its source span and reports its branch and exact value via `trace_at(x)`.

For large sums supplied as an iterable, pass one complete addend per line to
`compile_point_audit_terms(terms, "x")`. This retains only one addend's syntax
tree at a time. The audit still stores root corrections and one trace record
per source division. Use `audit.equality(target)` for the compact exact result:
`default` indicates whether ordinary points satisfy the equality, and `points`
lists the exceptions to that answer. Call `to_sympy()` to export a SymPy set.

For ordinary division, `cancel_ordinary(source, "x")` returns a canceled
expression together with its original real domain and source guards. For
example, the expression `(x**2-3*x+2)/(x-1)` from SymPy issue #5344 reduces to
`x-2` on the reals except 1. The result's `evaluate(1)` rejects that point.
`audit_ordinary_rewrite(original, replacement, "x")` also reports where a
replacement adds or removes domain points and where the two values agree.
The ordinary audit currently supports univariate rational expressions with
integer literals and nonzero literal integer powers.

Two helpers accept SymPy `Piecewise` expressions. For the integer refinement
case in SymPy #27627, `refine_integer_piecewise(p, x, x < 1000)` proves the
default polynomial agrees on every active integer branch under the assumption
before returning it. For the one-sided limit case in SymPy #26313, use
`piecewise_side_limit(p, x, 2, direction="+")`. It chooses the branch on the
requested side of a finite real point, then computes its ordinary limit.
These helpers support univariate guards. The limit helper requires guards
that resolve to intervals or points and reports if the requested side has
no adjacent domain.
