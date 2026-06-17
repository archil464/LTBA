# LTBA semantics

This document explains the semantics of the LTBA prototype used in this
repository. It is written for reviewers evaluating design choices and
reproducibility.

What an LTBA expression denotes
- An `LTBAExpr` denotes a base algebraic payload together with a collection
  of local branch records. Each local branch record pairs an atomic guard with
  an algebraic payload value and an optional tag.

Local branch groups and interpretation
- Local branches are stored near the algebraic factor that introduced them.
- Independent local branch groups may be combined by Cartesian product to
  produce a global explicit representation (Piecewise-like). The prototype
  does not automatically perform this expansion.

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
- The prototype treats guards as strings only and does not solve division-by-zero
  or other guard satisfiability problems.
- Materialization may grow exponentially; conversion helpers should only be
  used for small examples and tests.
