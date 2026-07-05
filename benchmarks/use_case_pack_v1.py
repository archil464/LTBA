"""Use Case Pack v1: scenario-based LTBA comparison against established approaches.

This runner focuses on practical usage scenarios and reports cross-backend metrics:
- time_to_execute: build + rewrite_all latency
- rewrite_one_latency: localized update latency
- branch_count: backend branch/path footprint proxy

Backends compared:
- ltba
- explicit (piecewise-style global materialization)
- bdd (optional, requires `dd`)
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import platform
import statistics
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from ltba import registry

from . import benchmark_v4


SCENARIOS = [
    {
        "id": "uc1_guarded_division_medium",
        "title": "Guarded Division Medium",
        "component": "LTBA-1",
        "n": 6,
        "description": "Guard-heavy division/cancellation simplification workload.",
    },
    {
        "id": "uc2_radicals_sign_split",
        "title": "Radicals Sign Split",
        "component": "LTBA-2",
        "n": 8,
        "description": "Sign-splitting radicals with many local alternatives.",
    },
    {
        "id": "uc3_mixed_small_fastpath",
        "title": "Mixed Small Fastpath",
        "component": "LTBA-0",
        "n": 8,
        "description": "Low-branch baseline to observe overhead in near-trivial cases.",
    },
]


def _is_num(v: object) -> bool:
    return isinstance(v, (int, float))


def _median(values: Iterable[object]) -> Optional[float]:
    nums = [float(v) for v in values if _is_num(v)]
    if not nums:
        return None
    return float(statistics.median(nums))


def _sum_maybe(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return float(a + b)


def _resolve_scenarios(raw: str, smoke: bool) -> List[Dict[str, object]]:
    if smoke:
        return SCENARIOS[:2]
    if raw == "all":
        return SCENARIOS
    wanted = {x.strip() for x in raw.split(",") if x.strip()}
    out = [s for s in SCENARIOS if s["id"] in wanted]
    if not out:
        raise ValueError(f"No scenarios matched --scenarios={raw!r}")
    return out


def _collect_backend_rows(scenario: Dict[str, object], trial_rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    comp = str(scenario["component"])
    n = int(scenario["n"])
    expr = registry.get(comp).make_family(n)

    ltba_build = _median(r.get("ltba_build_time") for r in trial_rows)
    ltba_rewrite_one = _median(r.get("ltba_rewrite_one_time") for r in trial_rows)
    ltba_rewrite_all = _median(r.get("ltba_rewrite_all_time") for r in trial_rows)

    explicit_build = _median(r.get("explicit_build_time") for r in trial_rows)
    explicit_rewrite_one = _median(r.get("explicit_rewrite_one_time") for r in trial_rows)
    explicit_rewrite_all = _median(r.get("explicit_rewrite_all_time") for r in trial_rows)

    bdd_build = _median(r.get("bdd_build_time") for r in trial_rows)
    bdd_rewrite_one = _median(r.get("bdd_rewrite_one_time") for r in trial_rows)
    bdd_rewrite_all = _median(r.get("bdd_rewrite_all_time") for r in trial_rows)

    ltba_row = {
        "scenario_id": scenario["id"],
        "scenario_title": scenario["title"],
        "backend": "ltba",
        "trials": len(trial_rows),
        "time_to_execute_s": _sum_maybe(ltba_build, ltba_rewrite_all),
        "rewrite_one_latency_s": ltba_rewrite_one,
        "branch_count": expr.local_branch_count,
        "branch_metric": "local_branch_count",
    }
    explicit_row = {
        "scenario_id": scenario["id"],
        "scenario_title": scenario["title"],
        "backend": "explicit",
        "trials": len(trial_rows),
        "time_to_execute_s": _sum_maybe(explicit_build, explicit_rewrite_all),
        "rewrite_one_latency_s": explicit_rewrite_one,
        "branch_count": int(expr.explicit_branch_upper_bound),
        "branch_metric": "explicit_case_count",
    }
    bdd_row = {
        "scenario_id": scenario["id"],
        "scenario_title": scenario["title"],
        "backend": "bdd",
        "trials": len(trial_rows),
        "time_to_execute_s": _sum_maybe(bdd_build, bdd_rewrite_all),
        "rewrite_one_latency_s": bdd_rewrite_one,
        "branch_count": _median(r.get("bdd_path_count") for r in trial_rows),
        "branch_metric": "bdd_path_count",
    }

    return [ltba_row, explicit_row, bdd_row]


def _winner_by_metric(rows: List[Dict[str, object]], metric: str) -> Optional[str]:
    available = [(str(r["backend"]), r.get(metric)) for r in rows if _is_num(r.get(metric))]
    if not available:
        return None
    available.sort(key=lambda kv: float(kv[1]))
    return available[0][0]


def run(args: argparse.Namespace) -> Dict[str, object]:
    repeats = max(1, int(getattr(args, "repeats", 5)))
    selected = _resolve_scenarios(raw=str(getattr(args, "scenarios", "all")), smoke=bool(getattr(args, "smoke", False)))

    rows: List[Dict[str, object]] = []
    trial_rows: List[Dict[str, object]] = []
    scenario_winners: List[Dict[str, object]] = []

    for scenario in selected:
        component = str(scenario["component"])
        n = int(scenario["n"])
        local_trials = [benchmark_v4.run_once(component, n) for _ in range(repeats)]

        backend_rows = _collect_backend_rows(scenario, local_trials)
        for br in backend_rows:
            t = br.get("time_to_execute_s")
            l = br.get("rewrite_one_latency_s")
            br["time_to_execute_ms"] = (float(t) * 1000.0) if _is_num(t) else None
            br["rewrite_one_latency_ms"] = (float(l) * 1000.0) if _is_num(l) else None
            rows.append(br)

        scenario_winners.append(
            {
                "scenario_id": scenario["id"],
                "winner_time_to_execute": _winner_by_metric(backend_rows, "time_to_execute_s"),
                "winner_rewrite_one_latency": _winner_by_metric(backend_rows, "rewrite_one_latency_s"),
                "winner_branch_count": _winner_by_metric(backend_rows, "branch_count"),
            }
        )

        for idx, tr in enumerate(local_trials):
            with_trial = dict(tr)
            with_trial["scenario_id"] = scenario["id"]
            with_trial["trial_index"] = idx
            trial_rows.append(with_trial)

    report = {
        "pack": "LTBA Use Case Pack v1",
        "generated_at_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "repeats": repeats,
        "scenarios": selected,
        "rows": rows,
        "scenario_winners": scenario_winners,
        "trial_rows": trial_rows,
        "notes": {
            "explicit": "Piecewise-style explicit materialization baseline.",
            "bdd": "BDD skeleton baseline; values may be null if `dd` is unavailable.",
        },
    }
    return report


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true", help="run a reduced scenario set")
    p.add_argument("--repeats", type=int, default=5, help="number of repeated trials per scenario")
    p.add_argument("--scenarios", default="all", help="comma-separated scenario ids or 'all'")
    p.add_argument("--reproduce-results", action="store_true", help="write results/use_cases_v1 outputs")
    args = p.parse_args()

    report = run(args)

    if args.reproduce_results:
        out_dir = Path("results/use_cases_v1")
        out_dir.mkdir(parents=True, exist_ok=True)

        json_path = out_dir / "use_case_pack_v1_report.json"
        csv_path = out_dir / "use_case_pack_v1_summary.csv"
        winners_path = out_dir / "use_case_pack_v1_winners.csv"

        json_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

        fieldnames = [
            "scenario_id",
            "scenario_title",
            "backend",
            "trials",
            "time_to_execute_s",
            "time_to_execute_ms",
            "rewrite_one_latency_s",
            "rewrite_one_latency_ms",
            "branch_count",
            "branch_metric",
        ]

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for row in report["rows"]:
                w.writerow({k: row.get(k) for k in fieldnames})

        winner_fields = [
            "scenario_id",
            "winner_time_to_execute",
            "winner_rewrite_one_latency",
            "winner_branch_count",
        ]
        with winners_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=winner_fields)
            w.writeheader()
            for row in report["scenario_winners"]:
                w.writerow({k: row.get(k) for k in winner_fields})

        print(f"wrote {json_path}")
        print(f"wrote {csv_path}")
        print(f"wrote {winners_path}")
    else:
        print(json.dumps({"rows": len(report["rows"]), "scenarios": len(report["scenarios"])}, indent=2))


if __name__ == "__main__":
    main()
