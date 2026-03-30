import asyncio
import json
import shutil
import time
from typing import Optional, Dict

class LighthouseComparator:
    """
    NEW: improvement 2 — Lighthouse CI Comparison
    Provides ground truth validation by running the official Lighthouse CLI.
    """

    @staticmethod
    def is_available() -> bool:
        """Checks if the lighthouse CLI is installed in the current environment."""
        return shutil.which("lighthouse") is not None

    @staticmethod
    async def run_audit(url: str, timeout: int = 60) -> Dict:
        """
        Runs a Lighthouse audit via subprocess and returns extracted metrics.
        """
        if not LighthouseComparator.is_available():
            return {"available": False, "reason": "lighthouse CLI not found — run: npm install -g lighthouse"}

        print(f"  🔦 Lighthouse Audit starting for {url} …")
        
        cmd = [
            "lighthouse",
            url,
            "--output=json",
            "--output-path=stdout",
            "--chrome-flags=--headless --no-sandbox",
            "--only-categories=performance",
            "--quiet"
        ]

        try:
            # Improvement 2: timeout handling
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except:
                    pass
                return {"available": True, "error": "timeout"}

            if proc.returncode != 0:
                return {"available": True, "error": f"Lighthouse failed with code {proc.returncode}"}

            data = json.loads(stdout.decode('utf-8'))
            audits = data.get("audits", {})
            categories = data.get("categories", {})
            
            # Extraction logic per Improvement 2
            return {
                "available": True,
                "metrics": {
                    "fcp":   audits.get("first-contentful-paint", {}).get("numericValue", 0),
                    "lcp":   audits.get("largest-contentful-paint", {}).get("numericValue", 0),
                    "tbt":   audits.get("total-blocking-time", {}).get("numericValue", 0),
                    "cls":   audits.get("cumulative-layout-shift", {}).get("numericValue", 0),
                    "ttfb":  audits.get("server-response-time", {}).get("numericValue", 0),
                    "score": categories.get("performance", {}).get("score", 0) * 100,
                }
            }
        except Exception as e:
            return {"available": True, "error": str(e)}

    @staticmethod
    def compare(our_metrics: dict, lighthouse_metrics: dict) -> dict:
        """
        NEW: improvement 2 — Side-by-side comparison logic.
        """
        keys = {
            "fcp": "Initial Paint (FCP)",
            "lcp": "Main Content (LCP)",
            "tbt": "Total Blocking (TBT)",
            "cls": "Visual Stability (CLS)",
            "ttfb": "Server Response (TTFB)"
        }
        
        comparison = {}
        for key, label in keys.items():
            ours = float(our_metrics.get(key, 0))
            lh = float(lighthouse_metrics.get(key, 0))
            
            # Calculate % difference
            diff_pct = round(abs(ours - lh) / lh * 100, 1) if lh > 0 else None
            is_accurate = diff_pct is not None and diff_pct <= 20
            
            comparison[key] = {
                "label": label,
                "ours": ours,
                "lighthouse": lh,
                "diff_pct": diff_pct,
                "accurate": is_accurate
            }
        
        comparison["score"] = {
            "lighthouse_score": lighthouse_metrics.get("score", 0)
        }
        return comparison
