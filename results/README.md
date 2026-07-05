# LTBA Benchmark Results

This folder stores raw benchmark outputs by benchmark version.

## v0

Initial general guarded-local substrate benchmark.

## v1

Explicit materialization and BDD guard-skeleton comparison.

## v2

Equivalence checking, sampled/exhaustive validation, and BDD+factor-payload model.

## v3

Timing benchmark for build, rewrite-one, and rewrite-all.

## v4

Fair amortized benchmark measuring cold build plus `k` equal-work rewrites.

Primary files:

- `ltba_general_benchmark_v4_summary.csv`
- `ltba_general_benchmark_v4_break_even.csv`
- `ltba_general_benchmark_v4_timing_rows.csv`
- `ltba_general_benchmark_v4_report.json`

## use_cases_v1

Scenario-oriented LTBA vs explicit vs BDD comparison outputs.

Primary files:

- `use_case_pack_v1_summary.csv`
- `use_case_pack_v1_winners.csv`
- `use_case_pack_v1_report.json`

Interpretation summary is published at:

- `docs/USE_CASE_PACK_V1_FINDINGS.md`
