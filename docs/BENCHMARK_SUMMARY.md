# Benchmark Summary

## v1

Correctness benchmark against explicit Piecewise-style semantics.

## v2

Representation/compression benchmark against explicit branch expansion and BDD-style representations.

## v3

Timing benchmark measuring build, rewrite-one, and rewrite-all behavior.

## v4

Fair amortized benchmark:

- cold build
- equal-work local rewrites
- build + k rewrites
- break-even analysis

Current v4 runner enhancements:

- repeated trials via `--repeats`
- aggregate statistics (median/mean/min/max) for core timing metrics
- environment metadata in JSON output (Python/platform)
- optional per-trial rows via `--include-trials`

Main v4 result:

For nontrivial guarded workloads, LTBA wins fair total runtime against explicit materialization and full BDD+payload construction.
