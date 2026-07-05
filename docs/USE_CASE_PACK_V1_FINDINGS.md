# Use Case Pack v1 Findings

This document is auto-generated from the latest Use Case Pack v1 result artifacts.

Source artifacts:

- `results/use_cases_v1/use_case_pack_v1_report.json`
- `results/use_cases_v1/use_case_pack_v1_summary.csv`
- `results/use_cases_v1/use_case_pack_v1_winners.csv`

## Snapshot

- Generated (UTC): 2026-07-05T11:11:22.099404+00:00

## Scenario Winners

| Scenario | Winner: Time To Execute | Winner: Rewrite-One Latency | Winner: Branch Count |
|---|---|---|---|
| uc1_guarded_division_medium | ltba | ltba | ltba |
| uc2_radicals_sign_split | ltba | ltba | ltba |
| uc3_mixed_small_fastpath | explicit | explicit | ltba |

## Metric Snapshot

- `uc1_guarded_division_medium`
- ltba: time_to_execute_ms = 0.0315, rewrite_one_latency_ms = 0.0040, branch_count = 12 (local_branch_count)
- explicit: time_to_execute_ms = 0.0687, rewrite_one_latency_ms = 0.0120, branch_count = 64 (explicit_case_count)
- bdd: time_to_execute_ms = n/a, rewrite_one_latency_ms = n/a, branch_count = n/a (bdd_path_count)

- `uc2_radicals_sign_split`
- ltba: time_to_execute_ms = 0.0300, rewrite_one_latency_ms = 0.0029, branch_count = 16 (local_branch_count)
- explicit: time_to_execute_ms = 0.2836, rewrite_one_latency_ms = 0.0534, branch_count = 256 (explicit_case_count)
- bdd: time_to_execute_ms = n/a, rewrite_one_latency_ms = n/a, branch_count = n/a (bdd_path_count)

- `uc3_mixed_small_fastpath`
- ltba: time_to_execute_ms = 0.0036, rewrite_one_latency_ms = 0.0006, branch_count = 0 (local_branch_count)
- explicit: time_to_execute_ms = 0.0009, rewrite_one_latency_ms = 0.0004, branch_count = 1 (explicit_case_count)
- bdd: time_to_execute_ms = n/a, rewrite_one_latency_ms = n/a, branch_count = n/a (bdd_path_count)

## Interpretation

- LTBA is expected to perform best as guarded branching complexity increases.
- Explicit materialization may remain faster in near-trivial fast-path scenarios.
- BDD rows can be partially empty when the optional `dd` package is unavailable.

## Reproducibility

```bash
python -m benchmarks.use_case_pack_v1 --reproduce-results --repeats 7
python scripts/generate_use_case_findings.py
```
