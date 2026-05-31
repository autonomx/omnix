from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from tests.rpg.manual.constants import MANUAL_HTML_JSON_PREVIEW_CHARS
from tests.rpg.manual.extractors.base import _extract_visible_interaction_reason
from tests.rpg.manual.safe import _safe_dict, _safe_list, _safe_str


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
