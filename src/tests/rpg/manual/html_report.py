from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from tests.rpg.manual.constants import (
    MANUAL_HTML_DIR_NAME,
    MANUAL_HTML_JSON_PREVIEW_CHARS,
    MANUAL_HTML_SCENARIO_DIR_NAME,
)
from tests.rpg.manual.extractors.base import (
    _extract_simulation_state,
    _extract_turn_contract,
    _extract_visible_interaction_reason,
    _first_dict,
)
from tests.rpg.manual.safe import _safe_dict, _safe_list, _safe_str

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


def _html_escape(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _json_pretty(value: Any, *, max_chars: int = MANUAL_HTML_JSON_PREVIEW_CHARS) -> str:
    try:
        text = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)
    except Exception:
        text = str(value)
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n... [truncated in HTML; see text chunks]"
    return text


def _status_for_warnings(warnings: List[str], error: str = "") -> str:
    if error:
        return "fail"
    if warnings:
        return "warn"
    return "pass"


def _badge(label: Any, status: str = "info") -> str:
    status = _safe_str(status or "info").lower()
    if status not in {"pass", "warn", "fail", "info", "muted"}:
        status = "info"
    return f'<span class="badge {status}">{_html_escape(label)}</span>'


def _status_for_summary(summary: Dict[str, Any]) -> str:
    if _safe_str(summary.get("error")):
        return "fail"
    if _safe_list(summary.get("regression_warnings")) or _safe_list(summary.get("scenario_warnings")):
        return "warn"
    return "pass"


def _rel_link(from_dir: Path, target: Any) -> str:
    try:
        target_path = Path(str(target))
        return str(target_path.relative_to(from_dir)).replace("\\", "/")
    except Exception:
        return str(target).replace("\\", "/")


def _extract_display_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in (
            "text",
            "content",
            "narration",
            "message",
            "line",
            "summary",
            "display_text",
        ):
            text = _safe_str(value.get(key)).strip()
            if text:
                return text
    return ""


def _extract_player_text(turn: Dict[str, Any], result: Dict[str, Any]) -> str:
    return (
        _safe_str(turn.get("player")).strip()
        or _safe_str(turn.get("input")).strip()
        or _safe_str(turn.get("player_input")).strip()
        or _safe_str(result.get("player_input")).strip()
        or _safe_str(result.get("input")).strip()
    )


def _extract_ai_narration_text(result: Dict[str, Any]) -> str:
    result = _safe_dict(result)
    nested_result = _safe_dict(result.get("result"))
    turn_contract = _safe_dict(result.get("turn_contract"))
    resolved = _first_dict(
        result.get("resolved_result"),
        nested_result.get("resolved_result"),
        turn_contract.get("resolved_result"),
        turn_contract.get("resolved_action"),
    )
    combat_payload = _safe_dict(result.get("combat_narration_payload"))
    nested_combat_payload = _safe_dict(nested_result.get("combat_narration_payload"))
    resolved_combat_payload = _safe_dict(resolved.get("combat_narration_payload"))
    contract_combat_payload = _safe_dict(turn_contract.get("combat_narration_payload"))

    candidates = [
        combat_payload.get("narration"),
        nested_combat_payload.get("narration"),
        resolved_combat_payload.get("narration"),
        contract_combat_payload.get("narration"),
        result.get("final_narration"),
        result.get("narration"),
        result.get("narration_preview"),
        nested_result.get("final_narration"),
        nested_result.get("narration"),
        nested_result.get("narration_preview"),
        resolved.get("final_narration"),
        resolved.get("narration"),
        resolved.get("narration_preview"),
        # keep the existing candidates below this line
        resolved.get("narrative"),
        resolved.get("description"),
        resolved.get("text"),
    ]

    for candidate in candidates:
        text = _extract_display_text(candidate)
        if text:
            text = _patch_visible_interaction_reason_in_text(text, result)
            return text

    # Structured narration contract variants.
    for container in (result, nested_result, turn_contract, resolved):
        container = _safe_dict(container)
        narration_obj = _safe_dict(
            container.get("narration_result")
            or container.get("presentation")
            or container.get("narration_contract")
        )
        text = _extract_display_text(narration_obj.get("narration") or narration_obj)
        if text:
            text = _patch_visible_interaction_reason_in_text(text, result)
            return text

    return ""


def _patch_visible_interaction_reason_in_text(text: Any, result: Dict[str, Any]) -> str:
    text = _safe_str(text)
    visible_reason = _extract_visible_interaction_reason(result)
    if not visible_reason:
        return text

    if not text.strip():
        return f"Result: {visible_reason}"

    text = re.sub(
        r"(?im)^(\s*Result:\s*)(unknown_item|item_not_found|unknown)\s*$",
        rf"\1{visible_reason}",
        text,
    )
    text = re.sub(
        r"(?i)Result:\s*(unknown_item|item_not_found|unknown)",
        f"Result: {visible_reason}",
        text,
    )
    return text


def _extract_npc_dialogue_lines(result: Dict[str, Any]) -> List[Dict[str, str]]:
    result = _safe_dict(result)
    nested_result = _safe_dict(result.get("result"))
    turn_contract = _safe_dict(result.get("turn_contract"))
    conversation = _first_dict(
        result.get("conversation_result"),
        nested_result.get("conversation_result"),
        turn_contract.get("conversation_result"),
        _safe_dict(turn_contract.get("resolved_result")).get("conversation_result"),
    )

    lines: List[Dict[str, str]] = []

    # Prefer explicit NPC response beat.
    npc_response = _safe_dict(conversation.get("npc_response_beat"))
    if npc_response:
        line = _safe_str(npc_response.get("line")).strip()
        if line:
            lines.append(
                {
                    "speaker": _safe_str(npc_response.get("speaker_name") or npc_response.get("speaker_id") or "NPC"),
                    "speaker_id": _safe_str(npc_response.get("speaker_id")),
                    "line": line,
                    "kind": "npc_response",
                }
            )

    # Include current beat if it is an NPC speaking.
    beat = _safe_dict(conversation.get("beat"))
    if beat:
        speaker_id = _safe_str(beat.get("speaker_id"))
        line = _safe_str(beat.get("line")).strip()
        if line and speaker_id != "player":
            item = {
                "speaker": _safe_str(beat.get("speaker_name") or speaker_id or "NPC"),
                "speaker_id": speaker_id,
                "line": line,
                "kind": "conversation_beat",
            }
            if item not in lines:
                lines.append(item)

    # Include the latest thread beats for context, bounded.
    thread = _safe_dict(conversation.get("thread"))
    for beat in _safe_list(thread.get("beats"))[-4:]:
        beat = _safe_dict(beat)
        speaker_id = _safe_str(beat.get("speaker_id"))
        line = _safe_str(beat.get("line")).strip()
        if not line or speaker_id == "player":
            continue
        item = {
            "speaker": _safe_str(beat.get("speaker_name") or speaker_id or "NPC"),
            "speaker_id": speaker_id,
            "line": line,
            "kind": "thread_beat",
        }
        if item not in lines:
            lines.append(item)

    return lines[:6]


def _extract_action_summary(result: Dict[str, Any]) -> str:
    result = _safe_dict(result)
    nested_result = _safe_dict(result.get("result"))
    turn_contract = _safe_dict(result.get("turn_contract"))
    resolved = _first_dict(
        result.get("resolved_result"),
        nested_result.get("resolved_result"),
        turn_contract.get("resolved_result"),
        turn_contract.get("resolved_action"),
    )
    conversation = _first_dict(
        result.get("conversation_result"),
        nested_result.get("conversation_result"),
        turn_contract.get("conversation_result"),
        resolved.get("conversation_result"),
    )
    service_result = _first_dict(resolved.get("service_result"), result.get("service_result"))

    action_type = (
        _safe_str(resolved.get("action_type"))
        or _safe_str(resolved.get("semantic_action_type"))
        or _safe_str(result.get("action_type"))
    )

    bits = []
    if action_type:
        bits.append(f"action_type={action_type}")
    if conversation:
        reason = _safe_str(conversation.get("reason"))
        mode = _safe_str(conversation.get("participation_mode"))
        if reason:
            bits.append(f"conversation={reason}")
        if mode:
            bits.append(f"mode={mode}")
    if service_result:
        kind = _safe_str(service_result.get("kind"))
        status = _safe_str(service_result.get("status"))
        if kind or status:
            bits.append(f"service={kind or 'service'}:{status or 'unknown'}")

    return " | ".join(bits)


def _html_json_block(value: Any, *, block_id: str, title: str = "JSON", open_by_default: bool = False) -> str:
    open_attr = " open" if open_by_default else ""
    pretty = _html_escape(_json_pretty(value))
    return f"""
<details{open_attr}>
  <summary>{_html_escape(title)}</summary>
  <div class="json-wrap">
    <button class="copy-btn" onclick="copyText('{_html_escape(block_id)}')">Copy</button>
    <pre><code id="{_html_escape(block_id)}">{pretty}</code></pre>
  </div>
</details>
"""


def _kv_panel(title: str, fields: Dict[str, Any], *, status: str = "info") -> str:
    rows = []
    for key, value in fields.items():
        if isinstance(value, (dict, list)):
            rendered = f"<pre><code>{_html_escape(_json_pretty(value, max_chars=12_000))}</code></pre>"
        else:
            rendered = _html_escape(value)
        rows.append(f"<div>{_html_escape(key)}</div><div>{rendered}</div>")
    return f"""
<div class="card">
  <div class="panel-title"><h3>{_html_escape(title)}</h3>{_badge(title, status)}</div>
  <div class="kv">{''.join(rows)}</div>
</div>
"""


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        value = _safe_dict(value)
        if value:
            return value
    return {}


def _first_list(*values: Any) -> List[Any]:
    for value in values:
        value = _safe_list(value)
        if value:
            return value
    return []


def _render_special_panels(result: Dict[str, Any], *, prefix: str) -> str:
    result = _safe_dict(result)
    nested_result = _safe_dict(result.get("result"))
    turn_contract = _safe_dict(result.get("turn_contract"))

    conversation = _first_dict(
        result.get("conversation_result"),
        nested_result.get("conversation_result"),
        turn_contract.get("conversation_result"),
        _safe_dict(turn_contract.get("resolved_result")).get("conversation_result"),
    )
    resolved = _first_dict(
        result.get("resolved_result"),
        nested_result.get("resolved_result"),
        turn_contract.get("resolved_result"),
        turn_contract.get("resolved_action"),
    )
    simulation_state = _first_dict(
        result.get("simulation_state"),
        nested_result.get("simulation_state"),
        turn_contract.get("simulation_state"),
        result.get("session", {}).get("simulation_state") if isinstance(result.get("session"), dict) else {},
    )

    npc_response = _safe_dict(conversation.get("npc_response_beat"))
    dialogue_profile = _first_dict(conversation.get("dialogue_profile"), npc_response.get("dialogue_profile"))
    topic_pivot = _safe_dict(conversation.get("topic_pivot"))
    director_intent = _first_dict(
        conversation.get("director_intent"),
        _safe_dict(simulation_state.get("conversation_director_state")).get("debug", {}).get("selected_intent"),
    )
    dialogue_recall = _first_dict(
        conversation.get("dialogue_recall"),
        npc_response.get("dialogue_recall"),
        dialogue_profile.get("dialogue_recall"),
    )

    panels = []

    if topic_pivot:
        panels.append(_kv_panel("Topic Pivot", {
            "requested": topic_pivot.get("requested"),
            "accepted": topic_pivot.get("accepted"),
            "requested_topic_hint": topic_pivot.get("requested_topic_hint"),
            "selected_topic_type": topic_pivot.get("selected_topic_type") or topic_pivot.get("topic_type"),
            "selected_topic_id": topic_pivot.get("selected_topic_id") or topic_pivot.get("topic_id"),
            "pivot_rejected_reason": topic_pivot.get("pivot_rejected_reason"),
        }, status="pass" if topic_pivot.get("accepted") else "info"))

    if director_intent:
        panels.append(_kv_panel("Director Intent", {
            "selected": director_intent.get("selected"),
            "speaker_id": director_intent.get("speaker_id"),
            "listener_id": director_intent.get("listener_id"),
            "topic_type": director_intent.get("topic_type"),
            "topic_id": director_intent.get("topic_id"),
            "reason": director_intent.get("reason"),
            "priority": director_intent.get("priority"),
        }, status="pass" if director_intent.get("selected") else "muted"))

    if dialogue_recall:
        panels.append(_kv_panel("Dialogue Recall", {
            "selected": dialogue_recall.get("selected"),
            "recall_requested": dialogue_recall.get("recall_requested"),
            "reason": dialogue_recall.get("reason"),
            "recalls": dialogue_recall.get("recalls"),
            "recalled_history_ids": conversation.get("recalled_history_ids") or npc_response.get("recalled_history_ids"),
            "recalled_knowledge_ids": conversation.get("recalled_knowledge_ids") or npc_response.get("recalled_knowledge_ids"),
        }, status="pass" if dialogue_recall.get("selected") else "muted"))

    for label, key in [
        ("Scene Population", "scene_population_state"),
        ("NPC Knowledge", "npc_knowledge_state"),
        ("NPC Reputation", "npc_reputation_state"),
        ("NPC Evolution", "npc_evolution_state"),
        ("Present NPCs", "present_npc_state"),
        ("Conversation Threads", "conversation_thread_state"),
        ("Scene Continuity", "scene_continuity_state"),
        ("Combat Result", "combat_result"),
        ("Combat State", "combat_state"),
        ("Companion Combat Result", "companion_combat_result"),
        ("Enemy Combat Result", "enemy_combat_result"),
        ("Combat Narration Contract", "combat_narration_contract"),
        ("Combat Narration Validation", "combat_narration_validation"),
        ("Conversation Director State", "conversation_director_state"),
        ("NPC Arc Continuity", "npc_arc_continuity_state"),
    ]:
        value = _first_dict(
            result.get(key),
            nested_result.get(key),
            conversation.get(key),
            simulation_state.get(key),
        )
        if value:
            panels.append(_html_json_block(value, block_id=f"{prefix}-{key}", title=label))

    if dialogue_profile:
        panels.append(_kv_panel("Dialogue Profile", {
            "npc_id": dialogue_profile.get("npc_id"),
            "name": dialogue_profile.get("name"),
            "role": dialogue_profile.get("role"),
            "response_intent": dialogue_profile.get("response_intent"),
            "reputation_response_style": dialogue_profile.get("reputation_response_style"),
            "used_fact_ids": dialogue_profile.get("used_fact_ids"),
            "known_facts": dialogue_profile.get("known_facts"),
        }, status="info"))

    service_result = _first_dict(resolved.get("service_result"), result.get("service_result"))
    if service_result:
        panels.append(_kv_panel("Service Result", {
            "matched": service_result.get("matched"),
            "kind": service_result.get("kind"),
            "status": service_result.get("status"),
            "reason": service_result.get("reason"),
        }, status="pass" if service_result.get("matched") else "muted"))

    quest_access = _first_dict(
        conversation.get("quest_conversation_access"),
        npc_response.get("quest_conversation_access"),
    )

    requested_access = _first_dict(
        conversation.get("requested_topic_access"),
        npc_response.get("requested_topic_access"),
    )
    if requested_access:
        panels.append(_kv_panel("Requested Topic Access", {
            "requested": requested_access.get("requested"),
            "accepted": requested_access.get("accepted"),
            "access": requested_access.get("access"),
            "reason": requested_access.get("reason"),
            "requested_topic_hint": requested_access.get("requested_topic_hint"),
            "safe_deflection": requested_access.get("safe_deflection"),
        }, status="pass" if requested_access.get("access") in {"backed", "partial", "normal", "trusted"} else "warn"))

    if quest_access:
        panels.append(_kv_panel("Quest Conversation Access", {
            "requested": quest_access.get("requested"),
            "access": quest_access.get("access"),
            "reason": quest_access.get("reason"),
            "allowed_detail_level": quest_access.get("allowed_detail_level"),
            "blocked_detail_level": quest_access.get("blocked_detail_level"),
            "npc_knows_topic": quest_access.get("npc_knows_topic"),
        }, status="pass" if quest_access.get("access") in {"partial", "normal", "trusted"} else "warn"))

    rep_consequence = _first_dict(
        conversation.get("player_reputation_consequence"),
        npc_response.get("player_reputation_consequence"),
    )
    if rep_consequence:
        panels.append(_html_json_block(
            rep_consequence,
            block_id=f"{prefix}-player-reputation-consequence",
            title="Player Reputation Consequence",
        ))

    quest_rumor = _first_dict(
        conversation.get("quest_rumor_result"),
        npc_response.get("quest_rumor_result"),
    )
    if quest_rumor:
        panels.append(_html_json_block(
            quest_rumor,
            block_id=f"{prefix}-quest-rumor-result",
            title="Quest Rumor Result",
        ))

    npc_referral = _first_dict(
        conversation.get("npc_referral"),
        npc_response.get("npc_referral"),
    )
    if npc_referral:
        panels.append(_html_json_block(
            npc_referral,
            block_id=f"{prefix}-npc-referral",
            title="NPC Referral",
        ))

    consequence_signal = _first_dict(
        conversation.get("consequence_signal_result"),
        npc_response.get("consequence_signal_result"),
    )
    if consequence_signal:
        panels.append(_html_json_block(
            consequence_signal,
            block_id=f"{prefix}-consequence-signal-result",
            title="Consequence Signal Result",
        ))

    for label, key in [
        ("Quest Rumor State", "quest_rumor_state"),
        ("Consequence Signal State", "consequence_signal_state"),
    ]:
        value = _first_dict(
            result.get(key),
            nested_result.get(key),
            conversation.get(key),
            simulation_state.get(key),
        )
        if value:
            panels.append(_html_json_block(value, block_id=f"{prefix}-{key}", title=label))

    evolution_result = _first_dict(
        conversation.get("npc_evolution_result"),
        npc_response.get("npc_evolution_result"),
    )
    if evolution_result:
        panels.append(_html_json_block(
            evolution_result,
            block_id=f"{prefix}-npc-evolution-result",
            title="NPC Evolution Result",
        ))

    for label, key in [
        ("NPC Arc Continuity", "npc_arc_continuity_state"),
    ]:
        value = _first_dict(
            result.get(key),
            nested_result.get(key),
            conversation.get(key),
            simulation_state.get(key),
        )
        if value:
            panels.append(_html_json_block(value, block_id=f"{prefix}-{key}", title=label))

    for label, key in [
        ("Party Join Eligibility", "party_join_eligibility_result"),
        ("Companion Join Intent", "companion_join_intent"),
        ("Companion Offer Record Result", "companion_offer_record_result"),
        ("Companion Acceptance Result", "companion_acceptance_result"),
        ("Companion Acceptance Debug", "companion_acceptance_debug"),
        ("Companion Dialogue Result", "companion_dialogue_result"),
        ("Companion Command Result", "companion_command_result"),
        ("Companion Memory Result", "companion_memory_result"),
        ("Companion Relationship Drift Result", "companion_relationship_drift_result"),
        ("Companion Loyalty Projection", "companion_loyalty_projection"),
        ("Companion Memory Summary", "companion_memory_summary"),
        ("Companion Quest Seed Result", "companion_quest_seed_result"),
        ("Companion Quest Progress Result", "companion_quest_progress_result"),
        ("Companion Quest Summary", "companion_quest_summary"),
        ("Companion Presence Summary", "companion_presence_summary"),
        ("Companion Presence Projection", "companion_presence_projection"),
        ("Party Composition Effects", "party_composition_effects"),
        ("Party Aware Turn Context", "party_aware_turn_context"),
        ("Direct Companion Turn Result", "direct_companion_turn_result"),
        ("Party State", "party_state"),
        ("NPC Arc Continuity Result", "npc_arc_continuity_result"),
        ("NPC Profile Summary", "npc_profile_summary"),
        ("NPC Profile Update Result", "npc_profile_update_result"),
        ("NPC Profile Draft Result", "npc_profile_draft_result"),
        ("NPC Profile Draft Approval Result", "npc_profile_draft_approval_result"),
        ("NPC Profile Draft Rejection Result", "npc_profile_draft_rejection_result"),
        ("NPC Profile Draft Summary", "npc_profile_draft_summary"),
        ("Character Cards Summary", "character_cards_summary"),
        ("Character Card Result", "character_card_result"),
        ("Character Card Update Result", "character_card_update_result"),
        ("Character Card Portrait Prompt Result", "character_card_portrait_prompt_result"),
        ("Semantic Action v2", "semantic_action_v2"),
        ("Interaction Result", "interaction_result"),
        ("General Interaction Result", "general_interaction_result"),
        ("Inventory Result", "inventory_result"),
        ("Container Result", "container_result"),
        ("Repair Result", "repair_result"),
        ("Consumable Result", "consumable_result"),
        ("Crafting Result", "crafting_result"),
        ("Loot Result", "loot_result"),
        ("Merchant Result", "merchant_result"),
        ("Ammo Result", "ammo_result"),
        ("Equipment Stats", "equipment_stats"),
        ("Companion Item Acceptance Result", "companion_item_acceptance_result"),
        ("Companion Auto Equip Result", "companion_auto_equip_result"),
    ]:
        value = _first_dict(
            result.get(key),
            nested_result.get(key),
            conversation.get(key),
            npc_response.get(key),
            simulation_state.get(key),
        )
        if value:
            panels.append(_html_json_block(value, block_id=f"{prefix}-{key}", title=label))

    return "".join(panels)


def _render_player_ai_conversation(turns: List[Dict[str, Any]]) -> str:
    rendered_turns = []

    for idx, turn in enumerate(turns, start=1):
        result = _safe_dict(turn.get("result") or turn)
        player_text = _extract_player_text(turn, result)
        narration_text = _extract_ai_narration_text(result)
        npc_lines = _extract_npc_dialogue_lines(result)
        action_summary = _extract_action_summary(result)

        npc_html = ""
        for npc_line in npc_lines:
            npc_html += f"""
            <div class="chat-row">
              <div class="chat-label">NPC {_html_escape(npc_line.get("speaker") or "")}</div>
              <div class="chat-bubble npc">{_html_escape(npc_line.get("line") or "")}</div>
            </div>
            """

        narration_text = _patch_visible_interaction_reason_in_text(narration_text, result)

        if not _safe_str(narration_text).strip():
            visible_reason = _extract_visible_interaction_reason(result)
            if visible_reason:
                narration_text = f"Result: {visible_reason}"

        if not narration_text and not npc_lines:
            narration_text = "[no AI/narration text found for this turn]"

        rendered_turns.append(
        f"""
            <div class="chat-turn" id="conversation-turn-{idx}">
              <div class="chat-turn-header">
                <span>Turn {idx}</span>
                <span>{_html_escape(action_summary)}</span>
              </div>

              <div class="chat-row">
                <div class="chat-label">Player</div>
                <div class="chat-bubble player">{_html_escape(player_text or "[no player text]")}</div>
              </div>

              <div class="chat-row">
                <div class="chat-label">AI / Narration</div>
                <div class="chat-bubble ai">{_html_escape(narration_text)}</div>
              </div>

              {npc_html}

              <div class="chat-action">{_html_escape(action_summary)}</div>
            </div>
            """
        )

    return f"""
    <div class="card">
      <div class="panel-title">
        <h2>Player ↔ AI Conversation</h2>
        {_badge("READABLE TRANSCRIPT", "info")}
      </div>
      <p class="small">
        Clean conversation view extracted from player input, narration, NPC response beats, and resolved turn metadata.
      </p>
      <div class="chat-transcript">
        {''.join(rendered_turns)}
      </div>
    </div>
    """


def _write_scenario_html_v2(
    *,
    output_dir: Path,
    scenario_name: str,
    scenario_summary: Dict[str, Any],
    turns: List[Dict[str, Any]],
    log_artifact: Dict[str, Any] | None = None,
) -> str:
    html_root = output_dir / MANUAL_HTML_DIR_NAME
    scenario_dir = html_root / MANUAL_HTML_SCENARIO_DIR_NAME
    scenario_dir.mkdir(parents=True, exist_ok=True)

    warnings = _safe_list(scenario_summary.get("regression_warnings")) + _safe_list(
        scenario_summary.get("scenario_warnings")
    )
    status = _status_for_summary(scenario_summary)

    warning_html = ""
    if warnings:
        warning_html = (
            '<div class="card warning"><h2>Warnings</h2><ul>'
            + "".join(f"<li>{_html_escape(w)}</li>" for w in warnings)
            + "</ul></div>"
        )

    artifact_html = ""
    if log_artifact:
        file_links = []
        for file_path in _safe_list(log_artifact.get("files"))[:300]:
            rel = str(file_path).replace("\\", "/")
            href = "../../" + rel
            file_links.append(
                f'<li><a href="{_html_escape(href)}">{_html_escape(Path(rel).name)}</a></li>'
            )

        artifact_html = f"""
<div class="card">
  <h2>Text/JSON Artifacts</h2>
  <div class="kv">
    <div>chunked</div><div>{_html_escape(log_artifact.get("chunked"))}</div>
    <div>total_bytes</div><div>{_html_escape(log_artifact.get("total_bytes"))}</div>
    <div>chunk_count</div><div>{_html_escape(log_artifact.get("chunk_count"))}</div>
  </div>
  <ul>{''.join(file_links)}</ul>
</div>
"""

    turn_html = []
    for idx, turn in enumerate(turns, start=1):
        result = _safe_dict(turn.get("result") or turn)
        player = (
            turn.get("player")
            or turn.get("input")
            or result.get("player_input")
            or result.get("input")
            or ""
        )

        nested_result = _safe_dict(result.get("result"))
        turn_contract = _safe_dict(result.get("turn_contract"))
        conversation = _first_dict(
            result.get("conversation_result"),
            nested_result.get("conversation_result"),
            turn_contract.get("conversation_result"),
            _safe_dict(turn_contract.get("resolved_result")).get("conversation_result"),
        )
        resolved = _first_dict(
            result.get("resolved_result"),
            nested_result.get("resolved_result"),
            turn_contract.get("resolved_result"),
            turn_contract.get("resolved_action"),
        )
        npc_response = _safe_dict(conversation.get("npc_response_beat"))

        action_type = (
            resolved.get("action_type")
            or resolved.get("semantic_action_type")
            or result.get("action_type")
            or ""
        )

        turn_status = "pass"
        if _safe_str(result.get("error")):
            turn_status = "fail"
        elif _safe_list(result.get("regression_warnings")) or _safe_list(result.get("scenario_warnings")):
            turn_status = "warn"

        block_id = f"{scenario_name}-turn-{idx}-raw".replace(":", "-").replace(" ", "-")

        turn_html.append(f"""
<details class="turn" id="turn-{idx}" open>
  <summary>
    Turn {idx}: {_html_escape(str(player)[:180])}
    {_badge(turn_status.upper(), turn_status)}
  </summary>
  <div>
    <div class="grid">
      <div class="card"><strong>Action Type</strong><br>{_html_escape(action_type)}</div>
      <div class="card"><strong>Conversation Reason</strong><br>{_html_escape(conversation.get("reason") or "")}</div>
      <div class="card"><strong>Participation</strong><br>{_html_escape(conversation.get("participation_mode") or "")}</div>
      <div class="card"><strong>Roleplay Source</strong><br>{_html_escape(npc_response.get("roleplay_source") or conversation.get("roleplay_source") or "")}</div>
    </div>

    <div class="card">
      <h3>Player</h3>
      <p>{_html_escape(player)}</p>
      <h3>NPC Response</h3>
      <p>{_html_escape(npc_response.get("line") or "")}</p>
    </div>

    {_render_special_panels(result, prefix=f"{scenario_name}-turn-{idx}".replace(":", "-").replace(" ", "-"))}

    {_html_json_block(result, block_id=block_id, title="Raw Turn JSON")}
  </div>
</details>
""")

    scenario_json_id = f"{scenario_name}-summary-json".replace(":", "-").replace(" ", "-")

    # Populate conversation preview for index
    first_turn = _safe_dict(turns[0]) if turns else {}
    first_result = _safe_dict(first_turn.get("result") or first_turn)
    scenario_summary["conversation_preview"] = (

        _extract_player_text(first_turn, first_result)
        or _extract_ai_narration_text(first_result)
        or ""
    )[:240]

    html_text = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{_html_escape(scenario_name)} — Manual RPG Scenario</title>
  <style>{HTML_REPORT_CSS}</style>
</head>
<body>
<script>{HTML_REPORT_JS}</script>
<div class="page">
  <div class="header">
    <div>
      <h1>{_html_escape(scenario_name)}</h1>
      <p class="small">Manual RPG transcript report</p>
    </div>
  </div>

  <div class="toolbar">
    <button onclick="toggleAllDetails(true)">Expand all</button>
    <button onclick="toggleAllDetails(false)">Collapse all</button>
  </div>

  <div class="grid">
    <div class="card"><strong>Turns</strong><br>{_html_escape(len(turns))}</div>
    <div class="card"><strong>Regression warnings</strong><br>{_html_escape(len(_safe_list(scenario_summary.get("regression_warnings"))))}</div>
    <div class="card"><strong>Scenario warnings</strong><br>{_html_escape(len(_safe_list(scenario_summary.get("scenario_warnings"))))}</div>
    <div class="card"><strong>Status</strong><br>{_badge(status.upper(), status)}</div>
  </div>

  {warning_html}
  {artifact_html}

  {_render_player_ai_conversation(turns)}

  <div class="card">
    <h2>Turn Navigation</h2>
    <div class="pill-list">
      {''.join(
        f'<a class="badge info" href="#conversation-turn-{i}">Chat {i}</a>'
        f'<a class="badge muted" href="#turn-{i}">Debug {i}</a>'
        for i in range(1, len(turns) + 1)
      )}
    </div>
  </div>

  {''.join(turn_html)}

  {_html_json_block(scenario_summary, block_id=scenario_json_id, title="Scenario Summary JSON")}
    </div>
</body>
</html>
"""

    if scenario_name == "inventory_consumables_ammo_equipment_stats":
        expected = "Result: ammo_consumed"
        if expected not in html_text:
            scenario_summary.setdefault("scenario_warnings", []).append(
                f"manual_ammo_command_html_expected_missing:{expected}"
            )
        if '<div class="chat-bubble ai"></div>' in html_text or '<p class="ai">AI: </p>' in html_text:
            scenario_summary.setdefault("scenario_warnings", []).append(
                "manual_ammo_command_html_empty_ai_text"
            )

    if scenario_name == "inventory_containers_durability_repair":
        stale_markers = [
            "Result: unknown_item",
            "Result: item_not_found",
        ]
        for marker in stale_markers:
            if marker in html_text:
                scenario_summary.setdefault("scenario_warnings", []).append(
                    f"visible_interaction_html_contains_stale_marker:{marker}"
                )

    path = scenario_dir / f"{scenario_name}.html"
    path.write_text(html_text, encoding="utf-8")
    return str(path)


def _write_html_index_v2(
    *,
    output_dir: Path,
    scenario_summaries: List[Dict[str, Any]],
    scenario_names_to_run: List[str],
) -> str:
    html_root = output_dir / MANUAL_HTML_DIR_NAME
    html_root.mkdir(parents=True, exist_ok=True)

    pass_count = warn_count = fail_count = 0
    rows = []

    for summary in scenario_summaries:
        name = _safe_str(
            summary.get("scenario")
            or summary.get("scenario_name")
            or summary.get("name")
            or "unknown"
        )
        status = _status_for_summary(summary)
        if status == "pass":
            pass_count += 1
        elif status == "warn":
            warn_count += 1
        else:
            fail_count += 1

        preview = _safe_str(summary.get("conversation_preview") or "")

        turn_count = len(_safe_list(summary.get("turns")))
        regression_count = len(_safe_list(summary.get("regression_warnings")))
        scenario_warning_count = len(_safe_list(summary.get("scenario_warnings")))
        error_text = _safe_str(summary.get("error"))[:240]
        preview = _safe_str(summary.get("conversation_preview") or "")[:240]

        rows.append(f"""
<tr
  data-scenario-row
  data-status="{_html_escape(status)}"
  data-name="{_html_escape(name)}"
  data-turns="{turn_count}"
  data-regression="{regression_count}"
  data-scenario-warnings="{scenario_warning_count}"
  data-error="{_html_escape(error_text)}"
  data-preview="{_html_escape(preview)}"
>
  <td>{_badge(status.upper(), status)}</td>
  <td><a href="scenarios/{_html_escape(name)}.html">{_html_escape(name)}</a></td>
  <td>{_html_escape(turn_count)}</td>
  <td>{_html_escape(regression_count)}</td>
  <td>{_html_escape(scenario_warning_count)}</td>
  <td>{_html_escape(preview)}</td>
  <td>{_html_escape(error_text)}</td>
</tr>
""")

    scenario_label = f"{len(scenario_summaries)} scenarios"
    html_text = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Manual RPG Test Report — {scenario_label}</title>
  <style>{HTML_REPORT_CSS}</style>
</head>
<body>
<script>{HTML_REPORT_JS}</script>
<div class="page">
  <div class="header">
    <div>
      <h1>Manual RPG Test Report — {scenario_label}</h1>
      <p class="small">Generated by manual_llm_transcript.py</p>
      <p><strong>Scenario filters:</strong> {_html_escape(', '.join(scenario_names_to_run))}</p>
    </div>
  </div>

  <div class="grid">
    <div class="card"><strong>Total</strong><br>{len(scenario_summaries)}</div>
    <div class="card"><strong>Pass</strong><br>{pass_count}</div>
    <div class="card"><strong>Warn</strong><br>{warn_count}</div>
    <div class="card"><strong>Fail</strong><br>{fail_count}</div>
  </div>

  <div class="toolbar">
    <input id="scenarioSearch" type="search" placeholder="Search scenarios/warnings..." oninput="applySearch()" />
    <button data-filter="all" class="active" onclick="activateFilter(this, 'all')">All</button>
    <button data-filter="pass" onclick="activateFilter(this, 'pass')">Pass</button>
    <button data-filter="warn" onclick="activateFilter(this, 'warn')">Warn</button>
    <button data-filter="fail" onclick="activateFilter(this, 'fail')">Fail</button>
  </div>

  <div class="card">
    <h2>Scenarios</h2>
    <table id="scenarioTable">
      <thead>
        <tr>
          <th class="sortable" data-sort-key="status" onclick="sortScenarioTable('status', 'status')">
            Status <span class="sort-indicator"></span>
          </th>
          <th class="sortable" data-sort-key="name" onclick="sortScenarioTable('name', 'text')">
            Scenario <span class="sort-indicator"></span>
          </th>
          <th class="sortable" data-sort-key="turns" onclick="sortScenarioTable('turns', 'number')">
            Turns <span class="sort-indicator"></span>
          </th>
          <th class="sortable" data-sort-key="regression" onclick="sortScenarioTable('regression', 'number')">
            Regression Warnings <span class="sort-indicator"></span>
          </th>
          <th class="sortable" data-sort-key="scenario-warnings" onclick="sortScenarioTable('scenario-warnings', 'number')">
            Scenario Warnings <span class="sort-indicator"></span>
          </th>
          <th class="sortable" data-sort-key="preview" onclick="sortScenarioTable('preview', 'text')">
            Preview <span class="sort-indicator"></span>
          </th>
          <th class="sortable" data-sort-key="error" onclick="sortScenarioTable('error', 'text')">
            Error <span class="sort-indicator"></span>
          </th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>
</div>
<script>
  sortScenarioTable('status', 'status');
</script>
</body>
</html>
"""

    path = html_root / "index.html"
    path.write_text(html_text, encoding="utf-8")
    return str(path)