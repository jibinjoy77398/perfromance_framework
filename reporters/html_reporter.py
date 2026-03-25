"""
html_reporter.py — Generates a fully self-contained HTML performance report.
Uses a premium, modern glassmorphic UI design suitable for browser viewing.
"""
from __future__ import annotations
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════════
#   Abstract Base — all reporters implement this interface
# ═══════════════════════════════════════════════════════════════════════════

class BaseReporter(ABC):
    """Abstract base class for all report generators."""
    @abstractmethod
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
        ...


# ═══════════════════════════════════════════════════════════════════════════
#   HTML Reporter — Premium Dashboard Implementation
# ═══════════════════════════════════════════════════════════════════════════

class HTMLReporter(BaseReporter):
    """Generates a premium, visually stunning HTML performance report."""

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _verdict_color(verdict: str) -> str:
        return {"PASS": "#10B981", "WARN": "#F59E0B", "FAIL": "#EF4444"}.get(verdict, "#94A3B8")

    @staticmethod
    def _verdict_gradient(verdict: str) -> str:
        return {"PASS": "linear-gradient(135deg, #10B981, #059669)", 
                "WARN": "linear-gradient(135deg, #F59E0B, #D97706)", 
                "FAIL": "linear-gradient(135deg, #EF4444, #DC2626)"}.get(verdict, "#94A3B8")

    @staticmethod
    def _grade_color(grade: str) -> str:
        return {"A": "#10B981", "B": "#84CC16", "C": "#F59E0B",
                "D": "#F97316", "F": "#EF4444"}.get(grade, "#94A3B8")

    @staticmethod
    def _grade_shadow(grade: str) -> str:
        return {"A": "rgba(16,185,129,0.3)", "B": "rgba(132,204,22,0.3)", "C": "rgba(245,158,11,0.3)",
                "D": "rgba(249,115,22,0.3)", "F": "rgba(239,68,68,0.3)"}.get(grade, "rgba(148,163,184,0.3)")

    @staticmethod
    def _fmt(value, unit: str = "") -> str:
        if isinstance(value, float):
            return f"{value:.2f}{unit}"
        return f"{value}{unit}"

    @staticmethod
    def _metric_unit(key: str) -> str:
        if key in ("cls",): return ""
        if "mb" in key: return " MB"
        if "kb" in key: return " KB"
        if "pct" in key: return "%"
        if "count" in key or key in ("resource_count", "failed_requests", "slow_requests", "breakpoint_users"):
            return ""
        return " ms"

    CSS = """
<style>
  :root {
    --bg-color: #0B1120;
    --card-bg: rgba(30, 41, 59, 0.4);
    --card-border: rgba(255, 255, 255, 0.08);
    --text-main: #F8FAFC;
    --text-muted: #94A3B8;
    --accent: linear-gradient(135deg, #818CF8, #C084FC);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    background: var(--bg-color);
    background-image: radial-gradient(circle at top right, rgba(129,140,248,0.1), transparent 400px),
                      radial-gradient(circle at bottom left, rgba(16,185,129,0.05), transparent 400px);
    color: var(--text-main);
    min-height: 100vh;
    padding: 3rem 1.5rem;
    line-height: 1.5;
  }
  .container { max-width: 1200px; margin: 0 auto; }
  
  /* Typography */
  h1 { font-size: 2.75rem; font-weight: 900; letter-spacing: -0.02em; margin-bottom: 0.5rem;
       background: var(--accent); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  h2 { font-size: 1.25rem; font-weight: 700; color: #E2E8F0; margin: 2.5rem 0 1rem;
       display: flex; align-items: center; gap: 0.5rem; }
  h2::before { content: ""; display: block; width: 8px; height: 8px; border-radius: 50%; background: #818CF8; }
  .subtitle { color: var(--text-muted); font-size: 1rem; margin-bottom: 3rem; font-weight: 500; }
  
  /* Glassmorphic Cards */
  .card { 
    background: var(--card-bg); 
    backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--card-border); 
    border-radius: 20px; 
    padding: 2rem; 
    box-shadow: 0 10px 30px -10px rgba(0,0,0,0.5);
    margin-bottom: 1.5rem;
  }

  /* Scorecard Hero */
  .scorecard { display: flex; align-items: center; gap: 2rem; flex-wrap: wrap; }
  .grade-badge {
    display: flex; align-items: center; justify-content: center;
    width: 100px; height: 100px; border-radius: 50%;
    font-size: 3.5rem; font-weight: 900; 
    background: var(--card-bg);
    border: 4px solid var(--grade-color);
    color: var(--grade-color);
    box-shadow: 0 0 30px var(--grade-shadow), inset 0 0 20px var(--grade-shadow);
    text-shadow: 0 0 10px var(--grade-shadow);
    animation: pulseGlow 3s infinite alternate;
  }
  @keyframes pulseGlow { from { box-shadow: 0 0 20px var(--grade-shadow); } to { box-shadow: 0 0 40px var(--grade-shadow); } }
  .score-stats { font-size: 1.1rem; color: var(--text-muted); line-height: 1.8; }
  .score-stats strong { color: var(--text-main); font-size: 1.25rem; }
  .stat-pill { display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 999px; font-weight: 700; font-size: 0.85rem; margin-right: 0.5rem; color: #fff; }

  /* Metrics Grid */
  .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.25rem; }
  .metric-card {
    background: rgba(15, 23, 42, 0.6); border-radius: 16px; padding: 1.5rem;
    border: 1px solid var(--card-border);
    border-top: 4px solid var(--verdict-color);
    transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.2s;
    position: relative; overflow: hidden;
  }
  .metric-card:hover { transform: translateY(-5px); box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5); }
  .metric-label { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-muted); margin-bottom: 0.5rem; font-weight: 600; }
  .metric-value { font-size: 2rem; font-weight: 900; letter-spacing: -0.02em; color: var(--text-main); margin-bottom: 0.25rem; }
  .metric-threshold { font-size: 0.8rem; color: #64748B; display: flex; justify-content: space-between; align-items: center; }
  .verdict-tag { font-size: 0.7rem; font-weight: 800; padding: 0.2rem 0.6rem; border-radius: 6px; color: #fff; background: var(--verdict-grad); letter-spacing: 0.05em; }

  /* Data Tables */
  .table-wrapper { overflow-x: auto; border-radius: 12px; border: 1px solid var(--card-border); }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; text-align: left; }
  th { background: rgba(15,23,42,0.8); padding: 1rem; color: var(--text-muted); font-weight: 600; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; border-bottom: 1px solid var(--card-border); white-space: nowrap; }
  td { padding: 1rem; border-bottom: 1px solid rgba(255,255,255,0.02); color: #CBD5E1; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(255,255,255,0.03); }
  td strong { color: var(--text-main); font-weight: 700; }
  
  /* Breakpoint Ramp */
  .ramp-row { display: flex; align-items: center; gap: 1rem; margin-bottom: 0.75rem; }
  .ramp-label { width: 80px; font-weight: 700; color: var(--text-muted); font-size: 0.9rem; text-align: right; }
  .ramp-bar-track { flex: 1; height: 24px; background: rgba(0,0,0,0.3); border-radius: 12px; overflow: hidden; position: relative; }
  .ramp-bar-fill { height: 100%; border-radius: 12px; transition: width 1s cubic-bezier(0.4, 0, 0.2, 1); display: flex; align-items: center; padding-left: 0.5rem; font-size: 0.75rem; font-weight: 700; color: rgba(255,255,255,0.9); text-shadow: 0 1px 2px rgba(0,0,0,0.5); }
  .ramp-meta { min-width: 150px; font-size: 0.85rem; color: var(--text-muted); }
  
  /* Resource Lists */
  .resource-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }
  @media (max-width: 768px) { .resource-grid { grid-template-columns: 1fr; } }
  .list-title { font-size: 0.9rem; font-weight: 700; color: #94A3B8; text-transform: uppercase; margin-bottom: 1rem; letter-spacing: 0.05em; border-bottom: 1px solid var(--card-border); padding-bottom: 0.5rem; }
  .resource-list { list-style: none; }
  .resource-list li { display: flex; align-items: center; gap: 0.75rem; padding: 0.6rem 0; border-bottom: 1px dashed rgba(255,255,255,0.05); }
  .resource-list li:last-child { border-bottom: none; }
  .r-val { font-family: monospace; font-size: 0.9rem; font-weight: 700; color: #E2E8F0; min-width: 70px; }
  .r-tag { background: rgba(56,189,248,0.1); color: #38BDF8; font-size: 0.7rem; padding: 0.15rem 0.5rem; border-radius: 4px; font-weight: 700; text-transform: uppercase; }
  .r-url { font-size: 0.8rem; color: #64748B; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  /* Details Panel */
  details summary { cursor: pointer; color: #818CF8; font-weight: 600; padding: 1rem 0; user-select: none; transition: color 0.2s; outline: none; }
  details summary:hover { color: #A5B4FC; }
  details[open] summary { border-bottom: 1px solid var(--card-border); margin-bottom: 1rem; }
</style>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
"""

    # ── Plain English Mappings ───────────────────────────────────────────
    METRIC_NAMES = {
        "lcp": "Main Content Load Time (LCP)",
        "fcp": "Initial Paint Time (FCP)",
        "ttfb": "Server Response (TTFB)",
        "cls": "Visual Stability (CLS)",
        "load_time": "Total Load Time",
    }
    METRIC_DESCS = {
        "lcp": "How long it takes for the largest image or text block to become visible.",
        "fcp": "How long until the very first piece of content appears on screen.",
        "ttfb": "How fast the server begins sending data after a request.",
        "cls": "How much the page layout unexpectedly jumps around while loading.",
        "load_time": "How long it takes for the entire page to fully finish loading.",
    }

    # ── Section builders ─────────────────────────────────────────────────

    def _metric_cards_html(self, evaluation: dict) -> str:
        html = '<div class="metrics-grid">'
        for key, ev in evaluation.items():
            color = self._verdict_color(ev["verdict"])
            grad = self._verdict_gradient(ev["verdict"])
            unit = self._metric_unit(key)
            formatted_val = self._fmt(ev['value'])
            name = self.METRIC_NAMES.get(key, key.replace('_', ' ').title())
            desc = self.METRIC_DESCS.get(key, "Performance metric.")
            
            html += f"""
        <div class="metric-card" style="--verdict-color:{color}; --verdict-grad:{grad}">
          <div class="metric-label">{name}</div>
          <p style="font-size:0.75rem; color:var(--text-muted); margin-bottom:1rem; line-height:1.4;">{desc}</p>
          <div class="metric-value">{formatted_val}<span style="font-size:1rem;color:#64748B;font-weight:600">{unit}</span></div>
          <div class="metric-threshold">
            <span>Target: {ev['threshold']}{unit}</span>
            <span class="verdict-tag">{"Passes Target" if ev['verdict'] == "PASS" else "Needs Improvement" if ev['verdict'] == "WARN" else "Failing"}</span>
          </div>
        </div>"""
        html += "</div>"
        return html

    def _baseline_table_html(self, stats: dict) -> str:
        if not stats: return "<p style='color:var(--text-muted)'>No baseline data collected.</p>"
        
        lcp_stat = stats.get("lcp", {}).get("p50", "?")
        html = f"<p style='margin-bottom:1.5rem;font-size:1.1rem;'>When loaded by multiple users at once, the typical main content load time is <strong>{lcp_stat} ms</strong>.</p>"
        
        html += '<details><summary>View Technical Variability Data</summary>'
        html += '<div class="table-wrapper" style="margin-top:1rem"><table><thead><tr><th>Metric</th><th>Typical (Median)</th><th>Worst Case (95th %ile)</th><th>Min</th><th>Max</th><th>Fluctuation</th><th>Runs</th></tr></thead><tbody>'
        for v, s in stats.items():
            stddev_color = "#EF4444" if s["stddev"] > 800 else "#10B981"
            p95_color = "#EF4444" if s["p95"] > 6000 else "#10B981"
            name = self.METRIC_NAMES.get(v, v.replace('_', ' ').title())
            html += f"""<tr>
          <td><strong>{name}</strong></td>
          <td>{s['p50']} ms</td>
          <td style="color:{p95_color};font-weight:700">{s['p95']} ms</td>
          <td>{s['min']} ms</td>
          <td>{s['max']} ms</td>
          <td style="color:{stddev_color};font-weight:700">± {s['stddev']}</td>
          <td>{s.get('runs','?')}</td>
        </tr>"""
        html += "</tbody></table></div></details>"
        return html

    def _network_stress_html(self, profile_results: dict) -> str:
        if not profile_results: return "<p style='color:var(--text-muted)'>No network stress data collected.</p>"
        
        html = "<p style='margin-bottom:1.5rem;font-size:1.1rem;'>We simulated slow internet connections (like 3G mobile networks) to see how the site degrades.</p>"
        html += '<details><summary>View Network Throttling Data</summary>'
        
        metrics_shown = ["fcp", "lcp", "load_time"]
        html += '<div class="table-wrapper" style="margin-top:1rem"><table><thead><tr><th>Internet Speed</th>'
        for m in metrics_shown:
            html += f"<th>{self.METRIC_NAMES.get(m, m)}</th>"
        html += "</tr></thead><tbody>"
        thresholds = {"fcp": 1800, "lcp": 2500, "ttfb": 800, "load_time": 4000, "cls": 0.1}
        for profile, m in profile_results.items():
            html += f"<tr><td><strong>{profile}</strong></td>"
            for met in metrics_shown:
                val = m.get(met, 0)
                thr = thresholds.get(met, 9999)
                color = "#EF4444" if val > thr else "#10B981"
                html += f"<td style='color:{color};font-weight:700'>{val:.1f} <span style='font-size:0.75rem;font-weight:500;color:#64748b'>ms</span></td>"
            html += "</tr>"
        html += "</tbody></table></div></details>"
        return html

    def _breakpoint_html(self, ramp_results: list[dict]) -> str:
        if not ramp_results: return "<p style='color:var(--text-muted)'>No capacity data collected.</p>"
        
        broke_at = next((r["users"] for r in ramp_results if r.get("error_rate_pct", 0) > 5 or r.get("p95_load_time", 0) > 6000), None)
        if broke_at:
            html = f"<p style='margin-bottom:1.5rem;font-size:1.1rem;color:#F59E0B'>⚠️ The site begins to struggle or crash when reaching <strong>{broke_at} concurrent users</strong>.</p>"
        else:
            max_u = max((r["users"] for r in ramp_results), default=0)
            html = f"<p style='margin-bottom:1.5rem;font-size:1.1rem;color:#10B981'>✅ The site remained stable even at the maximum tested load of <strong>{max_u} concurrent users</strong>.</p>"
            
        html += '<details><summary>View Capacity Test Results</summary><div style="margin-top:1rem">'
        
        max_p95 = max((r.get("p95_load_time", 0) for r in ramp_results), default=1) or 1
        for r in ramp_results:
            broke = r.get("error_rate_pct", 0) > 5 or r.get("p95_load_time", 0) > 6000
            color = "linear-gradient(90deg, #EF4444, #B91C1C)" if broke else "linear-gradient(90deg, #10B981, #047857)"
            pct_width = min(100, max(5, int((r.get("p95_load_time", 0) / max_p95) * 100)))
            html += f"""
        <div class="ramp-row">
          <div class="ramp-label">{r['users']} Users</div>
          <div class="ramp-bar-track">
            <div class="ramp-bar-fill" style="width: {pct_width}%; background: {color};">
              {r.get('p95_load_time',0):.0f}ms (Worst Case)
            </div>
          </div>
          <div class="ramp-meta">
            <span style="color:{'#EF4444' if r.get('error_rate_pct',0)>5 else '#10B981'};font-weight:700">{r.get('error_rate_pct',0):.1f}% Err</span>
            &nbsp;·&nbsp; {'🔴 Limit Reached' if broke else '🟢 Stable'}
          </div>
        </div>"""
        html += "</div></details>"
        return html

    def _resource_html(self, resource_groups: dict, requests: list) -> str:
        if not resource_groups: return "<p style='color:var(--text-muted)'>No asset data collected.</p>"
        
        total_kb = sum(g.get("total_size_kb", 0) for g in resource_groups.values())
        total_reqs = sum(g.get("count", 0) for g in resource_groups.values())
        html = f"<p style='margin-bottom:1.5rem;font-size:1.1rem;'>The page downloads <strong>{total_reqs} files</strong> totaling <strong>{total_kb/1024:.1f} MB</strong> (images, scripts, styles).</p>"
        
        html += '<details><summary>View Asset Breakdown & Slowest Requests</summary><div style="margin-top:1rem">'
        # Summary Table
        html += '<div class="table-wrapper" style="margin-bottom:2rem"><table><thead><tr><th>Asset Type</th><th>Requests</th><th>Total Payload</th><th>Avg Delivery Time</th></tr></thead><tbody>'
        for rtype, data in sorted(resource_groups.items(), key=lambda x: -x[1].get("total_size_kb", 0)):
            html += (f"<tr><td><span class='r-tag'>{rtype}</span></td>"
                     f"<td><strong>{data['count']}</strong></td>"
                     f"<td>{data['total_size_kb']:.1f} KB</td>"
                     f"<td>{data.get('avg_duration_ms',0):.0f} ms</td></tr>")
        html += "</tbody></table></div>"

        if requests:
            html += '<div class="resource-grid">'
            # Slowest
            slowest = sorted(requests, key=lambda x: x.get("duration_ms", 0), reverse=True)[:8]
            html += "<div><div class='list-title'>🐢 Top Longest Requests</div><ul class='resource-list'>"
            for r in slowest:
                html += (f"<li><span class='r-val' style='color:#F59E0B'>{r.get('duration_ms',0):.0f}ms</span>"
                         f"<span class='r-tag'>{r.get('resource_type','?')}</span>"
                         f"<span class='r-url' title='{r.get('url','')}'>{r.get('url','')}</span></li>")
            html += "</ul></div>"
            
            # Heaviest
            heaviest = sorted(requests, key=lambda x: x.get("size_bytes", 0), reverse=True)[:8]
            html += "<div><div class='list-title'>🐘 Top Heaviest Payloads</div><ul class='resource-list'>"
            for r in heaviest:
                html += (f"<li><span class='r-val' style='color:#818CF8'>{r.get('size_bytes',0)/1024:.1f}kb</span>"
                         f"<span class='r-tag'>{r.get('resource_type','?')}</span>"
                         f"<span class='r-url' title='{r.get('url','')}'>{r.get('url','')}</span></li>")
            html += "</ul></div></div>"
        
        html += '</div></details>'
        return html

    # ── Main entry point ─────────────────────────────────────────────────

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
        grade_col = self._grade_color(grade)
        grade_shadow = self._grade_shadow(grade)
        ts = datetime.now().strftime("%B %d, %Y at %I:%M %p")

        grade_desc = {
            "A": "Excellent. Feels instant.",
            "B": "Good. Slightly slow on mobile.",
            "C": "Average. Noticeable delays.",
            "D": "Poor. Users will get frustrated.",
            "F": "Failing. Severe speed or crash issues."
        }.get(grade, "")

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Performance Report — {site_name}</title>
  {self.CSS}
</head>
<body>
<div class="container">
  
  <header style="margin-bottom: 2rem;">
    <h1>Executive Performance Report</h1>
    <p class="subtitle">Report for <b>{site_name}</b> (<a href="{site_url}" style="color:#818CF8;text-decoration:none" target="_blank">{site_url}</a>) &nbsp;•&nbsp; Generated {ts} &nbsp;•&nbsp; Duration: {duration_seconds:.1f}s</p>
  </header>

  <section class="card">
    <div class="scorecard" style="--grade-color:{grade_col}; --grade-shadow:{grade_shadow}">
      <div class="grade-badge">{grade}</div>
      <div class="score-stats">
        <strong>Overall Health: {grade_desc}</strong><br>
        <div style="margin-top:0.5rem">
          <span class="stat-pill" style="background:{self._verdict_gradient('PASS')}">{passes} Passed</span>
          <span class="stat-pill" style="background:{self._verdict_gradient('WARN')}">{warns} Warnings</span>
          <span class="stat-pill" style="background:{self._verdict_gradient('FAIL')}">{fails} Failed</span>
        </div>
        <div style="font-size:0.9rem; margin-top:0.5rem">We checked {passes+warns+fails} strict speed targets to determine this grade.</div>
      </div>
    </div>
  </section>

  <h2>User Experience Metrics</h2>
  <section class="card">
    {self._metric_cards_html(evaluation)}
  </section>

  <h2>Performance Under Normal Traffic</h2>
  <section class="card">
    {self._baseline_table_html(baseline_stats)}
  </section>

  <h2>Performance on Slow Internet (Mobile)</h2>
  <section class="card">
    {self._network_stress_html(network_stress)}
  </section>

  <h2>User Capacity (Crash Test)</h2>
  <section class="card">
    {self._breakpoint_html(ramp_results)}
  </section>

  <h2>Page Size & Heavy Assets</h2>
  <section class="card">
    {self._resource_html(resource_groups, all_requests)}
  </section>

</div>
<script>
  // Tiny script to animate bars on load
  document.addEventListener("DOMContentLoaded", () => {{
    const bars = document.querySelectorAll('.ramp-bar-fill');
    bars.forEach(bar => {{
      const target = bar.style.width;
      bar.style.width = '0%';
      setTimeout(() => {{ bar.style.width = target; }}, 100);
    }});
  }});
</script>
</body>
</html>"""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        print(f"\n  📄 Exec report saved → {output_path}")

# ── Backward-compatible free function ────────────────────────────────────

def generate_report(**kwargs) -> None:
    """Backward-compatible wrapper — calls HTMLReporter().generate()."""
    HTMLReporter().generate(**kwargs)

