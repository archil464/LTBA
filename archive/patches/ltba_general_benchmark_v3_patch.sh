# LTBA v4 Freeze Note

Status: **frozen as benchmark-backed CAS patch candidate**

This document freezes the v4 interpretation of LTBA as a guarded-local representation strategy for CAS systems.

## Frozen claim

LTBA should be treated as a **guarded-local symbolic representation**, not as a universal replacement for Piecewise, BDDs, ADDs, or the ordinary expression tree.

The benchmark-backed claim is:

> For nontrivial guarded symbolic expressions, LTBA gives the best fair total runtime in the tested benchmark when measuring cold construction plus repeated local rewrites. It avoids both explicit branch materialization and expensive BDD guard-skeleton construction, while preserving lazy equivalence to explicit branch semantics in the tested cases.

## What is frozen

v4 freezes the following interpretation:

1. LTBA is a CAS-internal intermediate form.
2. LTBA is useful when algebraic payload locality matters.
3. LTBA is useful when explicit Piecewise expansion would multiply branches.
4. LTBA is useful when the same symbolic object will undergo local rewrites.
5. LTBA is not claimed to be universally smaller or faster than BDD/ADD-style structures.
6. BDD/ADD-style structures remain appropriate for pure guard logic, canonical Boolean reasoning, and shared-guard compression.
7. Piecewise remains the correct final/export form when explicit user-facing conditional output is needed.

## Main v4 interpretation

The fair comparison is:

- `ltba_local_persistent`
- `explicit_materialized`
- `bdd_full_cow_payload`

The following rows are lower bounds and should not be used as full-system wins:

- `bdd_payload_only_cow_lower_bound`
- `bdd_payload_only_mutable_lower_bound`

The payload-only BDD rows measure payload-table update cost without full guard-skeleton construction and are useful only as a theoretical lower bound.

## Routing conclusion

LTBA should be added to the CAS system as a **routing target**:

```text
ordinary expression
  -> ordinary CAS simplifier

guarded/singular/local expression
  -> LTBA guarded-local representation

pure Boolean guard logic
  -> BDD/decision-diagram backend

small explicit conditional output
  -> Piecewise
```

## Frozen warning

Do not claim:

> LTBA beats all BDDs.

Do claim:

> LTBA is an algebra-first guarded-local CAS representation that wins fair amortized runtime on the tested nontrivial guarded symbolic workloads.
