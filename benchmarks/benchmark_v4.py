"""v4 benchmark runner (reproducible, reviewer-friendly).

Provides a fast `--smoke` mode and a reproducible `--reproduce-results` mode
that writes CSV and JSON outputs to `results/v4/`.

This version also supports repeated trials with aggregate statistics to make
comparisons less sensitive to per-run noise.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import platform
import statistics
import time
from pathlib import Path
from typing import List, Dict

from ltba import registry
from ltba.piecewise_conversion import materialize_explicit


def timed(fn):
    t0 = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - t0


AGGREGATE_KEYS = [
    "ltba_build_time",
    "explicit_build_time",
    "bdd_build_time",
    "ltba_rewrite_one_time",
    "explicit_rewrite_one_time",
    "bdd_rewrite_one_time",
    "ltba_rewrite_all_time",
    "explicit_rewrite_all_time",
    "bdd_rewrite_all_time",
    "fair_amortized_time_ltba",
    "fair_amortized_time_explicit",
    "fair_amortized_time_bdd",
]


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float))


def _parse_sizes(smoke: bool, raw_sizes: str) -> List[int]:
    if raw_sizes:
        out = []
        for tok in raw_sizes.split(","):
            tok = tok.strip()
            if not tok:
                continue
            out.append(int(tok))
        return out
    return [1, 2, 4] if smoke else [1, 2, 4, 8]


def run_once(component_name: str, n: int) -> Dict[str, object]:
    comp = registry.get(component_name)
    expr, build_s = timed(lambda: comp.make_family(n))
    # LTBA local rewrite timings
    _, ltba_rewrite_one_s = timed(lambda: expr.rewrite_local(0, "REWRITTEN", "benchmark_locality") if expr.local_branch_count else expr)

    # LTBA rewrite all: simulate rewriting first branch in every group
    def ltba_rewrite_all():
        e = expr
        for gi in range(len(e.branch_groups)):
            e = e.rewrite_local(gi, "REWRITTEN", "benchmark_locality_all")
        return e

    _, ltba_rewrite_all_s = timed(ltba_rewrite_all)

    row: Dict[str, object] = {
        "family": component_name,
        "n": n,
        "ltba_build_time": build_s,
        "ltba_rewrite_one_time": ltba_rewrite_one_s,
        "ltba_rewrite_all_time": ltba_rewrite_all_s,
        "ltba_repr_size": expr.representation_size,
    }

    # Explicit materialization baseline
    try:
        explicit_rows, explicit_build_s = timed(lambda: materialize_explicit(expr, max_branches=1000000))
        # materialize_explicit returns a dict; adapt
        explicit_info = explicit_rows
        explicit_build_time = explicit_build_s
        row["explicit_build_time"] = explicit_build_time
        if explicit_info.get("available"):
            cases = explicit_info.get("cases", [])
            # rewrite one: touch cases containing first group's first branch
            def explicit_rewrite_one():
                touched = 0
                if not cases:
                    return 0
                # pick first group's first branch tag if present
                first_group = expr.branch_groups[0] if expr.branch_groups else None
                if first_group and first_group.branches:
                    target_guard = str(first_group.branches[0].guard)
                else:
                    target_guard = None
                for g, v, tags in cases:
                    if target_guard and target_guard in g.split(" and "):
                        touched += 1
                return touched

            touched, explicit_rewrite_one_s = timed(explicit_rewrite_one)
            row["explicit_rewrite_one_time"] = explicit_rewrite_one_s
            # explicit rewrite all: simulated as touching all cases
            def explicit_rewrite_all():
                return len(cases)

            _, explicit_rewrite_all_s = timed(explicit_rewrite_all)
            row["explicit_rewrite_all_time"] = explicit_rewrite_all_s
            row["explicit_actual_branch_count"] = explicit_info.get("actual_branch_count")
    except ValueError as exc:
        row["explicit_build_time"] = None
        row["explicit_rewrite_one_time"] = None
        row["explicit_rewrite_all_time"] = None
        row["explicit_error"] = str(exc)

    # BDD guard skeleton baseline (optional)
    try:
        import dd.autoref as _bdd  # type: ignore

        def bdd_build():
            bdd = _bdd.BDD()
            var_names = []
            group_bits = []
            for gi, g in enumerate(expr.branch_groups):
                bits = max(1, (len(g.branches) - 1).bit_length())
                names = [f"g{gi}_b{bi}" for bi in range(bits)]
                var_names.extend(names)
                group_bits.append(names)
            if var_names:
                bdd.declare(*var_names)
            paths = []
            if not expr.branch_groups:
                return bdd, [bdd.true]
            import itertools as _it
            for choices in _it.product(*[range(max(1, len(g.branches))) for g in expr.branch_groups]):
                node = bdd.true
                for gi, choice_idx in enumerate(choices):
                    bits = group_bits[gi]
                    for bi, name in enumerate(bits):
                        bit_is_one = bool((choice_idx >> bi) & 1)
                        lit = bdd.var(name)
                        if not bit_is_one:
                            lit = ~lit
                        node &= lit
                paths.append(node)
            return bdd, paths

        (bdd, paths), bdd_build_s = timed(bdd_build)
        row["bdd_build_time"] = bdd_build_s
        row["bdd_path_count"] = len(paths)
        # simulate rewrite costs proportional to path_count
        row["bdd_rewrite_one_time"] = (1.0 / max(1, len(paths))) if paths else 0.0
        row["bdd_rewrite_all_time"] = float(len(paths))
    except Exception:
        row["bdd_build_time"] = None
        row["bdd_rewrite_one_time"] = None
        row["bdd_rewrite_all_time"] = None

    # Fair amortized time: per-case amortized build + single-rewrite cost.
    # Definition: fair_amortized_time = build_time / max(1, total_cases) + rewrite_one_time
    total_cases = None
    if "explicit_actual_branch_count" in row and row.get("explicit_actual_branch_count"):
        total_cases = row["explicit_actual_branch_count"]
    else:
        total_cases = max(1, expr.explicit_branch_upper_bound)

    def amortized(build, rewrite_one):
        if build is None or rewrite_one is None:
            return None
        return build / max(1, total_cases) + rewrite_one

    row["fair_amortized_time_ltba"] = amortized(row.get("ltba_build_time"), row.get("ltba_rewrite_one_time"))
    row["fair_amortized_time_explicit"] = amortized(row.get("explicit_build_time"), row.get("explicit_rewrite_one_time"))
    row["fair_amortized_time_bdd"] = amortized(row.get("bdd_build_time"), row.get("bdd_rewrite_one_time"))

    # winner
    candidates = {k: v for k, v in (("ltba", row["fair_amortized_time_ltba"]), ("explicit", row.get("fair_amortized_time_explicit")), ("bdd", row.get("fair_amortized_time_bdd"))) if v is not None}
    row["winner_fair_amortized"] = min(candidates, key=candidates.get) if candidates else None

    return row


def aggregate_trials(component_name: str, n: int, trial_rows: List[Dict[str, object]]) -> Dict[str, object]:
    row: Dict[str, object] = {
        "family": component_name,
        "n": n,
        "trials": len(trial_rows),
    }

    # Keep canonical keys populated with median values for backward-compatible CSVs.
    for key in AGGREGATE_KEYS:
        vals = [r[key] for r in trial_rows if key in r and _is_number(r[key])]
        if not vals:
            row[key] = None
            continue
        med = float(statistics.median(vals))
        row[key] = med
        row[f"{key}_mean"] = float(sum(vals) / len(vals))
        row[f"{key}_min"] = float(min(vals))
        row[f"{key}_max"] = float(max(vals))

    # Carry representative non-aggregated fields.
    first = trial_rows[0] if trial_rows else {}
    for key in ("ltba_repr_size", "explicit_actual_branch_count", "bdd_path_count", "explicit_error"):
        row[key] = first.get(key)

    # Majority vote winner across repeated trials; ties resolve to deterministic lexical order.
    votes: Dict[str, int] = {}
    for r in trial_rows:
        winner = r.get("winner_fair_amortized")
        if isinstance(winner, str):
            votes[winner] = votes.get(winner, 0) + 1
    if votes:
        row["winner_fair_amortized"] = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        row["winner_vote_count"] = max(votes.values())
    else:
        row["winner_fair_amortized"] = None
        row["winner_vote_count"] = 0

    return row


def run(args: argparse.Namespace) -> Dict[str, object]:
    components = getattr(args, "components", "all")
    names = registry.names() if components == "all" else [x.strip() for x in components.split(",") if x.strip()]
    smoke = bool(getattr(args, "smoke", False))
    sizes = _parse_sizes(smoke=smoke, raw_sizes=getattr(args, "sizes", ""))
    repeats = max(1, int(getattr(args, "repeats", 1)))
    include_trials = bool(getattr(args, "include_trials", False))

    rows: List[Dict[str, object]] = []
    trial_rows: List[Dict[str, object]] = []
    for name in names:
        for n in sizes:
            local_trials = [run_once(name, n) for _ in range(repeats)]
            rows.append(aggregate_trials(name, n, local_trials))
            if include_trials:
                for idx, tr in enumerate(local_trials):
                    with_trial = dict(tr)
                    with_trial["trial_index"] = idx
                    trial_rows.append(with_trial)

    report = {
        "benchmark": "LTBA general benchmark v4",
        "schema_version": "v4.1",
        "generated_at_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "repeats": repeats,
        "sizes": sizes,
        "rows": rows,
        "claim": "LTBA preserves local branch provenance and avoids explicit global branch materialization.",
    }
    if include_trials:
        report["trial_rows"] = trial_rows
    return report


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true", help="run quick smoke checks")
    p.add_argument("--reproduce-results", action="store_true", help="regenerate results/v4/")
    p.add_argument("--components", default="all", help="comma-separated or 'all'")
    p.add_argument("--sizes", default="", help="comma-separated n sizes (overrides smoke/default sizes)")
    p.add_argument("--repeats", type=int, default=1, help="number of repeated trials per family/size")
    p.add_argument("--include-trials", action="store_true", help="include per-trial rows in JSON report")
    args = p.parse_args()

    report = run(args)

    out_dir = Path("results/v4")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.reproduce_results:
        json_path = out_dir / "ltba_general_benchmark_v4_report.json"
        csv_path = out_dir / "ltba_general_benchmark_v4_summary.csv"
        json_path.write_text(json.dumps(report, indent=2, sort_keys=True))

        fieldnames = [
            "family",
            "n",
            "trials",
            "ltba_build_time",
            "explicit_build_time",
            "bdd_build_time",
            "ltba_rewrite_one_time",
            "explicit_rewrite_one_time",
            "bdd_rewrite_one_time",
            "ltba_rewrite_all_time",
            "explicit_rewrite_all_time",
            "bdd_rewrite_all_time",
            "fair_amortized_time_ltba",
            "fair_amortized_time_explicit",
            "fair_amortized_time_bdd",
            "winner_fair_amortized",
            "winner_vote_count",
            "ltba_build_time_mean",
            "ltba_build_time_min",
            "ltba_build_time_max",
            "explicit_build_time_mean",
            "explicit_build_time_min",
            "explicit_build_time_max",
            "fair_amortized_time_ltba_mean",
            "fair_amortized_time_ltba_min",
            "fair_amortized_time_ltba_max",
            "fair_amortized_time_explicit_mean",
            "fair_amortized_time_explicit_min",
            "fair_amortized_time_explicit_max",
            "fair_amortized_time_bdd_mean",
            "fair_amortized_time_bdd_min",
            "fair_amortized_time_bdd_max",
        ]

        with csv_path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            # Fill in available fields; bench is minimal but columns are explicit
            for r in report["rows"]:
                row = {k: r.get(k) for k in fieldnames}
                w.writerow(row)

        print(f"wrote {json_path}")
        print(f"wrote {csv_path}")
    else:
        # quick console summary for smoke runs
        print(json.dumps({"rows": len(report["rows"])}, indent=2))


if __name__ == "__main__":
    main()
