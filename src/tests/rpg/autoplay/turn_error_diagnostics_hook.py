"""Per-turn error diagnostics for autoplay runs.

The generated runtime currently emits concise ``TURN N ERROR`` lines for some
caught turn failures.  This hook records those emissions with a bounded Python
stack tail from the error-handling site so the next evidence bundle contains a
source pointer instead of only the one-line message.
"""
from __future__ import annotations

import builtins
import json
import re
import traceback
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

SOURCE = "autoplay_turn_error_diagnostics_hook_v1"
SUMMARY_NAME = "autoplay-turn-error-diagnostics.json"
_PATTERN = re.compile(r"TURN\s+(?P<turn>\d+)\s+ERROR:\s+(?P<etype>[A-Za-z_][A-Za-z0-9_]*):\s*(?P<message>.*)")
_INSTALLED = False
_OUTPUT_DIR: Optional[Path] = None
_ORIGINAL_PRINT = builtins.print


def _parse_output_dir(argv: Iterable[str]) -> Optional[Path]:
    args = list(argv)
    for index, value in enumerate(args):
        if value == "--output-dir" and index + 1 < len(args):
            return Path(args[index + 1])
        if value.startswith("--output-dir="):
            return Path(value.split("=", 1)[1])
    return None


def _summary_path() -> Optional[Path]:
    return (_OUTPUT_DIR / SUMMARY_NAME) if _OUTPUT_DIR is not None else None


def _load_payload(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"ok": True, "source": SOURCE, "events": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"ok": True, "source": SOURCE, "events": []}
    except Exception:
        return {"ok": True, "source": SOURCE, "events": []}


def _record_line(line: str) -> None:
    match = _PATTERN.search(line)
    if not match:
        return
    path = _summary_path()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _load_payload(path)
    events = list(payload.get("events") or [])
    events.append(
        {
            "turn_index": int(match.group("turn")),
            "error_type": match.group("etype"),
            "message": match.group("message"),
            "line": line[-2000:],
            "stack_tail": traceback.format_stack(limit=30),
            "source": SOURCE,
        }
    )
    payload.update(
        {
            "ok": True,
            "source": SOURCE,
            "event_count": len(events),
            "events": events[-200:],
        }
    )
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def guarded_print(*args: Any, **kwargs: Any) -> None:
    _ORIGINAL_PRINT(*args, **kwargs)
    try:
        text = " ".join(str(arg) for arg in args)
        _record_line(text)
    except Exception:
        return


def install_turn_error_diagnostics_hook(*, output_dir: str | Path | None = None) -> bool:
    global _INSTALLED, _OUTPUT_DIR
    if output_dir is not None:
        _OUTPUT_DIR = Path(output_dir)
    if _INSTALLED:
        return False
    builtins.print = guarded_print  # type: ignore[assignment]
    _INSTALLED = True
    return True


def install_turn_error_diagnostics_hook_from_argv(argv: Iterable[str]) -> bool:
    return install_turn_error_diagnostics_hook(output_dir=_parse_output_dir(argv))
