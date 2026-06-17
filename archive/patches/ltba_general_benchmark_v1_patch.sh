# LTBA Novelty Statement

## Short answer

Yes, LTBA can be claimed as **new as a CAS patch/representation strategy**, provided the claim is stated carefully.

We should not claim that every ingredient is new. Guarded expressions, Piecewise forms, BDDs, ADDs, MTBDDs, XADDs, and symbolic domain assumptions already exist.

The defensible novelty is the combination and routing policy:

> LTBA is an algebra-first guarded-local normal form for CAS systems that preserves singular/local branch provenance and avoids eager global Piecewise expansion, while remaining exportable to explicit branch semantics and comparable to BDD+payload models.

## What is not new

The following ideas are established and should be cited as prior art:

1. Boolean decision diagrams for compact Boolean function representation.
2. Algebraic / multi-terminal decision diagrams for non-Boolean terminal values.
3. Piecewise symbolic expressions.
4. Domain guards and assumptions in CAS systems.
5. Symbolic branch conditions.

## What appears new enough to claim

The new contribution is not simply "conditions attached to expressions."

The new contribution is:

1. **Algebra-first locality**: branch records stay attached to the algebraic factor that produced them.
2. **Lazy global branch semantics**: full Piecewise expansion is an interpretation/export, not the native form.
3. **Singular-state preservation**: singular cases are not erased by cancellation or domain filtering.
4. **Subsystem generality**: the same guarded-local substrate hosts division, radicals, inequalities, transcendental domains, matrix inverse guards, removable limits, and solver provenance.
5. **CAS routing policy**: LTBA is used only when guarded-local algebra is predicted to beat Piecewise/BDD/ordinary forms.
6. **Benchmark-backed amortized runtime claim**: v4 compares cold build plus k equal-work rewrites and shows LTBA wins meaningful tested guarded cases.

## Suggested public claim

Use this wording:

> We introduce LTBA, a guarded-local algebraic representation for CAS systems. LTBA is not a replacement for BDDs or Piecewise expressions; it is a routing target for expressions whose branch structure is local to algebraic factors. In our v4 benchmark, LTBA outperforms explicit materialization and full BDD+payload construction on nontrivial guarded symbolic workloads under a fair amortized build-plus-rewrite metric.

## Claims to avoid

Avoid:

```text
LTBA is the first guarded symbolic representation.
LTBA is universally better than BDDs.
LTBA proves division by zero is solved.
LTBA replaces Piecewise.
LTBA replaces CAS assumptions.
```

Prefer:

```text
LTBA is a new CAS-internal guarded-local normal form.
LTBA is a selective optimization and provenance strategy.
LTBA works best for local symbolic branch payloads.
LTBA complements BDDs and Piecewise rather than replacing them.
```

## Research positioning

The correct positioning is:

```text
Piecewise: output/display/global branch semantics
BDD/ADD/XADD: guard-logic and decision-diagram compression
LTBA: algebra-first local guarded payload representation
```

LTBA should be presented as a practical CAS architecture contribution, not as a replacement for all decision diagrams.
