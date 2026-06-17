# LTBA Technical Note Draft

## Title

LTBA: A Guarded-Local Algebraic Representation for CAS Branch Locality

## Abstract

We propose LTBA, Local Term Branch Algebra, as a CAS-internal representation for symbolic expressions whose branch structure is local to algebraic factors. Unlike explicit Piecewise expansion, LTBA stores guarded branch records at the algebraic source that generated them. Unlike a guard-first decision diagram, LTBA treats algebraic payload locality as the primary representation objective and uses decision-diagram ideas only as an optional backend for guard logic.

The v4 benchmark compares LTBA against explicit branch materialization and full BDD+payload construction under a fair amortized metric: cold construction plus repeated equal-work payload rewrites. In the tested nontrivial guarded symbolic workloads, LTBA gives the best fair total runtime while preserving equivalence to explicit branch semantics in exhaustive or sampled checks.

## Main claim

LTBA is not a universal replacement for BDDs, ADDs, Piecewise, or ordinary CAS expression trees. It is a routing target for expressions where branch structure is local to algebraic factors and where repeated local rewrites or provenance preservation matter.

## Representation intuition

A global Piecewise representation expands branch combinations. LTBA stores each source of guarded branching independently:

```text
factor_1 -> local guarded branches
factor_2 -> local guarded branches
...
factor_n -> local guarded branches
```

The full branch semantics is interpreted lazily as the product of local branch choices. This allows local rewrites to affect the local source branch record rather than every global branch combination.

## CAS integration

LTBA should be selected by a routing policy:

- ordinary expression tree for unguarded expressions;
- Piecewise for final small explicit output;
- BDD/ADD for pure guard logic and heavily shared Boolean structure;
- LTBA for guarded-local algebraic payloads and singular provenance.

## Benchmark summary

v4 measures:

```text
cold build + k repeated equal-work rewrites
```

Fair backends:

```text
ltba_local_persistent
explicit_materialized
bdd_full_cow_payload
```

Lower-bound-only BDD rows:

```text
bdd_payload_only_cow_lower_bound
bdd_payload_only_mutable_lower_bound
```

The lower-bound BDD rows should not be interpreted as full-system wins because they omit guard-skeleton construction.

## Claims to avoid

Do not claim LTBA beats all BDDs or replaces Piecewise. Claim that LTBA is a selective CAS representation that wins the tested amortized-runtime workloads.
