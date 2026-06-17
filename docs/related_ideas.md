# Related ideas and distinctions

This note situates LTBA with respect to several existing ideas and
representations. The tone is intentionally humble and precise: LTBA does not
claim to invent guarded computation from scratch. Instead it explores a
focused CAS-oriented representation choice: preserve branch provenance
locally, close to the algebraic operation that introduced it, and delay
global case materialization until explicitly requested.

## Overview

LTBA overlaps in motivation and surface form with a number of earlier and
concurrent ideas:

- Piecewise expressions and conditional expressions
- Symbolic execution path conditions
- CAS assumption systems (local/global assumptions like `x>0`, `y!=0`)
- Protected simplification (heuristics that avoid unsafe rewrites)
- Expression DAGs (structural sharing, common subexpressions)
- BDDs, MTBDDs, and algebraic decision diagrams (decision-diagram
  representations for Boolean structure and payloads)

Intended distinction

LTBA keeps branch information in explicit local branch groups attached to
the algebraic transformation that introduced the branch. Global
materialization (Piecewise enumeration) is delayed and performed only when
explicitly requested by a conversion helper. This emphasis on local
provenance and delayed expansion is the concrete design point the project
explores.

## Versus Piecewise

Piecewise or guarded-case expressions represent global guarded cases and
are mathematically clear and convenient for reasoning and simplification.
However, when independent guarded sources are combined eagerly, explicit
Piecewise expansion can create a Cartesian-product explosion of cases.

LTBA stores branch sources separately as local branch groups attached to
the algebraic operations that produced them. Explicit Piecewise-like
materialization remains possible later via conversion helpers, but it is
not the primary immediate representation.

Example (informal): consider the expression

```
sqrt(x^2) + 1/y
```

- ordinary expression: a tree/DAG representing `sqrt(x^2) + 1/y`.
- radical/sign local branch group: the `sqrt(x^2)` operation may introduce
  a sign alternative for square-root simplification (e.g., `x` vs `-x`).
- division/domain local branch group: the `1/y` operation introduces a
  domain/division guard (e.g., `y != 0` vs `y == 0` -> blocked branch).

Materializing both groups into an explicit Piecewise list of cases will
produce the Cartesian product of the radical choices and the division
choices, even if those branches are locally unrelated.

## Versus BDDs and decision diagrams

BDD-style data structures optimize or canonicalize global Boolean decision
structure; MTBDDs and algebraic decision diagrams attach payloads to
leaves and can be compact for certain workloads. LTBA does not attempt to
replace BDDs or to be a canonical decision-diagram format.

Key differences:

- BDD-style representation: optimize or canonicalize a global Boolean
  decision structure, often with a focus on canonical minimality for a
  given variable ordering.
- LTBA: preserve local algebraic provenance (which operation introduced
  which branch) and delay global branch-product expansion.

LTBA expressions could be exported to a BDD-like representation for
post-hoc analysis or comparison, but that is an orthogonal target — the
native design goal is to keep provenance and algebraic structure explicit
and local.

## Versus symbolic execution path conditions

Symbolic execution records program path conditions derived from control
flow. LTBA records guard conditions that arise from algebraic
transformations: domain constraints, removable singularities, inverse
existence conditions, alternate solver branches, and similar algebraic
phenomena.

Similarity: both track conditions under which symbolic values are valid.

Difference: LTBA's guards are not program-branch path predicates per se;
they are algebraic provenance markers tied to CAS transformations. LTBA
can be viewed informally as a path-condition-like provenance for CAS
transformations, but it is not a program-analysis framework.

## Versus CAS assumption systems

CAS assumption engines manage facts like `x > 0` or `n is integer` and
provide reasoning/simplification based on discharged assumptions. LTBA is
not an assumption solver: it stores unresolved local guards as part of an
expression's representation. A separate assumption engine could be used to
discharge, simplify, or merge these local guards and thereby reduce local
branch groups.

## Versus protected simplification

Protected simplification practices refuse or delay unsafe rewrites that
change domains or drop branch information. LTBA shares the motivation but
proposes a concrete intermediate representation for guarded rewrites: keep
local alternatives attached to a node instead of either rejecting the
rewrite or immediately globalizing it.

## Versus ordinary expression DAGs

Expression DAGs provide structural sharing and compact representation; they
usually do not explicitly track the provenance of guarded alternatives.
LTBA can be seen as a DAG-like representation augmented with local guarded
alternatives where provenance (why a branch exists) is first-class.

## What LTBA is trying to contribute

LTBA explores a design point between three familiar choices:

- ordinary expression DAG: compact, but may hide branch/domain obligations
- global Piecewise: explicit and mathematically clear, but can eagerly
  explode
- BDD/decision diagram: compact for Boolean structure, but less focused
  on algebraic provenance

LTBA's proposed design point is: local guarded branch groups attached to
algebraic provenance, with optional later materialization into global
cases. The current prototype is an idea-transfer artifact: a small
implementation that makes this design point concrete enough for researchers
in CAS, symbolic computation, and formal methods to evaluate.

## Non-claims

LTBA does not currently claim to:

- replace Piecewise
- replace BDDs or algebraic decision diagrams
- solve guard satisfiability
- solve division by zero
- provide complete formal semantics for all CAS operations
- prove rewrite correctness
- handle all branch cuts of complex functions

## Pointers to related work

Plain-text pointers (not exhaustive, presented for orientation):

- Bryant, R. E. Binary decision diagrams and symbolic model checking.
- Clarke, E. M.; Fujita, M.; Zhao, X. Multi-terminal binary decision diagrams.
- England, M.; Bradford, R.; Davenport, J. H.; Wilson, D. Understanding branch cuts of expressions.
- Stoutemyer, D. R. Ten commandments for good default expression simplification.
- Research on algebraic decision diagrams and guarded symbolic representations.
