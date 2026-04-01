"""
html_reporter.py — Generates a fully self-contained HTML performance report.
Uses a premium, modern glassmorphic UI design suitable for browser viewing.
"""
from __future__ import annotations
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from utils.lighthouse_comparator import LighthouseComparator


class BaseReporter(ABC):
    """Abstract base class for all report generators."""
    @abstractmethod
    def generate(
        self,
        site_name: str,
        site_url: str,
        results: dict,
        output_path: Path,
        duration_seconds: float = 0,
    ) -> None:
        ...


class HTMLReporter(BaseReporter):
    """Generates a premium, visually stunning HTML performance report with consultation-style logic."""

    # Consultation mapping based on failing metrics
    FIX_LOGIC = {
        "ttfb": {
            "category": "Server / Hosting",
            "fixes": [
                {"do": "Add Cloudflare CDN (free tier) in front of origin", "why": "Caches static content closer to users, reducing network travel time.", "impact": "60-80%", "effort": "5 min"},
                {"do": "Enable FastCGI/Nginx fast-paging", "why": "Reduces the time the web server spends talking to the process manager.", "impact": "20-30%", "effort": "1 hour"},
                {"do": "Optimize SQL queries and add indexes", "why": "Reduces DB execution time which is often the primary TTFB bottleneck.", "impact": "40-50%", "effort": "1 day"}
            ]
        },
        "fcp": {
            "category": "Frontend / Network",
            "fixes": [
                {"do": "Inline critical CSS and defer non-critical scripts", "why": "First paint is blocked by external CSS; inlining gets pixels on screen faster.", "impact": "30-50%", "effort": "1 hour"},
                {"do": "Pre-connect to critical third-party origins", "why": "Establishes early connections to font/analytic servers before they are called.", "impact": "10-20%", "effort": "5 min"},
                {"do": "Minimize DOM depth and complexity", "why": "A deep DOM tree slows down initial layout and browser rendering.", "impact": "15-25%", "effort": "1 day"}
            ]
        },
        "lcp": {
            "category": "Images / Server",
            "fixes": [
                {"do": 'Add loading="lazy" + compress hero images to WebP', "why": "LCP is usually a large image; smaller files in modern formats load faster.", "impact": "50-70%", "effort": "1 hour"},
                {"do": "Use <link rel='preload'> for the LCP image", "why": "Forces the browser to start downloading the hero asset before parsing HTML.", "impact": "20-40%", "effort": "5 min"},
                {"do": "Set explicit Width/Height on hero elements", "why": "Prevents layout re-calculation when the large asset finally arrives.", "impact": "10-15%", "effort": "10 min"}
            ]
        },
        "cls": {
            "category": "Frontend",
            "fixes": [
                {"do": "Set explicit width and height on all images and embeds", "why": "Reserves layout space before the asset loads, preventing jumps.", "impact": "80-90%", "effort": "30 min"},
                {"do": "Avoid inserting content above existing content", "why": "Injecting dynamic ads/banners late causes entire layout shifts.", "impact": "50-70%", "effort": "1 hour"},
                {"do": "Use transform: translate() for animations", "why": "CSSTransform property doesn't trigger layout recalculations.", "impact": "10-20%", "effort": "1 hour"}
            ]
        },
        "tbt": {
            "category": "JavaScript",
            "fixes": [
                {"do": "Split large JS bundles and move analytics to web workers", "why": "Offloads heavy work from the main thread, allowing user input response.", "impact": "40-60%", "effort": "1 day"},
                {"do": "Remove unused JS code using Tree Shaking", "why": "Less code to parse and execute means shorter blocking periods.", "impact": "20-30%", "effort": "1 day"},
                {"do": "Break up long tasks (yield to main thread)", "why": "Using requestIdleCallback allows browser to handle user input mid-task.", "impact": "30-50%", "effort": "2 hours"}
            ]
        },
        "inp": {
            "category": "JavaScript",
            "fixes": [
                {"do": "Defer third-party scripts and reduce event listener count", "why": "Reduces the number of handlers triggered on every user interaction.", "impact": "30-50%", "effort": "1 hour"},
                {"do": "Optimize event handler execution speed", "why": "Calculations triggered by clicks must finish under 100ms for responsiveness.", "impact": "40-60%", "effort": "1 day"},
                {"do": "Use CSS for interactions where possible (hover, focus)", "why": "CSS animations are smoother and don't block on the JS thread.", "impact": "10-20%", "effort": "1 hour"}
            ]
        },
        "load_time": {
            "category": "Network / Assets",
            "fixes": [
                {"do": "Enable Brotli compression and leverage browser caching", "why": "Significantly reduces transfer size and prevents redundant downloads.", "impact": "50-70%", "effort": "1 hour"},
                {"do": "Audit and remove redundant third-party libraries", "why": "Every external script adds connection, download, and execution overhead.", "impact": "20-40%", "effort": "1 day"},
                {"do": "Implement a Service Worker for asset caching", "why": "Provides near-instant loads for return visitors using local storage.", "impact": "60-80%", "effort": "1 week"}
            ]
        },
        "dom_content_loaded": {
            "category": "Server / Scripts",
            "fixes": [
                {"do": "Remove render-blocking scripts; use 'defer' and 'async'", "why": "Allows HTML parsing to continue while scripts download in background.", "impact": "40-60%", "effort": "10 min"},
                {"do": "Minimize CSS imports and use flat files", "why": "@import statements force serial downloads rather than parallel.", "impact": "10-20%", "effort": "1 hour"},
                {"do": "Optimize HTML tag count and nesting", "why": "A smaller DOM tree is faster to parse and construct (DOM Tree).", "impact": "10-15%", "effort": "1 day"}
            ]
        },
        "resource_count": {
            "category": "Assets",
            "fixes": [
                {"do": "Combine CSS/JS files and use HTTP/2 multiplexing", "why": "Reduces HTTP request overhead and metadata transmission.", "impact": "20-40%", "effort": "1 day"},
                {"do": "Use Image Sprites for small icons", "why": "One request for multiple icons is more efficient than dozens of small ones.", "impact": "10-20%", "effort": "2 hours"},
                {"do": "Eliminate 404s and redundant redirects", "why": "Wasted requests slow down the total resource discovery and load.", "impact": "5-10%", "effort": "1 hour"}
            ]
        },
        "total_resource_size_kb": {
            "category": "Assets",
            "fixes": [
                {"do": "Enable Gzip/Brotli; audit and remove unused dependencies", "why": "Smaller binaries transfer faster over mobile and slow connections.", "impact": "40-60%", "effort": "1 hour"},
                {"do": "Lazy-load non-essential imagery and scripts", "why": "Downloading only what the user sees reduces initial payload dramatically.", "impact": "30-50%", "effort": "1 day"},
                {"do": "Compress SVG files using SVGO", "why": "SVGs can often be reduced by 50-80% without losing quality.", "impact": "5-10%", "effort": "1 hour"}
            ]
        },
        "js_heap_used_mb": {
            "category": "JavaScript",
            "fixes": [
                {"do": "Audit memory leaks and lazy-load heavy components", "why": "Prevents the browser from slowing down or crashing during usage.", "impact": "40-60%", "effort": "2 days"},
                {"do": "Unsubscribe from global event listeners on unmount", "why": "Common source of memory growth in Client-Side Apps.", "impact": "20-30%", "effort": "2 hours"},
                {"do": "Use Virtual Lists for long data tables", "why": "Only rendering visible rows keeps memory usage flat regardless of data size.", "impact": "50-70%", "effort": "1 week"}
            ]
        }
    }

    CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;600;700&display=swap');
  
  :root {
    --bg-color: #0d1117;
    --card-bg: rgba(22, 27, 34, 0.8);
    --card-border: rgba(48, 54, 61, 1);
    --text-main: #c9d1d9;
    --text-bright: #f0f6fc;
    --text-muted: #8b949e;
    --teal: #00d9a6;
    --red: #ff4466;
    --amber: #ffaa00;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Barlow', sans-serif;
    background: var(--bg-color);
    color: var(--text-main);
    line-height: 1.6;
    padding: 2rem 1rem;
    min-height: 100vh;
  }

  .container { max-width: 1100px; margin: 0 auto; }
  
  header { margin-bottom: 3rem; }
  h1 { font-size: 2.5rem; font-weight: 800; color: var(--text-bright); margin-bottom: 0.5rem; }
  .subtitle { color: var(--text-muted); font-size: 1.1rem; }
  
  .card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    animation: fadeIn 0.5s ease-out forwards;
    opacity: 0;
  }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  .card:nth-child(1) { animation-delay: 0.1s; }
  .card:nth-child(2) { animation-delay: 0.2s; }
  .card:nth-child(3) { animation-delay: 0.3s; }
  
  h2 { font-size: 1.25rem; font-weight: 700; color: var(--text-bright); margin: 2rem 0 1rem; text-transform: uppercase; letter-spacing: 0.05em; display: flex; align-items: center; gap: 0.75rem; }
  h2::after { content: ""; flex: 1; height: 1px; background: var(--card-border); }

  .status-pill { padding: 0.25rem 0.75rem; border-radius: 999px; font-size: 0.75rem; font-weight: 800; text-transform: uppercase; }
  .status-PASS { background: rgba(0, 217, 166, 0.15); color: var(--teal); border: 1px solid var(--teal); }
  .status-FAIL { background: rgba(255, 68, 102, 0.15); color: var(--red); border: 1px solid var(--red); }
  .status-WARN { background: rgba(255, 170, 0, 0.15); color: var(--amber); border: 1px solid var(--amber); }

  .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; }
  .metric-card { border-left: 4px solid var(--card-border); }
  .metric-label { font-size: 0.85rem; color: var(--text-muted); font-weight: 500; margin-bottom: 0.5rem; display: block; }
  .metric-value { font-family: 'IBM Plex Mono', monospace; font-size: 1.75rem; font-weight: 700; color: var(--text-bright); }
  .metric-target { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem; }

  .table-wrapper { width: 100%; overflow-x: auto; margin-top: 1rem; }
  table { width: 100%; border-collapse: collapse; text-align: left; }
  th { padding: 0.75rem 1rem; color: var(--text-muted); border-bottom: 1px solid var(--card-border); font-size: 0.8rem; text-transform: uppercase; }
  td { padding: 0.75rem 1rem; border-bottom: 1px solid rgba(48, 54, 61, 0.5); font-size: 0.95rem; }
  
  .fix-section { background: rgba(255, 68, 102, 0.05); border: 1px solid rgba(255, 68, 102, 0.2); }
  .fix-row { margin-bottom: 1.5rem; padding-bottom: 1.5rem; border-bottom: 1px dashed var(--card-border); }
  .fix-row:last-child { margin-bottom: 0; padding-bottom: 0; border-bottom: none; }
  .fix-gap { font-weight: 700; color: var(--red); margin-bottom: 0.5rem; }
  .suggestion-pill { font-size: 0.7rem; font-weight: 700; background: #30363d; color: var(--text-main); padding: 2px 6px; border-radius: 4px; margin-right: 5px; }

  @media print {
    body { background: white; color: black; padding: 0; }
    .card { border: 1px solid #ddd; box-shadow: none; animation: none; opacity: 1; }
    .metric-value { color: black; }
  }

  /* ── Lighthouse Comparator ──────────────────────────────── */
  .lh-section { border: 1px solid rgba(99, 179, 237, 0.3); background: rgba(99, 179, 237, 0.04); }
  .lh-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem; margin-bottom: 1.5rem; }
  .lh-score-ring {
    position: relative; width: 90px; height: 90px;
    border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: conic-gradient(var(--ring-color, #00d9a6) var(--ring-pct, 0%), rgba(48,54,61,0.6) 0%);
  }
  .lh-score-ring-inner {
    position: absolute; width: 70px; height: 70px; border-radius: 50%;
    background: var(--card-bg); display: flex; flex-direction: column;
    align-items: center; justify-content: center;
  }
  .lh-score-pct { font-family: 'IBM Plex Mono', monospace; font-size: 1.15rem; font-weight: 700; color: var(--text-bright); }
  .lh-score-label { font-size: 0.6rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
  .lh-badge-na { background: rgba(139,148,158,0.15); color: #8b949e; border: 1px solid #30363d;
    border-radius: 8px; padding: 0.5rem 1rem; font-size: 0.85rem; display: inline-flex; align-items: center; gap: 0.5rem; }
  .lh-row-accurate td { background: rgba(0, 217, 166, 0.04); }
  .lh-row-drift   td { background: rgba(255, 170, 0, 0.04); }
  .lh-row-na      td { background: transparent; }
  .lh-diff-badge {
    display: inline-block; padding: 2px 8px; border-radius: 999px;
    font-size: 0.72rem; font-weight: 700; font-family: 'IBM Plex Mono', monospace;
  }
  .lh-score-lh { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem; }
</style>
<script>
    let currentHash = null;
    async function checkUpdate() {
        try {
            const resp = await fetch('/api/report-ready');
            const data = await resp.json();
            if (currentHash && data.hash !== currentHash) { window.location.reload(); }
            currentHash = data.hash;
        } catch (e) {}
    }
    setInterval(checkUpdate, 5000);
</script>
"""

    def _get_fix_suggestions_html(self, evaluation: dict) -> str:
        failures = [k for k, v in evaluation.items() if v["verdict"] == "FAIL"]
        if not failures: return ""
        html = '<h2>🚀 Performance Gap Analysis & Fixes</h2><section class="card fix-section">'
        for key in failures:
            ev = evaluation[key]
            logic = self.FIX_LOGIC.get(key)
            if not logic: continue
            val = float(ev["value"])
            tgt = float(ev["threshold"])
            gap = val / tgt if tgt > 0 else 0
            html += f'<div class="fix-row"><div class="fix-gap">❌ {key.replace("_", " ").upper()} is {gap:.1f}x over target ({val:.0f} vs {tgt:.0f})</div>'
            html += f'<div style="font-size:0.85rem; color:var(--text-muted); margin-bottom:1rem;">Category: <b style="color:var(--text-bright)">{logic["category"]}</b></div>'
            for i, fix in enumerate(logic["fixes"]):
                lbl = "Quick Win" if i == 0 else "High Impact" if i == 1 else "Strategic"
                html += f"""<div style='margin-bottom:0.75rem;'><div style='font-weight:600; color:var(--text-bright);'><span class='suggestion-pill'>{lbl}</span> {fix['do']} <span style='font-size:0.7rem; color:var(--amber)'>[{fix['effort']}]</span></div>
                <div style='font-size:0.85rem; padding-left:1rem; border-left:2px solid var(--card-border); margin-top:0.25rem;'>{fix['why']} <br/><span style='color:var(--teal); font-weight:700;'>Est. Impact: {fix['impact']}</span></div></div>"""
            html += "</div>"
        return html + "</section>"

    def _calculate_reliability(self, results: dict) -> dict:
        main = results["authenticated"] if "authenticated" in results else results["anonymous"]
        ev = main["evaluation"]
        v = lambda k: ev.get(k, {}).get("verdict", "PASS")
        reliability = {
            "Availability": "Good" if float(main.get("evaluation", {}).get("failed_requests", {}).get("value", 0)) == 0 else "Poor",
            "Consistency": "Good" if main.get("baseline_stats", {}).get("lcp", {}).get("stddev", 0) < 500 else "At Risk",
            "UX Reliability": "Good" if v("lcp") == "PASS" else "Poor",
            "Frontend Stability": "Good" if v("cls") == "PASS" and v("tbt") == "PASS" else "At Risk",
            "Capacity Confidence": "Good" if len(main.get("ramp_results", [])) > 0 else "Poor"
        }
        reliability["Overall"] = "RELIABLE" if all(v == "Good" for v in [reliability["Availability"], reliability["UX Reliability"], reliability["Frontend Stability"]]) else "PARTIALLY RELIABLE" if reliability["Availability"] == "Good" else "UNRELIABLE"
        return reliability

    def _get_unit(self, key: str) -> str:
        if key in ("ttfb", "fcp", "lcp", "tbt", "inp", "load_time", "dom_content_loaded"):
            return "ms"
        if "size_kb" in key: return "KB"
        if "heap_used_mb" in key: return "MB"
        return ""

    def _get_glossary_html(self) -> str:
        glossary = {
            "TTFB": "<b>Time to First Byte</b>: Measures server responsiveness. High TTFB usually means slow DB queries or lack of server caching.",
            "FCP": "<b>First Contentful Paint</b>: When the browser renders the first bit of content. Crucial for user perceived speed.",
            "LCP": "<b>Largest Contentful Paint</b>: When the main content (hero image/text) is visible. Target: < 2.5s.",
            "CLS": "<b>Cumulative Layout Shift</b>: Measures visual stability. Avoid unexpected layout jumps by setting image dimensions.",
            "TBT": "<b>Total Blocking Time</b>: How long the main thread was 'frozen' by heavy JS, preventing user interaction.",
            "INP": "<b>Interaction to Next Paint</b>: Measures how quickly the page responds to clicks and keypresses throughout its life.",
            "RPS": "<b>Requests Per Second</b>: The throughput of your server. High RPS means your backend can handle many concurrent users simultaneously.",
            "Latency": "<b>Network Ping / Latency</b>: The time taken for an API trace or network request to travel from server to user. Over 1000ms is a warning.",
            "P95": "<b>95th Percentile Latency</b>: The maximum response time for 95% of users. Removes extreme outliers to give a reliable 'worst-case' speed.",
            "Concurrency": "<b>Concurrent Workers</b>: Parallel connections executing simultaneously inside the browser or network to test threshold limitations."
        }
        html = '<h2>📚 Technical Glossary</h2><section class="card"><div class="table-wrapper"><table>'
        for term, desc in glossary.items():
            html += f'<tr><td style="width:120px; font-weight:700; color:var(--text-bright)">{term}</td><td>{desc}</td></tr>'
        html += '</table></div></section>'
        
        # Add a static "How to Tackle Gaps" section
        html += '<h2>🛠️ Strategic Optimization Guide</h2><section class="card"><div class="metrics-grid">'
        strategies = [
            ("⚡ Server Side", "Use Redis caching and Cloudflare CDN to drop TTFB below 200ms."),
            ("🖼️ Visual Assets", "Use WebP/Avif formats and set explicit width/height to fix CLS."),
            ("📜 Script Loading", "Use 'defer' for non-critical JS to reduce TBT and improve INP."),
            ("☁️ Infrastructure", "Enable Brotli compression and HTTP/2 to slash resource transfer times.")
        ]
        for title, desc in strategies:
            html += f'<div class="card" style="border-left: 2px solid var(--amber);"><b style="color:var(--text-bright); display:block; margin-bottom:0.5rem">{title}</b><p style="font-size:0.85rem; color:var(--text-muted)">{desc}</p></div>'
        html += '</div></section>'
        return html

    def _get_lighthouse_section_html(self, results: dict) -> str:
        """
        Renders a side-by-side Lighthouse vs Framework comparison section.
        """
        main_mode = "authenticated" if "authenticated" in results else "anonymous"
        lh_comp = results.get(main_mode, {}).get("lighthouse_comparison")

        METRIC_LABELS = {
            "fcp":  ("FCP",  "First Contentful Paint",  "ms"),
            "lcp":  ("LCP",  "Largest Contentful Paint", "ms"),
            "tbt":  ("TBT",  "Total Blocking Time",      "ms"),
            "cls":  ("CLS",  "Cumulative Layout Shift",  ""),
            "ttfb": ("TTFB", "Server Response (TTFB)",   "ms"),
        }

        # ── Case 1: Lighthouse not available ────────────────────────────────
        if not lh_comp:
            return """
<h2>🔦 Lighthouse Ground-Truth Comparison</h2>
<section class="card lh-section">
  <div class="lh-header">
    <div>
      <p style="color:var(--text-bright); font-weight:600; margin-bottom:0.4rem"
        >Lighthouse CLI not detected</p>
      <p style="color:var(--text-muted); font-size:0.88rem; max-width:500px"
        >Install Lighthouse to enable ground-truth metric validation and get a
        system reliability score benchmarked against Google's auditing engine.</p>
    </div>
    <div>
      <span class="lh-badge-na">⚙️ Install: <code style="font-family:monospace"
        >npm install -g lighthouse</code></span>
    </div>
  </div>
  <div style="border-top:1px solid var(--card-border); padding-top:1rem; margin-top:0.5rem">
    <p style="color:var(--text-muted); font-size:0.82rem">
      Once installed, re-run the performance test. The next report will include a
      per-metric accuracy table, a reliability score ring, and Lighthouse's own
      performance score for cross-validation.
    </p>
  </div>
</section>
"""

        # ── Case 2: Error during LH run ──────────────────────────────────────
        if "error" in lh_comp.get(list(lh_comp.keys())[0] if lh_comp else "fcp", {}) or next(
            (True for v in lh_comp.values() if isinstance(v, dict) and "error" in v), False
        ):
            return ""

        # ── Case 3: Full comparison data ─────────────────────────────────────
        # Count accuracy
        total, accurate = 0, 0
        for key in METRIC_LABELS:
            entry = lh_comp.get(key, {})
            if entry.get("diff_pct") is not None:
                total += 1
                if entry.get("accurate"):
                    accurate += 1

        reliability_pct  = round((accurate / total) * 100) if total > 0 else 0
        ring_color = (
            "#00d9a6" if reliability_pct >= 80
            else "#ffaa00" if reliability_pct >= 60
            else "#ff4466"
        )
        reliability_label = (
            "Highly Reliable" if reliability_pct >= 80
            else "Partially Reliable" if reliability_pct >= 60
            else "Needs Calibration"
        )

        lh_score = lh_comp.get("score", {}).get("lighthouse_score", 0)
        lh_score_color = (
            "#00d9a6" if lh_score >= 90
            else "#ffaa00" if lh_score >= 50
            else "#ff4466"
        )

        # Ring CSS uses a conic-gradient trick
        ring_pct_css = f"{reliability_pct * 3.6}deg"

        # Build comparison rows
        rows_html = ""
        for key, (abbr, full_label, unit) in METRIC_LABELS.items():
            entry = lh_comp.get(key, {})
            ours   = entry.get("ours", 0)
            lh_val = entry.get("lighthouse", 0)
            diff   = entry.get("diff_pct")
            acc    = entry.get("accurate")

            if diff is None:
                row_cls  = "lh-row-na"
                badge    = f'<span class="lh-diff-badge" style="background:rgba(139,148,158,0.15); color:#8b949e">N/A</span>'
                acc_icon = "—"
            elif acc:
                row_cls  = "lh-row-accurate"
                badge    = f'<span class="lh-diff-badge" style="background:rgba(0,217,166,0.15); color:#00d9a6">±{diff}%</span>'
                acc_icon = "✅"
            else:
                row_cls  = "lh-row-drift"
                badge    = f'<span class="lh-diff-badge" style="background:rgba(255,170,0,0.15); color:#ffaa00">±{diff}%</span>'
                acc_icon = "⚠️ Drift"

            fmt = lambda v, u: f"{v:.3f}{u}" if u == "" else f"{v:.0f}{u}"

            rows_html += f"""
<tr class="{row_cls}">
  <td><b style="color:var(--text-bright)">{abbr}</b><br>
      <span style="font-size:0.75rem; color:var(--text-muted)">{full_label}</span></td>
  <td style="font-family:'IBM Plex Mono',monospace">{fmt(ours, unit)}</td>
  <td style="font-family:'IBM Plex Mono',monospace; color:#63b3ed">{fmt(lh_val, unit)}</td>
  <td>{badge}</td>
  <td>{acc_icon}</td>
</tr>"""

        return f"""
<h2>🔦 Lighthouse Ground-Truth Comparison</h2>
<section class="card lh-section">
  <div class="lh-header">
    <div style="flex:1">
      <p style="color:var(--text-bright); font-size:1rem; font-weight:600; margin-bottom:0.35rem"
        >System Reliability Score</p>
      <p style="color:var(--text-muted); font-size:0.85rem; max-width:520px"
        >Compares our Playwright-collected metrics against Google's Lighthouse CLI
        (ground truth). A metric is considered <em>accurate</em> when within ±20% of
        Lighthouse's value.</p>
    </div>
    <!-- Reliability ring -->
    <div style="text-align:center">
      <div class="lh-score-ring" style="--ring-pct:{ring_pct_css}; --ring-color:{ring_color}">
        <div class="lh-score-ring-inner">
          <span class="lh-score-pct">{reliability_pct}%</span>
          <span class="lh-score-label">Reliable</span>
        </div>
      </div>
      <div style="font-size:0.72rem; color:{ring_color}; margin-top:0.4rem; font-weight:700">{reliability_label}</div>
    </div>
    <!-- LH Performance Score -->
    <div style="text-align:center">
      <div class="lh-score-ring" style="--ring-pct:{lh_score * 3.6}deg; --ring-color:{lh_score_color}">
        <div class="lh-score-ring-inner">
          <span class="lh-score-pct">{lh_score:.0f}</span>
          <span class="lh-score-label">LH Score</span>
        </div>
      </div>
      <div style="font-size:0.72rem; color:{lh_score_color}; margin-top:0.4rem; font-weight:700">Lighthouse Perf</div>
    </div>
  </div>

  <div class="table-wrapper">
    <table>
      <thead>
        <tr>
          <th>Metric</th>
          <th>Our Framework</th>
          <th style="color:#63b3ed">Lighthouse (Truth)</th>
          <th>Deviation</th>
          <th>Verdict</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>

  <p style="margin-top:1rem; font-size:0.78rem; color:var(--text-muted); border-top:1px solid var(--card-border); padding-top:0.75rem">
    ✅ = within ±20% of Lighthouse  &nbsp;|&nbsp;  ⚠️ Drift = deviation exceeds 20%  &nbsp;|&nbsp;
    Accurate: <b style="color:#00d9a6">{accurate}/{total}</b> metrics
  </p>
</section>
"""

    def _get_dos_section_html(self, title: str, results: list, desc: str) -> str:
        if not results: return ""
        html = f'<h2>🔥 {title}</h2><section class="card"><p style="color:var(--text-muted); font-size:0.85rem; margin-bottom:1rem;">{desc}</p>'
        html += '<div class="table-wrapper"><table><thead><tr><th>Concurrency</th><th>Total Requests</th><th>Req/sec (RPS)</th><th>P95 Latency</th><th>Error Rate</th></tr></thead><tbody>'
        for st in results:
            err = st.get("error_rate_pct")
            if err is None:
                fails = st.get("failed", 0)
                tot = st.get("total_requests", st.get("ok", 0) + fails)
                err = (fails / tot) * 100 if tot > 0 else 0
                
            c = "PASS" if err == 0 else "FAIL" if err > 50 else "WARN"
            err_html = f"<span class='status-pill status-{c}'>{err:.1f}%</span>"
            users = st.get('concurrency', st.get('users', '-'))
            tot_reqs = st.get('total_requests', st.get('ok', 0) + st.get('failed', 0))
            html += f"<tr><td><b style='color:var(--text-bright)'>{users} Users</b></td>"
            html += f"<td>{tot_reqs}</td>"
            
            rps = st.get('rps')
            rps_html = f"{rps:.1f}" if isinstance(rps, (int, float)) else "-"
            html += f"<td style='font-family:\"IBM Plex Mono\",monospace'>{rps_html}</td>"
            
            p95 = st.get('p95_ms', st.get('p95_load_time', st.get('avg_time')))
            p95_html = f"{p95:.0f}ms" if isinstance(p95, (int, float)) else "-"
            html += f"<td style='font-family:\"IBM Plex Mono\",monospace'>{p95_html}</td>"
            
            html += f"<td>{err_html}</td></tr>"
        html += '</tbody></table></div></section>'
        return html

    def _get_network_section_html(self, results_data: dict) -> str:
        # Extract slowest from all_requests
        all_reqs = results_data.get("all_requests", [])
        if not all_reqs: return ""
        
        # Sort by duration
        slowest = sorted(all_reqs, key=lambda x: x.get("duration", 0), reverse=True)[:10]
        total_size_kb = results_data.get("total_resource_size_kb", 0)
        
        html = '<h2>🌐 Network Trace (Slowest Calls)</h2><section class="card">'
        html += f'<p style="color:var(--text-muted); font-size:0.85rem; margin-bottom:1rem;">Total Data Transferred: <b style="color:var(--text-bright)">{total_size_kb:.1f} KB</b></p>'
        html += '<div class="table-wrapper"><table><thead><tr><th>URL</th><th>Type</th><th>Latency</th></tr></thead><tbody>'
        for req in slowest:
            url = req.get("url", "")
            if len(url) > 60: url = url[:57] + "..."
            duration = req.get("duration", 0)
            c = "FAIL" if duration > 1000 else "WARN" if duration > 400 else "PASS"
            html += f"<tr><td style='max-width:300px; overflow:hidden; text-overflow:ellipsis;' title='{req.get('url')}'>{url}</td><td>{req.get('resource_type', req.get('type', '-'))}</td><td><span class='status-pill status-{c}'>{duration:.0f}ms</span></td></tr>"
        html += '</tbody></table></div></section>'
        return html

    def _get_resource_section_html(self, rg: dict) -> str:
        if not rg: return ""
        html = '<h2>📦 Asset Distribution</h2><section class="card"><div class="metrics-grid">'
        for rtype, data in rg.items():
            if data.get("count", 0) == 0: continue
            size = data.get("total_size_kb", 0)
            html += f"<div class='card metric-card' style='border-left-color:var(--text-bright)'><span class='metric-label'>{rtype.upper()}</span><div class='metric-value'>{size:.1f} KB</div><div class='metric-target'>Files: {data.get('count', 0)}</div></div>"
        html += '</div></section>'
        return html

    def generate(self, site_name: str, site_url: str, results: dict, output_path: Path, duration_seconds: float = 0) -> None:
        try:
            main_mode = "authenticated" if "authenticated" in results else "anonymous"
            r_main = results[main_mode]
            reliability = self._calculate_reliability(results)
            ts = datetime.now().strftime("%B %d, %Y at %I:%M %p")
            
            rel_html = '<h2>Reliability Dimensions</h2><section class="card"><div class="table-wrapper"><table><thead><tr><th>Dimension</th><th>Status</th><th>Explanation</th></tr></thead><tbody>'
            for dim, status in reliability.items():
                if dim == "Overall": continue
                c = "PASS" if status == "Good" else "WARN" if status == "At Risk" else "FAIL"
                rel_html += f"<tr><td><strong>{dim}</strong></td><td><span class='status-pill status-{c}'>{status}</span></td><td>Evaluated against {dim} thresholds.</td></tr>"
            rel_html += f"<tr><td><strong>VERDICT</strong></td><td><span class='status-pill status-{ 'PASS' if reliability['Overall'] == 'RELIABLE' else 'FAIL' }'>{reliability['Overall']}</span></td><td>System overall stability assessment.</td></tr></tbody></table></div></section>"

            metrics_html = '<h2>User Experience Metrics</h2><section class="card"><div class="metrics-grid">'
            for key, evaluation in r_main["evaluation"].items():
                unit = self._get_unit(key)
                border = "var(--teal)" if evaluation["verdict"] == "PASS" else "var(--red)" if evaluation["verdict"] == "FAIL" else "var(--amber)"
                metrics_html += f"""<div class='card metric-card' style='border-left-color:{border}'><span class='metric-label'>{key.replace("_", " ").upper()} <span class='status-pill status-{evaluation['verdict']}' style='font-size:0.6rem; float:right;'>{evaluation['verdict']}</span></span>
                <div class='metric-value'>{evaluation['value']}{unit}</div><div class='metric-target'>Target: {evaluation['threshold']}{unit}</div></div>"""
            metrics_html += '</div></section>'

            # lh_html = self._get_lighthouse_section_html(results)
            
            # Additional visual modules
            dos_html = self._get_dos_section_html("R&D DoS HTTP Stress Test", r_main.get("dos_results", []), "Direct protocol-level HTTP flooding bypassing UI rendering.")
            ramp_html = self._get_dos_section_html("Playwright Breakpoint Scaling", r_main.get("ramp_results", []), "End-to-end full browser concurrency testing.")
            net_html = self._get_network_section_html(r_main)
            res_html = self._get_resource_section_html(r_main.get("resource_groups", {}))

            html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Perf Report — {site_name}</title>{self.CSS}</head><body><div class="container"><header><h1>Executive Reliability Audit</h1><p class="subtitle">Analysis for <b>{site_name}</b> • {ts}</p></header>
            {rel_html} {metrics_html} {res_html} {net_html} {ramp_html} {dos_html} {self._get_fix_suggestions_html(r_main['evaluation'])} {self._get_glossary_html()}</div></body></html>"""
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(html, encoding="utf-8")
            
            root_dir = output_path.parent.parent.parent
            (root_dir / "latest_report.html").write_text(html, encoding="utf-8")
            
            import json
            def serialize(obj):
                if isinstance(obj, Path): return str(obj)
                return str(obj)
            
            (root_dir / "latest_results.json").write_text(json.dumps(results, default=serialize), encoding="utf-8")
            print(f"  📄 Premium report saved → {output_path}")
            
        except Exception as e:
            print(f"  ❌ Failed to generate report: {e}")
            import traceback
            traceback.print_exc()

def generate_report(**kwargs) -> None:
    HTMLReporter().generate(**kwargs)
