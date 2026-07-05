# How to Reproduce LTBA v4 Benchmarks

This repository preserves LTBA benchmark results and historical patch scripts.

The current frozen benchmark is **v4**, which measures fair amortized runtime:

```text
cold build + k equal-work local rewrites
```

This guide shows the shortest reproducible path for reviewers.

## 1) Environment

From the repository root:

```bash
python -m venv .venv
```

Activate the environment:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install package and optional tooling:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install -e .[dev]
python -m pip install -e .[benchmark]  # optional, enables BDD baseline via dd
```

## 2) Sanity Checks

Run tests:

```bash
python -m pytest
```

Run benchmark smoke mode:

```bash
python -m benchmarks.benchmark_v4 --smoke
```

Expected smoke output is a JSON object with the row count.

## 3) Regenerate v4 Results

Run the full reproducible benchmark pass:

```bash
python -m benchmarks.benchmark_v4 --reproduce-results
```

Generated files are written to `results/v4/`:

- `ltba_general_benchmark_v4_report.json`
- `ltba_general_benchmark_v4_summary.csv`

## 4) Notes for Reviewers

- The explicit materialization baseline is always available.
- The BDD-style columns are populated only when `dd` is installed.
- Large branch products are intentionally bounded by the benchmark runner.

## 5) Optional Packaging Check

Create a clean review archive from git:

```bash
git archive --format=zip --output=ltba-review.zip HEAD
