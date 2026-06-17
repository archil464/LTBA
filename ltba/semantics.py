"""High-level semantics notes for the LTBA prototype.

This module is documentation-first and intended for reviewers. It explains how
the prototype interprets local branches and what it intentionally does not do.
"""

SEMANTICS_OVERVIEW = """
LTBA expressions pair ordinary algebraic payloads with local branch records.

- An `LTBAExpr` denotes the base algebraic expression together with a set of
  local branch records attached to parts of the expression.
- Local branch groups represent alternative payloads guarded by atomic
  `Guard` labels. The prototype does not attempt to reason about guard
  satisfiability; guards are treated as provenance-bearing opaque labels.
- Materializing an LTBA expression into a global explicit product (a
  Piecewise-like expansion) requires taking the Cartesian product of
  independent local branch groups. This can grow exponentially in the number
  of independent groups and is therefore expensive in general.

Differences vs Piecewise and BDD+payload:
- Piecewise: eagerly constructs a global disjunction/product of branches. LTBA
  keeps branches colocated with the algebraic factor that introduced them.
- BDD+payload: BDDs can compactly represent boolean guard structure but do not
  by themselves store algebraic payloads; combining a BDD with payloads
  typically requires a materialized payload table.

Assumptions and limitations:
- Guards are opaque strings; the prototype does not evaluate them or solve
  satisfiability. Division-by-zero and guard satisfiability are not solved.
- The conversion to explicit Piecewise may produce exponential blowup; use
  the provided materialization helpers only for small examples or testing.
"""
