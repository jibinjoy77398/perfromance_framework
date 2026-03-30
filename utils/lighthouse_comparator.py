import asyncio
import json
import shutil
import time
from pathlib import Path
from typing import Optional, Dict

class LighthouseComparator:
    """
    NEW: improvement 2 — Lighthouse CI Comparison
    Provides ground truth validation by running the official Lighthouse CLI.
    """

    @staticmethod
    def is_available() -> bool:
        """Checks if the lighthouse CLI is installed in the current environment."""
        if shutil.which("lighthouse") is not None:
            return True
        # Fallback for common global install paths (Docker & Windows)
        user_home = Path.home()
        fallbacks = [
            "/usr/local/bin/lighthouse", 
            "/usr/bin/lighthouse", 
            "/app/node_modules/.bin/lighthouse",
            str(user_home / "AppData/Roaming/npm/lighthouse.cmd"),
            "lighthouse.cmd"
        ]
        for p in fallbacks:
            if shutil.which(p) or Path(p).exists():
                return True
        return False

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

        import os
        use_shell = os.name == 'nt' # Use shell for .cmd on Windows
        
        try:
            # Improvement 2: timeout handling
            if use_shell:
                # On Windows, we must use shell=True or call 'lighthouse.cmd'
                proc = await asyncio.create_subprocess_shell(
                    f'lighthouse "{url}" --output=json --output-path=stdout --chrome-flags="--headless --no-sandbox" --only-categories=performance --quiet',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL
                )
            
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                if stderr:
                    print(f"  [Lighthouse Stderr]: {stderr.decode('utf-8', errors='ignore')}")
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except:
                    pass
                return {"available": True, "error": f"Lighthouse audit timed out ({timeout}s limit)"}

            if proc.returncode != 0:
                # Capture possible error message from stdout/stderr
                err_msg = stderr.decode('utf-8', errors='ignore') if stderr else "Check container logs."
                return {"available": True, "error": f"Lighthouse failed (Code {proc.returncode}): {err_msg[:100]}..."}

            # Robustly find JSON in stdout
            raw_stdout = stdout.decode('utf-8', errors='ignore').strip()
            if not raw_stdout.startswith('{'):
                start = raw_stdout.find('{')
                if start != -1:
                    raw_stdout = raw_stdout[start:]
                else:
                    return {"available": True, "error": "Lighthouse did not return valid JSON results."}

            data = json.loads(raw_stdout)
            audits = data.get("audits", {})
            categories = data.get("categories", {})
            
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
            print(f"  ❌ Lighthouse Error: {str(e)}")
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
