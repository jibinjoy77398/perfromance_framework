"""
Threshold Evaluator — compares collected metrics against thresholds.json.
Returns a verdict: PASS / WARN / FAIL for each metric.
"""
from __future__ import annotations
import json
from pathlib import Path

THRESHOLD_FILE = Path(__file__).parent.parent / "config" / "thresholds.json"

# Metrics where LOWER is better (value > threshold → FAIL)
LOWER_IS_BETTER = {
    "lcp", "fcp", "ttfb", "tti", "tbt", "inp",
    "load_time", "dom_content_loaded",
    "resource_count", "total_resource_size_kb",
    "js_heap_used_mb", "failed_requests", "slow_requests",
    "p95_load_time", "stddev_load_time", "error_rate_pct",
}


class ThresholdEvaluator:
    """
    Encapsulates threshold loading, metric evaluation, and grading.

    Usage:
        evaluator = ThresholdEvaluator()            # loads default thresholds
        evaluator = ThresholdEvaluator(custom_path)  # loads from custom file
        results = evaluator.evaluate(metrics)
        letter  = evaluator.grade(results)
    """

    # At 80% of threshold → WARN, at 100% → FAIL
    WARN_RATIO = 0.80

    def __init__(self, threshold_path: Path | None = None):
        self._path = threshold_path or THRESHOLD_FILE
        self._thresholds = self._load()

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def thresholds(self) -> dict:
        """Return the current thresholds (read-only copy)."""
        return dict(self._thresholds)

    # ── Core methods ─────────────────────────────────────────────────────

    def evaluate(self, metrics: dict) -> dict[str, dict]:
        """
        Compare each metric against its threshold.

        Returns:
            { metric_name: { "value": ..., "threshold": ..., "verdict": "PASS|WARN|FAIL" } }
        """
        results = {}
        for key, threshold in self._thresholds.items():
            value = metrics.get(key)
            if value is None:
                continue
            if key in LOWER_IS_BETTER:
                if value > threshold:
                    verdict = "FAIL"
                elif value > threshold * self.WARN_RATIO:
                    verdict = "WARN"
                else:
                    verdict = "PASS"
            else:
                if value < threshold:
                    verdict = "FAIL"
                elif value < threshold * (1 + (1 - self.WARN_RATIO)):
                    verdict = "WARN"
                else:
                    verdict = "PASS"
            results[key] = {"value": value, "threshold": threshold, "verdict": verdict}
        return results

    @staticmethod
    def grade(results: dict[str, dict]) -> str:
        """Return an A–F letter grade based on pass rate."""
        if not results:
            return "N/A"
        total = len(results)
        failures = sum(1 for r in results.values() if r["verdict"] == "FAIL")
        warns = sum(1 for r in results.values() if r["verdict"] == "WARN")
        score = (total - failures - 0.5 * warns) / total
        if score >= 0.95:
            return "A"
        elif score >= 0.85:
            return "B"
        elif score >= 0.70:
            return "C"
        elif score >= 0.50:
            return "D"
        return "F"

    def reload(self) -> None:
        """Re-read thresholds from disk (useful after editing thresholds.json)."""
        self._thresholds = self._load()

    # ── Private ──────────────────────────────────────────────────────────

    def _load(self) -> dict:
        with open(self._path, "r") as f:
            raw = json.load(f)
        return {k: v for k, v in raw.items() if not k.startswith("_")}


# ── Backward-compatible free functions ───────────────────────────────────
# Keep these so existing test files don't break immediately.

_default_evaluator: ThresholdEvaluator | None = None


def _get_default() -> ThresholdEvaluator:
    global _default_evaluator
    if _default_evaluator is None:
        _default_evaluator = ThresholdEvaluator()
    return _default_evaluator


def load_thresholds() -> dict:
    """Backward-compatible: returns thresholds dict."""
    return _get_default().thresholds


def evaluate(metrics: dict, thresholds: dict | None = None) -> dict[str, dict]:
    """Backward-compatible: evaluate metrics."""
    if thresholds is not None:
        # Caller passed custom thresholds — use old-style logic
        ev = ThresholdEvaluator()
        ev._thresholds = thresholds
        return ev.evaluate(metrics)
    return _get_default().evaluate(metrics)


def grade(results: dict[str, dict]) -> str:
    """Backward-compatible: compute letter grade."""
    return ThresholdEvaluator.grade(results)
