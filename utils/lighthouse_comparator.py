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
    async def run_audit(url: str, timeout: int = 90) -> Dict:
        """
        Runs a Lighthouse audit via a thread-pool executor (subprocess.run).

        WHY NOT asyncio.create_subprocess_shell?
        On Windows, asyncio subprocesses inherit the Python process's file handle
        table and security context. Node.js's fs.mkdtemp() uses the WINAPI
        CreateFile with exclusive access flags — when the parent Python process
        already has open handles on temp dirs (from HAR recording, etc.), the
        exclusive lock request triggers EPERM regardless of which directory we
        point TEMP/TMP to.

        subprocess.run() in a thread creates a fully detached process tree with
        its own handle table, resolving the conflict entirely.
        """
        if not LighthouseComparator.is_available():
            return {"available": False, "reason": "lighthouse CLI not found — run: npm install -g lighthouse"}

        print(f"  🔦 Lighthouse Audit starting for {url} …")

        import os
        import subprocess
        import concurrent.futures

        # Write LH output to a file we own (avoids any stdout pipe issues on Windows)
        lh_out_file = Path("reports") / f"_lh_{int(time.time())}.json"
        lh_out_file.parent.mkdir(parents=True, exist_ok=True)
        lh_out_path = str(lh_out_file.resolve())

        def _run_lighthouse() -> subprocess.CompletedProcess:
            """Blocking call — runs in a thread so it doesn't block the event loop."""
            if os.name == 'nt':
                cmd = (
                    f'lighthouse "{url}" '
                    f'--output=json --output-path="{lh_out_path}" '
                    f'--chrome-flags="--headless --disable-gpu" '
                    f'--only-categories=performance '
                    f'--disable-full-page-screenshot '
                    f'--screenEmulation.disabled '
                    f'--quiet'
                )
                return subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    timeout=timeout,
                )
            else:
                return subprocess.run(
                    [
                        "lighthouse", url,
                        "--output=json", f"--output-path={lh_out_path}",
                        "--chrome-flags=--headless --no-sandbox",
                        "--only-categories=performance",
                        "--disable-full-page-screenshot",
                        "--quiet",
                    ],
                    capture_output=True,
                    timeout=timeout,
                )

        try:
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                try:
                    result = await asyncio.wait_for(
                        loop.run_in_executor(pool, _run_lighthouse),
                        timeout=timeout + 5,
                    )
                except asyncio.TimeoutError:
                    lh_out_file.unlink(missing_ok=True)
                    print(f"  ⚠️ Lighthouse audit timed out after {timeout}s")
                    return {"available": True, "error": f"Lighthouse audit timed out ({timeout}s limit)"}

            if result.returncode != 0:
                err = result.stderr.decode('utf-8', errors='ignore').strip()[:300]
                lh_out_file.unlink(missing_ok=True)
                print(f"  ⚠️ Lighthouse failed (exit {result.returncode}): {err}")
                return {"available": True, "error": f"Lighthouse failed: {err}"}

            if not lh_out_file.exists():
                return {"available": True, "error": "Lighthouse did not write output file."}

            try:
                raw = lh_out_file.read_text(encoding='utf-8')
            finally:
                lh_out_file.unlink(missing_ok=True)

            data     = json.loads(raw)
            audits   = data.get("audits", {})
            cats     = data.get("categories", {})

            lh_score = (cats.get("performance", {}).get("score") or 0) * 100
            print(f"  ✅ Lighthouse complete — Score: {lh_score:.0f}/100")

            return {
                "available": True,
                "metrics": {
                    "fcp":   audits.get("first-contentful-paint",  {}).get("numericValue", 0),
                    "lcp":   audits.get("largest-contentful-paint", {}).get("numericValue", 0),
                    "tbt":   audits.get("total-blocking-time",       {}).get("numericValue", 0),
                    "cls":   audits.get("cumulative-layout-shift",   {}).get("numericValue", 0),
                    "ttfb":  audits.get("server-response-time",      {}).get("numericValue", 0),
                    "score": lh_score,
                }
            }

        except subprocess.TimeoutExpired:
            lh_out_file.unlink(missing_ok=True)
            print(f"  ⚠️ Lighthouse subprocess timed out after {timeout}s")
            return {"available": True, "error": f"Lighthouse audit timed out ({timeout}s limit)"}
        except Exception as e:
            lh_out_file.unlink(missing_ok=True)
            print(f"  ❌ Lighthouse Error: {e}")
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
