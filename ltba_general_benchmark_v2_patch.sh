# LTBA Review Request Template

Use this when asking SymPy/Sage/CAS people for feedback.

## Short message

Hello,

I am looking for expert feedback on a benchmark-backed CAS representation idea called **LTBA**: Local Term Branch Algebra.

I am not claiming it replaces BDDs, ADDs, Piecewise, or CAS assumptions. The claim is narrower:

> LTBA is a guarded-local algebraic representation for expressions whose branch structure is local to algebraic factors. It avoids eager global Piecewise expansion and preserves branch provenance. In the v4 benchmark, it wins fair amortized runtime for nontrivial guarded symbolic workloads under a cold-build plus repeated-rewrite metric.

The repository contains:

- v0-v4 benchmark patches;
- v4 benchmark outputs;
- a CAS routing policy;
- a novelty statement with claims to avoid;
- reproducibility commands.

I would appreciate feedback on whether this is already known under another name, whether the benchmark is flawed, or whether the idea is worth formalizing as a CAS internal representation/routing strategy.

Thank you.
