# Use Case Pack v1

Use Case Pack v1 compares LTBA against two established approaches:

- `ltba`: locality-preserving tagged branch representation
- `explicit`: piecewise-style global materialization baseline
- `bdd`: BDD skeleton baseline (optional, requires `dd`)

## Metrics

For each scenario and backend:

- `time_to_execute_s` / `time_to_execute_ms`:
  median build time + median rewrite-all time across repeated trials
- `rewrite_one_latency_s` / `rewrite_one_latency_ms`:
  median rewrite-one latency across repeated trials
- `branch_count`:
  backend branch/path footprint proxy

Winner columns are produced per scenario for:

- time to execute
- rewrite-one latency
- branch count

## Scenarios

- `uc1_guarded_division_medium`: guarded cancellation workload (`LTBA-1`, n=6)
- `uc2_radicals_sign_split`: radicals sign-split workload (`LTBA-2`, n=8)
- `uc3_mixed_small_fastpath`: low-branch baseline (`LTBA-0`, n=8)

## Run

Quick smoke run:

```bash
python -m benchmarks.use_case_pack_v1 --smoke --repeats 2
```

Full results run:

```bash
python -m benchmarks.use_case_pack_v1 --reproduce-results --repeats 7
```

Target selected scenarios only:

```bash
python -m benchmarks.use_case_pack_v1 --reproduce-results --scenarios uc1_guarded_division_medium,uc2_radicals_sign_split --repeats 7
```

## Output Files

Written to `results/use_cases_v1/` when `--reproduce-results` is provided:

- `use_case_pack_v1_report.json`
- `use_case_pack_v1_summary.csv`
- `use_case_pack_v1_winners.csv`

`use_case_pack_v1_summary.csv` is row-oriented (scenario x backend).
`use_case_pack_v1_winners.csv` is scenario-oriented and helps quick comparison.
