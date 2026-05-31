from __future__ import annotations


HTML_REPORT_CSS = r"""
:root {
  color-scheme: dark;
  --bg: #0f1117;
  --panel: #171a23;
  --panel2: #202431;
  --panel3: #11141c;
  --text: #e7eaf0;
  --muted: #a9b0bf;
  --border: #343a4a;
  --pass: #38a169;
  --warn: #d69e2e;
  --fail: #e53e3e;
  --info: #4299e1;
  --code: #0b0d12;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
a { color: #8cc8ff; text-decoration: none; }
a:hover { text-decoration: underline; }
.page {
  max-width: 1600px;
  margin: 0 auto;
  padding: 24px;
}
.header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  border-bottom: 1px solid var(--border);
  padding-bottom: 16px;
  margin-bottom: 20px;
}
.card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  margin: 12px 0;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
.badge {
  display: inline-block;
  border-radius: 999px;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 700;
  margin-right: 6px;
  white-space: nowrap;
}
.badge.pass { background: rgba(56,161,105,.18); color: #8ff0b3; }
.badge.warn { background: rgba(214,158,46,.18); color: #ffd37a; }
.badge.fail { background: rgba(229,62,62,.18); color: #ff9a9a; }
.badge.info { background: rgba(66,153,225,.18); color: #9dd2ff; }
.badge.muted { background: rgba(169,176,191,.14); color: var(--muted); }
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin: 12px 0;
}
input[type="search"] {
  background: var(--panel2);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 9px 12px;
  min-width: 320px;
}
button {
  background: var(--panel2);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 10px;
  cursor: pointer;
}
button:hover { background: #2b3142; }
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--panel);
}
th, td {
  border-bottom: 1px solid var(--border);
  padding: 8px 10px;
  text-align: left;
  vertical-align: top;
}
th {
  background: var(--panel2);
  color: var(--muted);
  position: sticky;
  top: 0;
  z-index: 2;
}
tr.hidden { display: none; }
pre {
  background: var(--code);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
  max-height: 720px;
}
code { color: #d8e2ff; }
details {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  margin: 10px 0;
}
summary {
  cursor: pointer;
  padding: 10px 12px;
  font-weight: 700;
}
details > div {
  padding: 0 12px 12px;
}
.warning { border-left: 4px solid var(--warn); }
.error { border-left: 4px solid var(--fail); }
.turn { border-left: 4px solid var(--info); }
.small {
  color: var(--muted);
  font-size: 12px;
}
.kv {
  display: grid;
  grid-template-columns: minmax(180px, 260px) 1fr;
  gap: 8px;
}
.kv div:nth-child(odd) { color: var(--muted); }
.panel-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.json-wrap { position: relative; }
.copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  font-size: 12px;
}
.pill-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
hr {
  border: none;
  border-top: 1px solid var(--border);
  margin: 16px 0;
}
.chat-transcript {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.chat-turn {
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--panel3);
  padding: 14px;
}
.chat-turn-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--muted);
  font-size: 12px;
  margin-bottom: 10px;
}
.chat-row {
  display: grid;
  grid-template-columns: 130px 1fr;
  gap: 12px;
  margin: 8px 0;
}
.chat-label {
  color: var(--muted);
  font-weight: 700;
}
.chat-bubble {
  border-radius: 12px;
  padding: 10px 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  white-space: pre-wrap;
}
.chat-bubble.player {
  background: rgba(66,153,225,.12);
  border-color: rgba(66,153,225,.35);
}
.chat-bubble.ai {
  background: rgba(56,161,105,.10);
  border-color: rgba(56,161,105,.30);
}
.chat-bubble.npc {
  background: rgba(214,158,46,.10);
  border-color: rgba(214,158,46,.30);
}
.chat-action {
  color: var(--muted);
  font-size: 12px;
}
th.sortable {
  cursor: pointer;
  user-select: none;
}
th.sortable:hover {
  background: #2b3142;
}
.sort-indicator {
  color: var(--muted);
  font-size: 11px;
  margin-left: 6px;
}
th.sort-asc,
th.sort-desc {
  color: var(--text);
}
"""


HTML_REPORT_JS = r"""
let sortState = { key: "", direction: "asc" };

function sortScenarioTable(key, type = "text") {
  const table = document.getElementById("scenarioTable");
  if (!table) return;

  const tbody = table.querySelector("tbody");
  const rows = Array.from(tbody.querySelectorAll("[data-scenario-row]"));

  const direction =
    sortState.key === key && sortState.direction === "asc" ? "desc" : "asc";

  sortState = { key, direction };

  rows.sort((a, b) => {
    let av = a.getAttribute(`data-${key}`) || "";
    let bv = b.getAttribute(`data-${key}`) || "";

    if (type === "number") {
      av = Number(av || 0);
      bv = Number(bv || 0);
      return direction === "asc" ? av - bv : bv - av;
    }

    if (type === "status") {
      const rank = { fail: 0, warn: 1, pass: 2 };
      av = rank[av] ?? 99;
      bv = rank[bv] ?? 99;
      return direction === "asc" ? av - bv : bv - av;
    }

    av = String(av).toLowerCase();
    bv = String(bv).toLowerCase();
    return direction === "asc"
      ? av.localeCompare(bv)
      : bv.localeCompare(av);
  });

  rows.forEach(row => tbody.appendChild(row));

  document.querySelectorAll("[data-sort-key]").forEach(th => {
    th.classList.remove("sort-asc", "sort-desc");
    const label = th.querySelector(".sort-indicator");
    if (label) label.textContent = "";
  });

  const active = document.querySelector(`[data-sort-key="${key}"]`);
  if (active) {
    active.classList.add(direction === "asc" ? "sort-asc" : "sort-desc");
    const label = active.querySelector(".sort-indicator");
    if (label) label.textContent = direction === "asc" ? "▲" : "▼";
  }

  applySearch();
}
function setFilter(status) {
  const q = (document.getElementById('scenarioSearch')?.value || '').toLowerCase();
  document.querySelectorAll('[data-scenario-row]').forEach(row => {
    const rowStatus = row.getAttribute('data-status');
    const text = row.innerText.toLowerCase();
    const statusMatch = status === 'all' || rowStatus === status;
    const textMatch = !q || text.includes(q);
    row.classList.toggle('hidden', !(statusMatch && textMatch));
  });
}
function applySearch() {
  const active = document.querySelector('[data-filter].active')?.getAttribute('data-filter') || 'all';
  setFilter(active);
}
function activateFilter(btn, status) {
  document.querySelectorAll('[data-filter]').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  setFilter(status);
}
function toggleAllDetails(open) {
  document.querySelectorAll('details').forEach(d => d.open = open);
}
async function copyText(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const text = el.innerText;
  try {
    await navigator.clipboard.writeText(text);
  } catch (err) {
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
}
"""
