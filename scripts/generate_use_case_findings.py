from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_CSV = ROOT / "results" / "use_cases_v1" / "use_case_pack_v1_summary.csv"
WINNERS_CSV = ROOT / "results" / "use_cases_v1" / "use_case_pack_v1_winners.csv"
REPORT_JSON = ROOT / "results" / "use_cases_v1" / "use_case_pack_v1_report.json"
OUT_MD = ROOT / "docs" / "USE_CASE_PACK_V1_FINDINGS.md"


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _fmt_ms(value: str) -> str:
    if not value:
        return "n/a"
    try:
        return f"{float(value):.4f}"
    except Exception:
        return "n/a"


def _fmt_count(value: str) -> str:
    if not value:
        return "n/a"
    try:
        n = float(value)
        if n.is_integer():
            return str(int(n))
        return f"{n:.2f}"
    except Exception:
        return "n/a"


def main() -> None:
    if not SUMMARY_CSV.exists() or not WINNERS_CSV.exists() or not REPORT_JSON.exists():
        raise SystemExit(
            "Missing use-case artifacts. Run: python -m benchmarks.use_case_pack_v1 --reproduce-results --repeats 7"
        )

    summary_rows = _read_csv(SUMMARY_CSV)
    winner_rows = _read_csv(WINNERS_CSV)

    by_scenario: Dict[str, List[Dict[str, str]]] = {}
    for row in summary_rows:
        by_scenario.setdefault(row.get("scenario_id", ""), []).append(row)

    lines: List[str] = []
    lines.append("# Use Case Pack v1 Findings")
    lines.append("")
    lines.append("This document is auto-generated from the latest Use Case Pack v1 result artifacts.")
    lines.append("")
    lines.append("Source artifacts:")
    lines.append("")
    lines.append("- `results/use_cases_v1/use_case_pack_v1_report.json`")
    lines.append("- `results/use_cases_v1/use_case_pack_v1_summary.csv`")
    lines.append("- `results/use_cases_v1/use_case_pack_v1_winners.csv`")
    lines.append("")
    lines.append("## Snapshot")
    lines.append("")
    lines.append(f"- Generated (UTC): {dt.datetime.now(dt.timezone.utc).isoformat()}")
    lines.append("")
    lines.append("## Scenario Winners")
    lines.append("")
    lines.append("| Scenario | Winner: Time To Execute | Winner: Rewrite-One Latency | Winner: Branch Count |")
    lines.append("|---|---|---|---|")
    for row in winner_rows:
        sid = row.get("scenario_id", "")
        w_exec = row.get("winner_time_to_execute", "")
        w_lat = row.get("winner_rewrite_one_latency", "")
        w_branch = row.get("winner_branch_count", "")
        lines.append(f"| {sid} | {w_exec} | {w_lat} | {w_branch} |")

    lines.append("")
    lines.append("## Metric Snapshot")
    lines.append("")

    backend_order = ["ltba", "explicit", "bdd"]
    for sid in [row.get("scenario_id", "") for row in winner_rows]:
        lines.append(f"- `{sid}`")
        rows = sorted(by_scenario.get(sid, []), key=lambda r: backend_order.index(r.get("backend", "zzz")) if r.get("backend", "") in backend_order else 999)
        for row in rows:
            backend = row.get("backend", "unknown")
            t_ms = _fmt_ms(row.get("time_to_execute_ms", ""))
            l_ms = _fmt_ms(row.get("rewrite_one_latency_ms", ""))
            b_count = _fmt_count(row.get("branch_count", ""))
            b_metric = row.get("branch_metric", "")
            lines.append(
                f"- {backend}: time_to_execute_ms = {t_ms}, rewrite_one_latency_ms = {l_ms}, branch_count = {b_count} ({b_metric})"
            )
        lines.append("")

    lines.append("## Interpretation")
    lines.append("")
    lines.append("- LTBA is expected to perform best as guarded branching complexity increases.")
    lines.append("- Explicit materialization may remain faster in near-trivial fast-path scenarios.")
    lines.append("- BDD rows can be partially empty when the optional `dd` package is unavailable.")
    lines.append("")
    lines.append("## Reproducibility")
    lines.append("")
    lines.append("```bash")
    lines.append("python -m benchmarks.use_case_pack_v1 --reproduce-results --repeats 7")
    lines.append("python scripts/generate_use_case_findings.py")
    lines.append("```")

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
