from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

SOURCE = "deterministic_phase7_real_artifact_discovery_hardening_gate"

NESTED_ARTIFACT_PREFIXES = (
    "",
    "reports",
    "report",
    "html",
    "transcripts",
    "transcript",
    "states",
    "state",
    "saves",
    "save",
    "sessions",
    "artifacts",
    "artifacts/reports",
    "artifacts/html",
    "artifacts/transcripts",
    "artifacts/states",
)


def _source_entry(kind: str, *, source: str = SOURCE, **fields: Any) -> Dict[str, Any]:
    entry = {"kind": kind, "source": source}
    entry.update(fields)
    return entry


def normalize_artifact_name(name: str) -> str:
    return str(name).replace("\\", "/").strip().lstrip("/")


def expanded_artifact_candidates(names: Iterable[str]) -> Tuple[str, ...]:
    """Return deterministic flat and nested candidate paths for saved artifacts."""

    candidates: List[str] = []
    seen: set[str] = set()
    for raw_name in names:
        normalized = normalize_artifact_name(raw_name)
        if not normalized:
            continue
        basename = normalized.rsplit("/", 1)[-1]
        expanded = [normalized]
        expanded.extend(
            f"{prefix}/{basename}" if prefix else basename
            for prefix in NESTED_ARTIFACT_PREFIXES
        )
        for candidate in expanded:
            candidate = normalize_artifact_name(candidate)
            if candidate and candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
    return tuple(candidates)


def find_artifact_matches(output_dir: Path, names: Iterable[str]) -> List[str]:
    output_root = Path(output_dir)
    matches: List[str] = []
    seen: set[str] = set()
    for candidate in expanded_artifact_candidates(names):
        path = output_root / candidate
        if path.is_file() and candidate not in seen:
            matches.append(candidate)
            seen.add(candidate)
    return matches


def discover_artifact_group(
    *,
    output_dir: Path,
    group: str,
    names: Iterable[str],
    required: bool = True,
    source: str = SOURCE,
) -> Dict[str, Any]:
    """Discover one saved artifact group with source-backed duplicate diagnostics."""

    output_root = Path(output_dir)
    candidates = expanded_artifact_candidates(names)
    matches = find_artifact_matches(output_root, candidates)
    diagnostics: List[Dict[str, Any]] = []
    blockers: List[Dict[str, Any]] = []

    if matches:
        diagnostics.append(
            _source_entry(
                "artifact_group_found",
                source=source,
                group=group,
                path=matches[0],
                matches=matches,
            )
        )
        if len(matches) > 1:
            diagnostics.append(
                _source_entry(
                    "ambiguous_artifact_group_candidates",
                    source=source,
                    group=group,
                    selected_path=matches[0],
                    matches=matches,
                )
            )
    elif required:
        blocker = _source_entry(
            "missing_artifact_group",
            source=source,
            group=group,
            output_dir=str(output_root),
            candidates=list(candidates),
        )
        diagnostics.append(blocker)
        blockers.append(blocker)

    return {
        "ok": bool(matches) or not required,
        "reason": "phase7_artifact_group_discovered" if matches else "phase7_artifact_group_missing",
        "group": group,
        "output_dir": str(output_root),
        "selected_path": matches[0] if matches else "",
        "matches": matches,
        "candidates": list(candidates),
        "diagnostics": diagnostics,
        "blockers": blockers,
        "source": source,
    }


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def read_json_artifact_group(
    *,
    output_dir: Path,
    group: str,
    names: Iterable[str],
    required: bool = True,
    source: str = SOURCE,
) -> Dict[str, Any]:
    discovery = discover_artifact_group(
        output_dir=output_dir,
        group=group,
        names=names,
        required=required,
        source=source,
    )
    output_root = Path(output_dir)
    diagnostics = list(discovery["diagnostics"])
    blockers = list(discovery["blockers"])

    for match in discovery["matches"]:
        path = output_root / match
        payload = _read_json(path)
        if payload is not None:
            diagnostics.append(_source_entry("json_artifact_loaded", source=source, group=group, path=match))
            return {
                "ok": not blockers,
                "reason": "phase7_json_artifact_loaded",
                "group": group,
                "path": path,
                "relative_path": match,
                "payload": payload,
                "discovery": discovery,
                "diagnostics": diagnostics,
                "blockers": blockers,
                "source": source,
            }
        diagnostics.append(_source_entry("invalid_json_artifact_candidate", source=source, group=group, path=match))

    if discovery["matches"] or required:
        blocker = _source_entry(
            "missing_valid_json_artifact",
            source=source,
            group=group,
            output_dir=str(output_root),
            matches=discovery["matches"],
        )
        diagnostics.append(blocker)
        blockers.append(blocker)

    return {
        "ok": False if required else not blockers,
        "reason": "phase7_json_artifact_missing_or_invalid",
        "group": group,
        "path": None,
        "relative_path": "",
        "payload": None,
        "discovery": discovery,
        "diagnostics": diagnostics,
        "blockers": blockers,
        "source": source,
    }


def assert_phase7_real_artifact_discovery_hardening_ready() -> Dict[str, Any]:
    required_prefixes = {"reports", "transcripts", "states", "artifacts"}
    available_prefixes = {prefix.split("/", 1)[0] for prefix in NESTED_ARTIFACT_PREFIXES if prefix}
    blockers: List[Dict[str, Any]] = []
    missing = sorted(required_prefixes - available_prefixes)
    if missing:
        blockers.append(_source_entry("missing_nested_artifact_prefixes", missing=missing))
    candidates = expanded_artifact_candidates(("campaign_report.html", "autoplay_transcript.json", "final_session.json"))
    for expected in ("reports/campaign_report.html", "transcripts/autoplay_transcript.json", "states/final_session.json"):
        if expected not in candidates:
            blockers.append(_source_entry("missing_nested_artifact_candidate", candidate=expected))
    return {
        "ok": not blockers,
        "reason": "phase7_real_artifact_discovery_hardening_ready"
        if not blockers
        else "phase7_real_artifact_discovery_hardening_not_ready",
        "nested_prefixes": NESTED_ARTIFACT_PREFIXES,
        "blockers": blockers,
        "source": SOURCE,
    }
