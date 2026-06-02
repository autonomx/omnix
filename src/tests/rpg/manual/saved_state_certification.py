from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from app.rpg.session import session_checkpoint_digest
from tests.rpg.manual.artifact_discovery import read_json_artifact_group
from tests.rpg.manual.certification_artifacts import emit_saved_100_turn_certification_artifacts

SOURCE = "deterministic_phase7_real_saved_state_certification_gate"
FINAL_STATE_FILENAMES = (
    "final_session.json",
    "final_state.json",
    "campaign_final_state.json",
)
LOADABLE_STATE_FILENAMES = (
    "loadable_session.json",
    "loaded_session.json",
    "saved_session.json",
    "loadable_state.json",
)
EXPECTED_STATE_FILENAMES = (
    "expected_final_session.json",
    "expected_final_state.json",
)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return "" if value is None else str(value)


def _source_entry(kind: str, **fields: Any) -> Dict[str, Any]:
    entry = {"kind": kind, "source": SOURCE}
    entry.update(fields)
    return entry


def _stable_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _payload_session(payload: Dict[str, Any]) -> Dict[str, Any]:
    if "manifest" in payload or "simulation_state" in payload or "runtime_state" in payload:
        return payload
    return _safe_dict(payload.get("session"))


def _state_digest(payload: Dict[str, Any]) -> Dict[str, Any]:
    session = _payload_session(payload)
    if session:
        return {
            "checkpoint_digest": session_checkpoint_digest(session),
            "state_digest": _stable_digest(_safe_dict(session.get("simulation_state")) or session),
            "digest_kind": "session",
        }
    state = _safe_dict(payload.get("state")) or payload
    return {
        "checkpoint_digest": "",
        "state_digest": _stable_digest(state),
        "digest_kind": "state",
    }


def _json_group(output_dir: Path, group: str, names: tuple[str, ...], *, required: bool) -> Dict[str, Any]:
    return read_json_artifact_group(
        output_dir=output_dir,
        group=group,
        names=names,
        required=required,
        source=SOURCE,
    )


def build_real_saved_state_certification_artifact(
    saved_artifacts: Dict[str, Any],
    *,
    output_dir: Path,
) -> Dict[str, Any]:
    """Attach real saved/loadable state digests from manual/autoplay output files."""

    output_dir = Path(output_dir)
    saved = dict(_safe_dict(saved_artifacts))
    final = _json_group(output_dir, "final_state_artifact", FINAL_STATE_FILENAMES, required=True)
    loaded = _json_group(output_dir, "loadable_state_artifact", LOADABLE_STATE_FILENAMES, required=True)
    expected = _json_group(output_dir, "expected_state_artifact", EXPECTED_STATE_FILENAMES, required=False)
    blockers: List[Dict[str, Any]] = []
    metadata: List[Dict[str, Any]] = []
    metadata.extend(final["diagnostics"])
    metadata.extend(loaded["diagnostics"])
    metadata.extend(expected["diagnostics"])

    final_payload = _safe_dict(final.get("payload"))
    loaded_payload = _safe_dict(loaded.get("payload"))
    expected_payload = _safe_dict(expected.get("payload"))

    if not final_payload:
        blockers.append(_source_entry("missing_final_saved_state", output_dir=str(output_dir)))
    else:
        final_digest = _state_digest(final_payload)
        saved["final_checkpoint_digest"] = final_digest["checkpoint_digest"]
        saved["final_state_digest"] = final_digest["state_digest"]
        metadata.append(
            _source_entry(
                "final_saved_state",
                path=str(final.get("relative_path")),
                digest_kind=final_digest["digest_kind"],
                checkpoint_digest=final_digest["checkpoint_digest"],
                state_digest=final_digest["state_digest"],
            )
        )

    if not loaded_payload:
        blockers.append(_source_entry("missing_loadable_saved_state", output_dir=str(output_dir)))
    else:
        loaded_digest = _state_digest(loaded_payload)
        saved["loaded_checkpoint_digest"] = loaded_digest["checkpoint_digest"]
        saved["loaded_state_digest"] = loaded_digest["state_digest"]
        metadata.append(
            _source_entry(
                "loadable_saved_state",
                path=str(loaded.get("relative_path")),
                digest_kind=loaded_digest["digest_kind"],
                checkpoint_digest=loaded_digest["checkpoint_digest"],
                state_digest=loaded_digest["state_digest"],
            )
        )

    if expected_payload:
        expected_digest = _state_digest(expected_payload)
        saved["expected_final_checkpoint_digest"] = expected_digest["checkpoint_digest"]
        saved["expected_final_state_digest"] = expected_digest["state_digest"]
        metadata.append(
            _source_entry(
                "expected_final_saved_state",
                path=str(expected.get("relative_path")),
                digest_kind=expected_digest["digest_kind"],
                checkpoint_digest=expected_digest["checkpoint_digest"],
                state_digest=expected_digest["state_digest"],
            )
        )

    saved["state_diff_source"] = SOURCE
    saved["artifact_source"] = _safe_str(saved.get("artifact_source") or SOURCE)
    saved["saved_state_source_metadata"] = metadata
    return {
        "ok": not blockers,
        "reason": "phase7_real_saved_state_artifact_ready"
        if not blockers
        else "phase7_real_saved_state_artifact_blocked",
        "saved_artifacts": saved,
        "metadata": metadata,
        "blockers": blockers,
        "source": SOURCE,
    }


def emit_real_saved_state_certification_artifacts(
    saved_artifacts: Dict[str, Any],
    *,
    output_dir: Path,
    report_html_path: Path | None = None,
    expected_turns: int = 100,
) -> Dict[str, Any]:
    artifact = build_real_saved_state_certification_artifact(saved_artifacts, output_dir=output_dir)
    emitted = emit_saved_100_turn_certification_artifacts(
        artifact["saved_artifacts"],
        output_dir=output_dir,
        report_html_path=report_html_path,
        expected_turns=expected_turns,
    )
    emitted = dict(emitted)
    emitted["saved_state_source"] = SOURCE
    emitted["saved_state_metadata"] = artifact["metadata"]
    emitted["saved_state_blockers"] = artifact["blockers"]
    emitted["ok"] = emitted.get("ok") is True and artifact.get("ok") is True
    if artifact.get("ok") is not True:
        emitted["reason"] = "phase7_real_saved_state_certification_emitted_with_blockers"
    return emitted


def assert_phase7_real_saved_state_certification_ready() -> Dict[str, Any]:
    blockers: List[Dict[str, Any]] = []
    if "final_session.json" not in FINAL_STATE_FILENAMES:
        blockers.append(_source_entry("missing_final_state_filename_candidate"))
    if "loadable_session.json" not in LOADABLE_STATE_FILENAMES:
        blockers.append(_source_entry("missing_loadable_state_filename_candidate"))
    return {
        "ok": not blockers,
        "reason": "phase7_real_saved_state_certification_ready"
        if not blockers
        else "phase7_real_saved_state_certification_not_ready",
        "blockers": blockers,
        "source": SOURCE,
    }
