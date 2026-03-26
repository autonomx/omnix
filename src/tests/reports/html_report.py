"""
Custom HTML Report Generator for Omnix Playwright Tests.

Generates a professional, visually rich HTML test report with:
- Executive summary with pass/fail/skip metrics
- Animated donut chart for pass rate
- Per-suite collapsible sections with individual test details
- Failure screenshots (inline base64)
- Timing data per test
- Search and filter functionality
"""

from __future__ import annotations

import base64
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Report data collector (pytest plugin)
# ---------------------------------------------------------------------------


class OmnixReportPlugin:
    """Pytest plugin that collects test results and generates the HTML report."""

    def __init__(self, report_dir: Path) -> None:
        self.report_dir = report_dir
        self.results: list[dict] = []
        self.suite_start: float = 0.0
        self.suite_end: float = 0.0

    # -- hooks ---------------------------------------------------------------

    def pytest_sessionstart(self, session):
        self.suite_start = time.time()

    def pytest_runtest_logreport(self, report):
        if report.when != "call":
            return

        result = {
            "name": report.nodeid,
            "short_name": report.nodeid.split("::")[-1],
            "suite": _suite_from_nodeid(report.nodeid),
            "outcome": report.outcome,  # "passed" / "failed" / "skipped"
            "duration": round(report.duration, 3),
            "message": "",
            "screenshot": None,
        }

        if report.failed:
            result["message"] = str(report.longrepr) if report.longrepr else ""

        # Grab screenshot path attached by conftest hook
        for key, value in report.user_properties:
            if key == "screenshot":
                result["screenshot"] = value

        self.results.append(result)

    def pytest_sessionfinish(self, session, exitstatus):
        self.suite_end = time.time()
        self._generate_report()

    # -- report generation ---------------------------------------------------

    def _generate_report(self) -> None:
        self.report_dir.mkdir(parents=True, exist_ok=True)

        passed = sum(1 for r in self.results if r["outcome"] == "passed")
        failed = sum(1 for r in self.results if r["outcome"] == "failed")
        skipped = sum(1 for r in self.results if r["outcome"] == "skipped")
        total = len(self.results)
        duration = round(self.suite_end - self.suite_start, 2)
        pass_rate = round((passed / total) * 100, 1) if total else 0
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Group by suite
        suites: dict[str, list[dict]] = {}
        for r in self.results:
            suites.setdefault(r["suite"], []).append(r)

        suite_html = self._render_suites(suites)

        html = _REPORT_TEMPLATE.format(
            timestamp=timestamp,
            total=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            duration=duration,
            pass_rate=pass_rate,
            pass_rate_deg=round(pass_rate * 3.6, 1),
            suite_sections=suite_html,
            results_json=json.dumps(self.results, default=str),
        )

        report_path = self.report_dir / "report.html"
        report_path.write_text(html, encoding="utf-8")

    def _render_suites(self, suites: dict[str, list[dict]]) -> str:
        parts = []
        for suite_name, tests in suites.items():
            s_passed = sum(1 for t in tests if t["outcome"] == "passed")
            s_failed = sum(1 for t in tests if t["outcome"] == "failed")
            s_skipped = sum(1 for t in tests if t["outcome"] == "skipped")
            s_total = len(tests)
            status_class = "suite-pass" if s_failed == 0 else "suite-fail"

            rows = []
            for t in tests:
                badge = _outcome_badge(t["outcome"])
                screenshot_html = ""
                if t["screenshot"] and os.path.isfile(t["screenshot"]):
                    try:
                        img_data = Path(t["screenshot"]).read_bytes()
                        b64 = base64.b64encode(img_data).decode()
                        screenshot_html = (
                            f'<details class="screenshot"><summary>📷 Screenshot</summary>'
                            f'<img src="data:image/png;base64,{b64}" alt="failure screenshot"/>'
                            f"</details>"
                        )
                    except Exception:
                        pass

                error_html = ""
                if t["message"]:
                    safe_msg = (
                        t["message"]
                        .replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                    )
                    error_html = f'<pre class="error-msg">{safe_msg}</pre>'

                rows.append(
                    f'<tr class="test-row {t["outcome"]}">'
                    f'<td class="test-name">{t["short_name"]}</td>'
                    f"<td>{badge}</td>"
                    f'<td class="dur">{t["duration"]}s</td>'
                    f"<td>{error_html}{screenshot_html}</td>"
                    f"</tr>"
                )

            parts.append(
                f'<div class="suite-card {status_class}">'
                f'<div class="suite-header" onclick="toggleSuite(this)">'
                f'<span class="suite-title">{suite_name}</span>'
                f'<span class="suite-stats">'
                f'<span class="badge pass">{s_passed} ✓</span>'
                f'<span class="badge fail">{s_failed} ✗</span>'
                f'<span class="badge skip">{s_skipped} ⊘</span>'
                f'<span class="badge total">{s_total} total</span>'
                f"</span>"
                f'<span class="chevron">▸</span>'
                f"</div>"
                f'<div class="suite-body" style="display:none">'
                f'<table class="test-table"><tbody>'
                + "\n".join(rows)
                + "</tbody></table>"
                f"</div></div>"
            )
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _suite_from_nodeid(nodeid: str) -> str:
    """Extract a human-readable suite name from a pytest nodeid."""
    parts = nodeid.split("::")
    # tests/e2e/test_foo.py::TestBar::test_baz  →  TestBar
    if len(parts) >= 2:
        return parts[-2]
    return parts[0]


def _outcome_badge(outcome: str) -> str:
    icons = {"passed": "✓ PASS", "failed": "✗ FAIL", "skipped": "⊘ SKIP"}
    return f'<span class="badge {outcome}">{icons.get(outcome, outcome)}</span>'


# ---------------------------------------------------------------------------
# pytest plugin hook: register automatically when conftest imports us
# ---------------------------------------------------------------------------


def pytest_configure(config):
    report_dir = Path(config.rootdir) / "reports"
    plugin = OmnixReportPlugin(report_dir)
    config.pluginmanager.register(plugin, "omnix_report")


# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------

_REPORT_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Omnix Test Report</title>
<style>
:root {{
  --bg: #0f0f1a;
  --card: #181828;
  --border: #2a2a40;
  --text: #e0e0f0;
  --muted: #8888aa;
  --pass: #10b981;
  --fail: #ef4444;
  --skip: #f59e0b;
  --accent: #7c3aed;
  --accent2: #a78bfa;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
}}
.container {{ max-width: 1200px; margin: 0 auto; padding: 2rem 1.5rem; }}

/* Header */
.report-header {{
  text-align: center;
  padding: 3rem 0 2rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 2rem;
}}
.report-header h1 {{
  font-size: 2.4rem;
  font-weight: 700;
  background: linear-gradient(135deg, var(--accent), var(--accent2));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 0.5rem;
}}
.report-header .timestamp {{
  color: var(--muted);
  font-size: 0.9rem;
}}

/* Summary cards */
.summary {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}}
.summary-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1.5rem;
  text-align: center;
  transition: transform 0.2s;
}}
.summary-card:hover {{ transform: translateY(-2px); }}
.summary-card .value {{
  font-size: 2.5rem;
  font-weight: 700;
  display: block;
}}
.summary-card .label {{
  color: var(--muted);
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}
.summary-card.passed .value {{ color: var(--pass); }}
.summary-card.failed .value {{ color: var(--fail); }}
.summary-card.skipped .value {{ color: var(--skip); }}
.summary-card.total .value {{ color: var(--accent2); }}
.summary-card.duration .value {{ color: var(--text); font-size: 1.8rem; }}

/* Donut chart */
.donut-wrap {{
  display: flex;
  justify-content: center;
  margin-bottom: 2rem;
}}
.donut {{
  width: 180px; height: 180px;
  border-radius: 50%;
  background: conic-gradient(
    var(--pass) 0deg {pass_rate_deg}deg,
    var(--fail) {pass_rate_deg}deg 360deg
  );
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}}
.donut::after {{
  content: '{pass_rate}%';
  width: 130px; height: 130px;
  background: var(--bg);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--pass);
}}

/* Filter bar */
.filter-bar {{
  display: flex;
  gap: 0.75rem;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
  align-items: center;
}}
.filter-bar input {{
  flex: 1;
  min-width: 200px;
  padding: 0.6rem 1rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text);
  font-size: 0.95rem;
}}
.filter-bar input::placeholder {{ color: var(--muted); }}
.filter-btn {{
  padding: 0.6rem 1.2rem;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--text);
  cursor: pointer;
  font-size: 0.85rem;
  transition: background 0.15s;
}}
.filter-btn:hover, .filter-btn.active {{
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}}

/* Suite cards */
.suite-card {{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  margin-bottom: 1rem;
  overflow: hidden;
}}
.suite-card.suite-fail {{ border-left: 4px solid var(--fail); }}
.suite-card.suite-pass {{ border-left: 4px solid var(--pass); }}
.suite-header {{
  padding: 1rem 1.5rem;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  user-select: none;
}}
.suite-header:hover {{ background: rgba(124,58,237,0.05); }}
.suite-title {{ font-weight: 600; font-size: 1.05rem; }}
.suite-stats {{ display: flex; gap: 0.5rem; align-items: center; }}
.chevron {{
  transition: transform 0.2s;
  color: var(--muted);
  font-size: 1.2rem;
}}
.suite-card.open .chevron {{ transform: rotate(90deg); }}
.suite-body {{ padding: 0 1rem 1rem; }}

/* Test table */
.test-table {{ width: 100%; border-collapse: collapse; }}
.test-table td {{ padding: 0.6rem 0.8rem; border-top: 1px solid var(--border); vertical-align: top; }}
.test-name {{ font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 0.9rem; }}
.dur {{ color: var(--muted); font-size: 0.85rem; white-space: nowrap; }}

/* Badges */
.badge {{
  display: inline-block;
  padding: 0.15rem 0.6rem;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.03em;
}}
.badge.passed, .badge.pass {{ background: rgba(16,185,129,0.15); color: var(--pass); }}
.badge.failed, .badge.fail {{ background: rgba(239,68,68,0.15); color: var(--fail); }}
.badge.skipped, .badge.skip {{ background: rgba(245,158,11,0.15); color: var(--skip); }}
.badge.total {{ background: rgba(124,58,237,0.15); color: var(--accent2); }}

/* Error messages */
.error-msg {{
  background: rgba(239,68,68,0.08);
  border: 1px solid rgba(239,68,68,0.2);
  border-radius: 6px;
  padding: 0.6rem;
  font-size: 0.8rem;
  color: #fca5a5;
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  margin-top: 0.4rem;
}}

/* Screenshots */
.screenshot summary {{
  cursor: pointer;
  color: var(--accent2);
  font-size: 0.85rem;
  margin-top: 0.4rem;
}}
.screenshot img {{
  max-width: 100%;
  border-radius: 6px;
  margin-top: 0.5rem;
  border: 1px solid var(--border);
}}

/* Footer */
.report-footer {{
  text-align: center;
  padding: 2rem 0 1rem;
  color: var(--muted);
  font-size: 0.8rem;
  border-top: 1px solid var(--border);
  margin-top: 2rem;
}}
</style>
</head>
<body>
<div class="container">

  <div class="report-header">
    <h1>🧪 Omnix Test Report</h1>
    <p class="timestamp">Generated {timestamp}</p>
  </div>

  <div class="summary">
    <div class="summary-card total">
      <span class="value">{total}</span>
      <span class="label">Total Tests</span>
    </div>
    <div class="summary-card passed">
      <span class="value">{passed}</span>
      <span class="label">Passed</span>
    </div>
    <div class="summary-card failed">
      <span class="value">{failed}</span>
      <span class="label">Failed</span>
    </div>
    <div class="summary-card skipped">
      <span class="value">{skipped}</span>
      <span class="label">Skipped</span>
    </div>
    <div class="summary-card duration">
      <span class="value">{duration}s</span>
      <span class="label">Duration</span>
    </div>
  </div>

  <div class="donut-wrap"><div class="donut"></div></div>

  <div class="filter-bar">
    <input type="text" id="searchInput" placeholder="🔍  Search tests..." oninput="filterTests()"/>
    <button class="filter-btn active" data-filter="all" onclick="setFilter(this)">All</button>
    <button class="filter-btn" data-filter="passed" onclick="setFilter(this)">✓ Passed</button>
    <button class="filter-btn" data-filter="failed" onclick="setFilter(this)">✗ Failed</button>
    <button class="filter-btn" data-filter="skipped" onclick="setFilter(this)">⊘ Skipped</button>
  </div>

  <div id="suiteContainer">
    {suite_sections}
  </div>

  <div class="report-footer">
    Omnix Playwright Testing Framework &bull; Powered by pytest + Playwright Python
  </div>

</div>

<script>
function toggleSuite(header) {{
  const card = header.parentElement;
  const body = card.querySelector('.suite-body');
  const isOpen = card.classList.toggle('open');
  body.style.display = isOpen ? 'block' : 'none';
}}

function setFilter(btn) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  filterTests();
}}

function filterTests() {{
  const search = document.getElementById('searchInput').value.toLowerCase();
  const activeBtn = document.querySelector('.filter-btn.active');
  const filter = activeBtn ? activeBtn.dataset.filter : 'all';

  document.querySelectorAll('.test-row').forEach(row => {{
    const name = row.querySelector('.test-name').textContent.toLowerCase();
    const matchesSearch = !search || name.includes(search);
    const matchesFilter = filter === 'all' || row.classList.contains(filter);
    row.style.display = matchesSearch && matchesFilter ? '' : 'none';
  }});

  // Hide empty suites
  document.querySelectorAll('.suite-card').forEach(card => {{
    const visibleRows = card.querySelectorAll('.test-row:not([style*="display: none"])');
    card.style.display = visibleRows.length > 0 ? '' : 'none';
  }});
}}

// Auto-expand suites with failures
document.querySelectorAll('.suite-card.suite-fail').forEach(card => {{
  card.classList.add('open');
  card.querySelector('.suite-body').style.display = 'block';
}});
</script>
</body>
</html>
"""
