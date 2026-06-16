# Publication Plan

## Recommended order

1. Commit this overlay to the GitHub repository.
2. Tag a release: `v4-ltba-cas-routing`.
3. Archive the release on Zenodo to get a DOI.
4. Ask for targeted expert review from SymPy/Sage/CAS people.
5. Prepare a short 6-10 page technical note.
6. Submit to arXiv under `cs.SC` / `cs.MS` after review.
7. Later consider ISSAC/CASC/SCSS/workshop submissions.

## Positioning

Do not lead with division by zero. Lead with CAS representation and routing:

> LTBA is a guarded-local algebraic representation for symbolic expressions whose branch structure is local to algebraic factors.

## Recommended public claim

> LTBA is not a replacement for BDDs or Piecewise expressions; it is a CAS routing target. In the v4 benchmark, it outperforms explicit materialization and full BDD+payload construction on nontrivial guarded symbolic workloads under a fair amortized build-plus-rewrite metric.

## First reviewers to ask

- SymPy developers / discussion forum
- SageMath development list
- CAS researchers familiar with symbolic computation, rewriting, and decision diagrams
- Formal methods people interested in guarded rewriting / provenance
