# LTBA — Locality-Preserving Tagged Branch Algebra

LTBA is an experimental guarded-local symbolic representation for computer algebra systems.

It is designed to preserve branch provenance locally instead of eagerly expanding expressions into global `Piecewise` forms.

## Core idea

Instead of immediately expanding local guarded expressions into a global branch product, LTBA stores branch information near the algebraic factor that generated it.

## What LTBA is

- a symbolic intermediate representation
- a CAS routing target
- a pre-Piecewise guarded-local normal form
- a benchmarked approach for branch-heavy symbolic workloads

## What LTBA is not

- not a replacement for all CAS systems
- not a replacement for BDDs
- not a replacement for Piecewise
- not a claim that division by zero is “solved”

## Current strongest claim

In v4 benchmarks, LTBA wins fair amortized runtime on nontrivial guarded symbolic workloads when compared with explicit branch materialization and full BDD+payload construction.

## Repository layout

```text
docs/              Explanations and technical notes
benchmarks/        Benchmark code by version
results/           Raw benchmark results
examples/          Small hand-checkable examples
review_packet/     Material for independent reviewers
scripts/           Helper scripts
archive/           Old generated zip/patch artifacts