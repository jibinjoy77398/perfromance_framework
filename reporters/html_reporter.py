"""
html_reporter.py — Generates a fully self-contained HTML performance report.
Uses a premium, modern glassmorphic UI design suitable for browser viewing.
"""
from __future__ import annotations
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path


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
    """Generates a premium, visually stunning HTML performance report."""

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
  
  h1 { font-size: 2.75rem; font-weight: 900; letter-spacing: -0.02em; margin-bottom: 0.5rem;
       background: var(--accent); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  h2 { font-size: 1.25rem; font-weight: 700; color: #E2E8F0; margin: 2.5rem 0 1rem; display: flex; align-items: center; gap: 0.5rem; }
  h2::before { content: ""; display: block; width: 8px; height: 8px; border-radius: 50%; background: #818CF8; }
  .subtitle { color: var(--text-muted); font-size: 1rem; margin-bottom: 3rem; font-weight: 500; }
  
  .card { 
    background: var(--card-bg); 
    backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--card-border); 
    border-radius: 20px; 
    padding: 2rem; 
    box-shadow: 0 10px 30px -10px rgba(0,0,0,0.5);
    margin-bottom: 1.5rem;
  }

  .scorecard { display: flex; align-items: stretch; gap: 2rem; flex-wrap: wrap; }
  .sc-left { display: flex; align-items: center; gap: 2rem; flex: 1; }
  .grade-badge { display: flex; align-items: center; justify-content: center; width: 100px; height: 100px; border-radius: 50%; font-size: 3.5rem; font-weight: 900; background: var(--card-bg); border: 4px solid var(--grade-color); color: var(--grade-color); box-shadow: 0 0 30px var(--grade-shadow), inset 0 0 20px var(--grade-shadow); text-shadow: 0 0 10px var(--grade-shadow); animation: pulseGlow 3s infinite alternate; }
  @keyframes pulseGlow { from { box-shadow: 0 0 20px var(--grade-shadow); } to { box-shadow: 0 0 40px var(--grade-shadow); } }
  .score-stats { font-size: 1.1rem; color: var(--text-muted); line-height: 1.8; }
  
  .auth-overhead-card { flex: 1; min-width: 300px; border-left: 2px dashed rgba(255,255,255,0.1); padding-left: 2rem; display:flex; flex-direction:column; justify-content:center; }
  .auth-stat-value { font-size: 2.5rem; font-weight: 900; color: #F59E0B; line-height:1; margin-bottom: 0.2rem; }
  .auth-stat-label { font-size: 0.85rem; color: #94A3B8; text-transform: uppercase; font-weight: 600; letter-spacing: 0.05em; }

  .stat-pill { display: inline-flex; align-items: center; padding: 0.25rem 0.75rem; border-radius: 999px; font-weight: 700; font-size: 0.85rem; margin-right: 0.5rem; color: #fff; }

  .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.25rem; }
  .metric-card { background: rgba(15, 23, 42, 0.6); border-radius: 16px; padding: 1.5rem; border: 1px solid var(--card-border); transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.2s; position: relative; overflow: hidden; }
  .metric-card:hover { transform: translateY(-5px); box-shadow: 0 10px 25px -5px rgba(0,0,0,0.5); }
  .metric-label { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-muted); margin-bottom: 0.5rem; font-weight: 600; }
  .metric-value { font-size: 1.8rem; font-weight: 900; letter-spacing: -0.02em; margin-bottom: 0.25rem; display: flex; align-items: baseline; gap: 0.5rem; }
  .verdict-tag { font-size: 0.7rem; font-weight: 800; padding: 0.2rem 0.6rem; border-radius: 6px; color: #fff; letter-spacing: 0.05em; }

  .table-wrapper { overflow-x: auto; border-radius: 12px; border: 1px solid var(--card-border); }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; text-align: left; }
  th { background: rgba(15,23,42,0.8); padding: 1rem; color: var(--text-muted); font-weight: 600; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; border-bottom: 1px solid var(--card-border); white-space: nowrap; }
  td { padding: 1rem; border-bottom: 1px solid rgba(255,255,255,0.02); color: #CBD5E1; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: rgba(255,255,255,0.03); }
  
  .ramp-row { display: flex; align-items: center; gap: 1rem; margin-bottom: 0.75rem; }
  .ramp-label { width: 80px; font-weight: 700; color: var(--text-muted); font-size: 0.9rem; text-align: right; }
  .ramp-bar-track { flex: 1; height: 24px; background: rgba(0,0,0,0.3); border-radius: 12px; overflow: hidden; position: relative; }
  .ramp-bar-fill { height: 100%; border-radius: 12px; transition: width 1s cubic-bezier(0.4, 0, 0.2, 1); display: flex; align-items: center; padding-left: 0.5rem; font-size: 0.75rem; font-weight: 700; color: rgba(255,255,255,0.9); text-shadow: 0 1px 2px rgba(0,0,0,0.5); }
  .ramp-meta { min-width: 150px; font-size: 0.85rem; color: var(--text-muted); }
  
  .details-btn { cursor: pointer; color: #818CF8; font-weight: 600; padding: 1rem 0; user-select: none; transition: color 0.2s; outline: none; }
  .details-btn:hover { color: #A5B4FC; }
  details[open] summary { border-bottom: 1px solid var(--card-border); margin-bottom: 1rem; }
</style>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
"""

    METRIC_NAMES = {
        "lcp": "Main Content Load Time (LCP)",
        "fcp": "Initial Paint Time (FCP)",
        "ttfb": "Server Response (TTFB)",
        "cls": "Visual Stability (CLS)",
        "load_time": "Total Load Time",
    }
    METRIC_DESCS = {
        "lcp": "How long it takes for the largest image/text to become visible.",
        "fcp": "How long until the first piece of content appears.",
        "ttfb": "How fast the server begins sending data.",
        "cls": "How much the page layout unexpected jumps while loading.",
        "load_time": "How long the entire page takes to fully finish loading.",
    }

    def _metric_cards_html(self, results: dict) -> str:
        # Display side-by-side if both exist, otherwise just main
        main_mode = "authenticated" if "authenticated" in results else "anonymous"
        eval_main = results[main_mode]["evaluation"]
        has_anon = "anonymous" in results and "authenticated" in results
        
        html = '<div class="metrics-grid">'
        for key, ev in eval_main.items():
            unit = self._metric_unit(key)
            name = self.METRIC_NAMES.get(key, key.replace('_', ' ').title())
            desc = self.METRIC_DESCS.get(key, "Performance metric.")
            
            # Primary value (Authenticated usually)
            val_main = self._fmt(ev['value'])
            c_main = self._verdict_color(ev['verdict'])
            g_main = self._verdict_gradient(ev['verdict'])
            
            # Comparison value (Anonymous)
            comp_html = ""
            if has_anon and key in results["anonymous"]["evaluation"]:
                ev_anon = results["anonymous"]["evaluation"].get(key, {})
                val_anon = self._fmt(ev_anon.get('value', 0))
                c_anon = self._verdict_color(ev_anon.get('verdict', 'WARN'))
                comp_html = f"""
                <div style="font-size: 0.85rem; margin-top: 0.5rem; color:#94A3B8; display:flex; justify-content:space-between;">
                  <span>🔓 Public (CDN): <span style="color:{c_anon};font-weight:700">{val_anon}{unit}</span></span>
                </div>
                """
            
            html += f"""
        <div class="metric-card" style="border-top-color:{c_main}">
          <div class="metric-label">{name}</div>
          <p style="font-size:0.75rem; color:var(--text-muted); margin-bottom:1rem; line-height:1.4;">{desc}</p>
          <div class="metric-value" style="color:{c_main}">
            {'🔐 ' if has_anon else ''}{val_main}<span style="font-size:1rem;color:#64748B;font-weight:600">{unit}</span>
          </div>
          <div class="metric-threshold" style="font-size:0.75rem;">
            <span>Target: {ev['threshold']}{unit}</span>
            <span class="verdict-tag" style="background:{g_main}">{ev['verdict']}</span>
          </div>
          {comp_html}
        </div>"""
        html += "</div>"
        return html

    def _baseline_table_html(self, results: dict) -> str:
        html = ""
        for mode, data in results.items():
            stats = data.get("baseline_stats")
            if not stats: continue
            
            lcp_stat = stats.get("lcp", {}).get("p50", "?")
            title = "Public Load Typical Speed" if mode == "anonymous" else "Authenticated Full-Stack Speed"
            html += f"<p style='margin-bottom:0.5rem;font-size:1.1rem;'><strong>{title}:</strong> {lcp_stat} ms.</p>"
            
            html += f'<details><summary class="details-btn">View {mode.title()} Variability Data</summary>'
            html += '<div class="table-wrapper" style="margin-top:0.5rem; margin-bottom:1.5rem;"><table><thead><tr><th>Metric</th><th>p50 (Median)</th><th>p95 (Worst Case)</th><th>Min</th><th>Max</th><th>StdDev</th></tr></thead><tbody>'
            for v, s in stats.items():
                p95_color = "#EF4444" if s["p95"] > 6000 else "#10B981"
                name = self.METRIC_NAMES.get(v, v.title())
                html += f"<tr><td><strong>{name}</strong></td><td>{s['p50']} ms</td><td style='color:{p95_color};font-weight:700'>{s['p95']} ms</td><td>{s['min']} ms</td><td>{s['max']} ms</td><td>± {s['stddev']}</td></tr>"
            html += "</tbody></table></div></details>"
        return html

    def _network_stress_html(self, results: dict) -> str:
        html = "<p style='margin-bottom:1.5rem;font-size:1.1rem;'>We simulated slow internet connections (like 3G mobile networks).</p>"
        for mode, data in results.items():
            prof = data.get("network_stress")
            if not prof: continue
            html += f'<details><summary class="details-btn">View {mode.title()} Throttling Data</summary>'
            html += '<div class="table-wrapper" style="margin-top:0.5rem; margin-bottom:1.5rem;"><table><thead><tr><th>Internet Speed</th><th>LCP</th><th>Load Time</th></tr></thead><tbody>'
            for p, m in prof.items():
                html += f"<tr><td><strong>{p}</strong></td><td>{m.get('lcp',0):.1f} ms</td><td>{m.get('load_time',0):.1f} ms</td></tr>"
            html += "</tbody></table></div></details>"
        return html

    def _breakpoint_html(self, results: dict) -> str:
        html = ""
        for mode, data in results.items():
            ramp = data.get("ramp_results")
            if not ramp: continue
            
            broke_at = next((r["users"] for r in ramp if r.get("error_rate_pct", 0) > 5 or r.get("p95_load_time", 0) > 6000), None)
            alert = f"⚠️ Begins to struggle at <strong>{broke_at} concurrent users</strong>." if broke_at else f"✅ Stable at max load."
            title = "Login Storm authentications" if mode == "authenticated" else "Anonymous traffic drops"
            html += f"<p style='margin-bottom:0.5rem;font-size:1.1rem;'><strong>{title}:</strong> {alert}</p>"
            
            html += f'<details><summary class="details-btn">View {mode.title()} Capacity Graph</summary><div style="margin-top:1rem; margin-bottom:2rem;">'
            max_p95 = max((r.get("p95_load_time", 0) for r in ramp), default=1) or 1
            for r in ramp:
                broke = r.get("error_rate_pct", 0) > 5 or r.get("p95_load_time", 0) > 6000
                color = "linear-gradient(90deg, #EF4444, #B91C1C)" if broke else "linear-gradient(90deg, #10B981, #047857)"
                pct = min(100, max(5, int((r.get("p95_load_time", 0) / max_p95) * 100)))
                html += f"""
            <div class="ramp-row">
              <div class="ramp-label">{r['users']} Users</div>
              <div class="ramp-bar-track"><div class="ramp-bar-fill" style="width: {pct}%; background: {color};">{r.get('p95_load_time',0):.0f}ms</div></div>
              <div class="ramp-meta"><span style="color:{'#EF4444' if r.get('error_rate_pct',0)>5 else '#10B981'};font-weight:700">{r.get('error_rate_pct',0):.1f}% Err</span></div>
            </div>"""
            html += "</div></details>"
        return html

    def _resource_html(self, results: dict) -> str:
        html = ""
        for mode, data in results.items():
            rg = data.get("resource_groups")
            if not rg: continue
            tkb = sum(g.get("total_size_kb", 0) for g in rg.values())
            trq = sum(g.get("count", 0) for g in rg.values())
            html += f"<p style='margin-bottom:0.5rem;font-size:1.1rem;'><strong>{mode.title()} page size:</strong> {trq} files totaling {tkb/1024:.1f} MB.</p>"
            
            html += f'<details><summary class="details-btn">View {mode.title()} Raw Assets</summary>'
            html += '<div class="table-wrapper" style="margin-top:0.5rem; margin-bottom:1.5rem;"><table><thead><tr><th>Type</th><th>Requests</th><th>Size</th><th>Avg ms</th></tr></thead><tbody>'
            for rtype, rdata in sorted(rg.items(), key=lambda x: -x[1].get("total_size_kb", 0)):
                html += f"<tr><td>{rtype}</td><td>{rdata['count']}</td><td>{rdata['total_size_kb']:.1f} KB</td><td>{rdata.get('avg_duration_ms',0):.0f} ms</td></tr>"
            html += "</tbody></table></div></details>"
        return html


    def generate(
        self,
        site_name: str,
        site_url: str,
        results: dict,
        output_path: Path,
        duration_seconds: float = 0,
    ) -> None:
        
        # Primary grade is Authenticated if exists, else Anonymous
        main_mode = "authenticated" if "authenticated" in results else "anonymous"
        r_main = results[main_mode]
        eval_dict = r_main["evaluation"]
        grade = r_main["grade"]
        
        passes = sum(1 for v in eval_dict.values() if v["verdict"] == "PASS")
        warns = sum(1 for v in eval_dict.values() if v["verdict"] == "WARN")
        fails = sum(1 for v in eval_dict.values() if v["verdict"] == "FAIL")

        grade_col = self._grade_color(grade)
        grade_shadow = self._grade_shadow(grade)
        ts = datetime.now().strftime("%B %d, %Y at %I:%M %p")

        # Auth Cost Math
        # "auth_overhead_cost = authenticated.load_time - anonymous.load_time"
        overhead_ms = 0.0
        auth_speed = r_main.get("auth_speed", 0)
        has_overhead = False

        if "authenticated" in results and "anonymous" in results:
            auth_bp = results["authenticated"].get("baseline_stats", {}).get("load_time", {}).get("p50", 0)
            anon_bp = results["anonymous"].get("baseline_stats", {}).get("load_time", {}).get("p50", 0)
            overhead_ms = auth_bp - anon_bp
            has_overhead = True

        overhead_html = ""
        if main_mode == "authenticated":
            # Display Auth Setup
            overhead_html += f"""
            <div class="auth-overhead-card">
              <div class="auth-stat-label">Authentication Engine</div>
              <div class="auth-stat-value" style="color: #60A5FA;">{auth_speed:.0f}ms</div>
              <div style="font-size:0.8rem; color:var(--text-muted); margin-bottom: 1rem;">Credential sumbit to redirect</div>
            """
            if has_overhead:
                overhead_col = "#EF4444" if overhead_ms > 1000 else "#F59E0B" if overhead_ms > 0 else "#10B981"
                overhead_html += f"""
                  <div class="auth-stat-label">Auth Overhead Cost (Per Req)</div>
                  <div class="auth-stat-value" style="color: {overhead_col};">+{overhead_ms:.0f}ms</div>
                  <div style="font-size:0.8rem; color:var(--text-muted);">CDN Public vs Authenticated Delta</div>
                """
            overhead_html += "</div>"
            

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
      <div class="sc-left">
        <div class="grade-badge">{grade}</div>
        <div class="score-stats">
          <strong>Overall Health</strong><br>
          <div style="margin-top:0.5rem">
            <span class="stat-pill" style="background:{self._verdict_gradient('PASS')}">{passes} Passed</span>
            <span class="stat-pill" style="background:{self._verdict_gradient('WARN')}">{warns} Warnings</span>
            <span class="stat-pill" style="background:{self._verdict_gradient('FAIL')}">{fails} Failed</span>
          </div>
          <div style="font-size:0.9rem; margin-top:0.5rem">Scored against {passes+warns+fails} thresholds.</div>
        </div>
      </div>
      {overhead_html}
    </div>
  </section>

  <h2>User Experience Metrics</h2>
  <section class="card">
    {self._metric_cards_html(results)}
  </section>

  <h2>Performance Under Normal Traffic</h2>
  <section class="card">
    {self._baseline_table_html(results)}
  </section>

  <h2>Performance on Slow Internet (Mobile)</h2>
  <section class="card">
    {self._network_stress_html(results)}
  </section>

  <h2>User Capacity (Crash Test)</h2>
  <section class="card">
    {self._breakpoint_html(results)}
  </section>

  <h2>Page Size & Heavy Assets</h2>
  <section class="card">
    {self._resource_html(results)}
  </section>

</div>
<script>
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

def generate_report(**kwargs) -> None:
    HTMLReporter().generate(**kwargs)
