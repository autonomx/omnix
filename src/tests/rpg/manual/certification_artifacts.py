from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from app.rpg.session import (
    append_saved_100_turn_certification_to_campaign_report_html,
    build_saved_100_turn_certification_payload,
)
from tests.rpg.manual.constants import TEST_RESULTS_ROOT

SOURCE = "deterministic_phase7_saved_certification_artifact_writer_gate"
CERTIFICATION_PAYLOAD_FILENAME = "phase7_100_turn_certification.json"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _utf8_size(value: str) -> int:
    return len(value.encode("utf-8"))


def emit_saved_100_turn_certification_artifacts(
    saved_artifacts: Dict[str, Any],
    *,
    output_dir: Path | None = None,
    report_html_path: Path | None = None,
    expected_turns: int = 100,
) -> Dict[str, Any]:
    """Write deterministic Phase 7.8 certification artifacts next to manual/autoplay outputs."""

    output_root = output_dir or TEST_RESULTS_ROOT
    output_root.mkdir(parents=True, exist_ok=True)

    payload = build_saved_100_turn_certification_payload(_safe_dict(saved_artifacts), expected_turns=expected_turns)
    payload = dict(payload)
    payload["artifact_writer_source"] = SOURCE

    payload_path = output_root / CERTIFICATION_PAYLOAD_FILENAME
    payload_text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    payload_path.write_text(payload_text, encoding="utf-8")

    html_result: Dict[str, Any] = {
        "appended": False,
        "path": "",
        "bytes": 0,
        "source": SOURCE,
    }
    if report_html_path is not None:
        existing_html = report_html_path.read_text(encoding="utf-8") if report_html_path.exists() else ""
        appended_html = append_saved_100_turn_certification_to_campaign_report_html(existing_html, payload)
        report_html_path.parent.mkdir(parents=True, exist_ok=True)
        report_html_path.write_text(appended_html, encoding="utf-8")
        html_result = {
            "appended": True,
            "path": str(report_html_path),
            "bytes": _utf8_size(appended_html),
            "source": SOURCE,
        }

    return {
        "ok": payload.get("ok") is True,
        "reason": "phase7_saved_certification_artifacts_emitted"
        if payload.get("ok") is True
        else "phase7_saved_certification_artifacts_emitted_with_blockers",
        "payload_path": str(payload_path),
        "payload_bytes": _utf8_size(payload_text),
        "html_report": html_result,
        "certification_status": _safe_dict(payload.get("certification_result")).get("certification_status", ""),
        "source": SOURCE,
    }


def assert_phase7_saved_certification_artifact_writer_ready() -> Dict[str, Any]:
    turns = [
        {
            "turn_index": index + 1,
            "action_text": f"writer artifact step {index % 7}",
            "location_id": f"location:{index % 5}",
            "quest_events": [{"quest_id": "quest:old_mill"}] if index % 25 == 0 else [],
            "currency_delta": {"silver": -1} if index % 20 == 0 else {},
            "journal_updates": ["new clue"] if index % 30 == 0 else [],
            "combat_event": {"encounter_id": "encounter:road"} if index == 40 else None,
        }
        for index in range(100)
    ]
    payload = build_saved_100_turn_certification_payload({"transcript": {"rows": turns}, "report": {"html": "ok"}})
    blockers = []
    if payload.get("ok") is not True:
        blockers.append({"kind": "saved_certification_payload_not_ready", "source": SOURCE})
    if not CERTIFICATION_PAYLOAD_FILENAME.endswith(".json"):
        blockers.append({"kind": "saved_certification_payload_filename_not_json", "source": SOURCE})
    return {
        "ok": not blockers,
        "reason": "phase7_saved_certification_artifact_writer_ready"
        if not blockers
        else "phase7_saved_certification_artifact_writer_not_ready",
        "blockers": blockers,
        "source": SOURCE,
    }
