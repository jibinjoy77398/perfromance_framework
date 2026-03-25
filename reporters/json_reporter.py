"""
json_reporter.py — Outputs performance results as machine-readable JSON.
Demonstrates polymorphism: same BaseReporter interface, different output format.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

from reporters.html_reporter import BaseReporter


class JSONReporter(BaseReporter):
    """
    Generates a JSON performance report.

    Usage:
        reporter = JSONReporter(indent=2)
        reporter.generate(site_name=..., ..., output_path=Path("report.json"))
    """

    def __init__(self, indent: int = 2):
        self._indent = indent

    def generate(
        self,
        site_name: str,
        site_url: str,
        evaluation: dict,
        grade: str,
        baseline_stats: dict,
        network_stress: dict,
        ramp_results: list,
        resource_groups: dict,
        all_requests: list,
        output_path: Path,
        duration_seconds: float = 0,
    ) -> None:
        passes = sum(1 for v in evaluation.values() if v["verdict"] == "PASS")
        warns = sum(1 for v in evaluation.values() if v["verdict"] == "WARN")
        fails = sum(1 for v in evaluation.values() if v["verdict"] == "FAIL")

        report = {
            "meta": {
                "site_name": site_name,
                "site_url": site_url,
                "timestamp": datetime.now().isoformat(),
                "duration_seconds": round(duration_seconds, 2),
            },
            "summary": {
                "grade": grade,
                "passed": passes,
                "warned": warns,
                "failed": fails,
                "total_metrics": passes + warns + fails,
            },
            "evaluation": evaluation,
            "baseline": baseline_stats,
            "network_stress": network_stress,
            "breakpoint": ramp_results,
            "resources": {
                "by_type": resource_groups,
                "request_count": len(all_requests),
            },
        }

        # Change extension to .json
        json_path = output_path.with_suffix(".json")
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, indent=self._indent, default=str),
                             encoding="utf-8")
        print(f"\n  📄 JSON report saved → {json_path}")
