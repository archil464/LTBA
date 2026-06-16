# LTBA CAS Routing Policy

This document defines when the CAS should route an expression into LTBA instead of ordinary simplification, explicit Piecewise, or a BDD/ADD-style backend.

## Use ordinary CAS representation when

Use the normal expression tree when:

- there are no symbolic guards;
- there are no singular denominators;
- no domain-sensitive transformation is being performed;
- simplification is purely algebraic and globally safe;
- the expression does not need branch provenance.

Examples:

```text
x + x                       -> ordinary CAS
sin(x)^2 + cos(x)^2         -> ordinary CAS
expand((x+1)^2)             -> ordinary CAS
```

## Use Piecewise when

Use explicit Piecewise when:

- the branch count is tiny;
- the result is final output for a user;
- exact visible conditions are required;
- the CAS is exporting to a backend that expects Piecewise;
- the expression will not undergo many local rewrites.

Good Piecewise cases:

```text
abs(x)
small manually inspectable branch expressions
final display form
```

Avoid Piecewise when:

- the branch count is a product of local branch factors;
- local rewrites should not touch unrelated branches;
- branch provenance must remain attached to local algebraic facts.

## Use BDD / ADD / decision diagrams when

Use BDD/ADD-style structures when:

- the primary problem is Boolean guard reasoning;
- guards are heavily shared;
- canonical equivalence of guard logic is more important than algebraic payload locality;
- many expressions share the same guard skeleton;
- SAT/equivalence/minimization over guards is the central operation;
- the expensive skeleton build cost can be amortized across many operations.

Good BDD cases:

```text
pure guard simplification
large shared Boolean guard sets
checking whether two guard partitions are equivalent
```

## Use LTBA when

Use LTBA when:

- the expression has many independent or semi-independent local branch factors;
- algebraic payloads are attached to local guarded facts;
- explicit Piecewise would multiply branches;
- branch provenance matters;
- local rewrites are expected;
- singular states must be preserved rather than erased;
- the expression mixes different symbolic subsystems.

Strong LTBA candidates:

```text
x/x
(x^2-a^2)/(x-a)
sqrt(x^2)
log(x*y) with domain guards
inequality transformations depending on sign
matrix inverse with det(A) guard
removable limits
solver transformations with singular provenance
mixed expressions combining the above
```

## Practical routing heuristic

Route to LTBA if any of the following are true:

```text
1. estimated_branch_product > explicit_piecewise_cap
2. local_guard_count >= 4 and expression will be rewritten
3. singular denominator or removable singularity is detected
4. domain-sensitive rewrite would otherwise duplicate payload
5. provenance/auditability is required
6. expression contains mixed guarded subsystems
```

Route away from LTBA if:

```text
1. no guards exist
2. final user-facing output is required
3. guard logic is purely Boolean and heavily shared
4. BDD skeleton already exists and many guard-only queries are expected
5. explicit branch count is very small and no repeated rewrites are expected
```

## Decision table

| Situation | Preferred representation |
|---|---|
| No guards, no singularities | ordinary CAS |
| Final small conditional expression | Piecewise |
| Pure Boolean guard reasoning | BDD/ADD |
| Guarded algebra with local payloads | LTBA |
| Mixed symbolic subsystems | LTBA |
| Heavy shared guard skeleton | BDD + payload or hybrid |
| Need export/readability | LTBA -> Piecewise |

## Hybrid recommendation

The strongest system is not LTBA alone. The strongest system is:

```text
LTBA as algebra-first guarded-local normal form
BDD/ADD as optional guard-logic backend
Piecewise as export/display form
ordinary CAS as default unguarded representation
```
