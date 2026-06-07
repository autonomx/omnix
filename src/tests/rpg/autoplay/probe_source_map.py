"""Generated probe source mapping for autoplay diagnostics."""
from __future__ import annotations

import json
import linecache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SOURCE = "autoplay_probe_source_map_v1"
ARTIFACT_NAME = "autoplay-runtime-probe-source-map.json"
EVENT_TEXT = "runtime_turn_execution.result"
_OUTPUT_DIR: Optional[Path] = None


def parse_output_dir(argv: Iterable[str]) -> Optional[Path]:
    args = list(argv)
    for index, value in enumerate(args):
        if value == "--output-dir" and index + 1 < len(args):
            return Path(args[index + 1])
        if value.startswith("--output-dir="):
            return Path(value.split("=", 1)[1])
    return None


def configure_probe_source_map(*, output_dir: str | Path | None = None) -> None:
    global _OUTPUT_DIR
    if output_dir is not None:
        _OUTPUT_DIR = Path(output_dir)


def configure_probe_source_map_from_argv(argv: Iterable[str]) -> None:
    configure_probe_source_map(output_dir=parse_output_dir(argv))


def _enclosing_function(lines: List[str], line_index: int) -> str:
    for index in range(line_index, -1, -1):
        text = lines[index].strip()
        if text.startswith("def ") or text.startswith("async def "):
            name = text.split("def ", 1)[1].split("(", 1)[0].strip()
            return name
    return ""


def _helper_names(line: str) -> List[str]:
    names: List[str] = []
    for part in line.replace("(", " ( ").split():
        if part == "(" and names:
            continue
        if part.endswith("("):
            candidate = part[:-1]
            if candidate.isidentifier():
                names.append(candidate)
    # Simpler fallback for common call syntax.
    tokens = line.replace("(", " ( ").split()
    for index, token in enumerate(tokens[:-1]):
        if tokens[index + 1] == "(" and token.isidentifier() and token not in names:
            names.append(token)
    return names[:40]


def _names_on_line(line: str) -> List[str]:
    cleaned = "".join(ch if (ch.isalnum() or ch == "_") else " " for ch in line)
    blocked = {"event", "keys", "ok", "ts", "True", "False", "None"}
    return sorted({token for token in cleaned.split() if token.isidentifier() and token not in blocked})[:80]


def build_probe_source_map_from_source(source: str, *, filename: str = "") -> Dict[str, Any]:
    lines = source.splitlines()
    matches: List[Dict[str, Any]] = []
    for line_index, line in enumerate(lines):
        if EVENT_TEXT not in line:
            continue
        start = max(0, line_index - 6)
        end = min(len(lines), line_index + 7)
        matches.append(
            {
                "line_number": line_index + 1,
                "filename": filename,
                "enclosing_function_name": _enclosing_function(lines, line_index),
                "line": line,
                "called_helper_names": _helper_names(line),
                "referenced_local_names": _names_on_line(line),
                "context": [
                    {"line_number": index + 1, "text": lines[index]}
                    for index in range(start, end)
                ],
            }
        )
    return {"ok": True, "source": SOURCE, "event_text": EVENT_TEXT, "match_count": len(matches), "matches": matches}


def write_probe_source_map_from_linecache() -> Dict[str, Any]:
    if _OUTPUT_DIR is None:
        return {"ok": False, "reason": "output_dir_missing", "source": SOURCE}
    path = _OUTPUT_DIR / ARTIFACT_NAME
    matches: List[Dict[str, Any]] = []
    for filename, entry in list(linecache.cache.items()):
        if "__combined_autoplay_llm_campaign__.py" not in str(filename):
            continue
        try:
            source = "".join(entry[2])
            result = build_probe_source_map_from_source(source, filename=str(filename))
            matches.extend(result.get("matches", []))
        except Exception:
            continue
    payload = {"ok": True, "source": SOURCE, "event_text": EVENT_TEXT, "match_count": len(matches), "matches": matches}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["path"] = str(path)
    return payload
