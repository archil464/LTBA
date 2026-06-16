# Benchmarks

This folder is reserved for benchmark source code.

The current repository preserves benchmark outputs under `results/` and reproduction scripts under `scripts/`.

Planned benchmark suite:

## v0 — General guarded-local substrate

Initial LTBA general-substrate benchmark.

## v1 — Explicit materialization

Compares LTBA local form against explicit branch materialization and BDD guard skeletons.

## v2 — Equivalence and BDD+payload

Adds exhaustive/sampled equivalence checks and a BDD+factor-payload model.

## v3 — Timing

Measures build time, rewrite-one time, and rewrite-all time.

## v4 — Amortized runtime

Measures cold build plus `k` equal-work rewrites.

Primary target:

```text
fair_total_time = cold_build_time + rewrite_time(k)
