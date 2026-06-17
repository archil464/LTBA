# LTBA semantics

This document explains the semantics of the LTBA prototype used in this
repository. It is written for reviewers evaluating design choices and
reproducibility.

What an LTBA expression denotes
- An `LTBAExpr` denotes a base algebraic payload plus zero or more local
  branch groups. Each `LocalBranchGroup` represents alternatives generated
  by a single algebraic operation or transformation.

- A `LocalBranchGroup` contains a `group_id` and a tuple of `LocalBranch`
  alternatives. Branches in the same group are alternatives; different
  groups are independent unless guard analysis proves otherwise.

Local branch groups and interpretation
- Local branch groups are stored near the algebraic factor that introduced
  them. Materializing an LTBA expression means forming the Cartesian product
  across independent groups to produce explicit global cases.

Example: two groups with two alternatives each

```
LTBAExpr(
  base="f(x)",
  branch_groups=(
    LocalBranchGroup("g1", (LocalBranch(Guard("a"), "A"), LocalBranch(Guard("not a"), "B"))),
    LocalBranchGroup("g2", (LocalBranch(Guard("b"), "C"), LocalBranch(Guard("not b"), "D"))),
  )
)
```

Materializing the above example yields four global cases with combined guards
and combined payloads: (a and b -> A|C), (a and not b -> A|D), (not a and b -> B|C), (not a and not b -> B|D).

Guard provenance
- Guards are opaque provenance labels in this prototype. They are not
  evaluated, solved, or normalized. This design is intentional: the prototype
  focuses on representation and locality rather than symbolic satisfiability.

Differences from Piecewise and BDD+payload
- Piecewise eagerly materializes global branches; LTBA keeps branches local.
- BDDs can represent boolean guard structure compactly but do not itself
  store algebraic payloads — combining BDDs with payloads often requires
  external payload tables and materialization.

Assumptions and limitations
- Guards are opaque provenance labels in this prototype; we do not attempt
  logical simplification, satisfiability checking, or division-by-zero
  resolution.
- Materialization can grow exponentially in the number of independent groups
  and arities; use the provided conversion helpers only for small examples
  and tests.
