from __future__ import annotations

import io
import sys
import threading
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Dict, List, TextIO


class _TeeStream(io.TextIOBase):
    def __init__(self, original: TextIO, buffer: io.StringIO, lock: threading.Lock, prefix: str = ""):
        self._original = original
        self._buffer = buffer
        self._lock = lock
        self._prefix = prefix

    def write(self, text: str) -> int:
        if text is None:
            return 0
        with self._lock:
            self._original.write(text)
            self._original.flush()
            if self._prefix and text.strip():
                # Prefix line-by-line but preserve original console output.
                lines = text.splitlines(keepends=True)
                for line in lines:
                    if line.strip():
                        self._buffer.write(f"{self._prefix}{line}")
                    else:
                        self._buffer.write(line)
            else:
                self._buffer.write(text)
        return len(text)

    def flush(self) -> None:
        with self._lock:
            self._original.flush()

    @property
    def encoding(self) -> str:
        return getattr(self._original, "encoding", "utf-8") or "utf-8"

    def isatty(self) -> bool:
        return bool(getattr(self._original, "isatty", lambda: False)())


class ConsoleCapture(AbstractContextManager):
    """Tee stdout/stderr to an in-memory buffer and optional file.

    This keeps normal console behavior while giving the report/zip access to
    the exact logs the user would otherwise have to copy-paste manually.
    """

    def __init__(self, *, output_path: Path | None = None, max_chars: int = 250_000):
        self.output_path = output_path
        self.max_chars = max_chars
        self._stdout_original: TextIO | None = None
        self._stderr_original: TextIO | None = None
        self._buffer = io.StringIO()
        self._lock = threading.Lock()

    def __enter__(self) -> "ConsoleCapture":
        self._stdout_original = sys.stdout
        self._stderr_original = sys.stderr
        sys.stdout = _TeeStream(self._stdout_original, self._buffer, self._lock, prefix="")
        sys.stderr = _TeeStream(self._stderr_original, self._buffer, self._lock, prefix="[stderr] ")
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if self._stdout_original is not None:
            sys.stdout = self._stdout_original
        if self._stderr_original is not None:
            sys.stderr = self._stderr_original
        self.write_file()
        return False

    def text(self) -> str:
        value = self._buffer.getvalue()
        if len(value) > self.max_chars:
            return value[-self.max_chars :]
        return value

    def write_file(self) -> Dict[str, Any]:
        if not self.output_path:
            return {"ok": True, "path": "", "bytes": 0, "truncated": False}
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        text = self.text()
        self.output_path.write_text(text, encoding="utf-8", errors="replace")
        return {
            "ok": True,
            "path": str(self.output_path),
            "bytes": self.output_path.stat().st_size if self.output_path.exists() else 0,
            "truncated": len(self._buffer.getvalue()) > self.max_chars,
        }


def summarize_console_log(text: str) -> Dict[str, Any]:
    text = text or ""
    lines = text.splitlines()
    error_lines: List[str] = []
    warning_lines: List[str] = []
    turn_error_lines: List[str] = []
    provider_lines: List[str] = []

    for line in lines:
        lower = line.lower()
        stripped = line.strip()
        if not stripped:
            continue
        if "turn " in lower and " error:" in lower:
            turn_error_lines.append(stripped)
        if "error" in lower or "traceback" in lower or "exception" in lower:
            error_lines.append(stripped)
        if "warning" in lower or "warn" in lower:
            warning_lines.append(stripped)
        if "registered provider" in lower or "provider discovery" in lower or "provider shape" in lower:
            provider_lines.append(stripped)

    return {
        "line_count": len(lines),
        "char_count": len(text),
        "error_count": len(error_lines),
        "warning_count": len(warning_lines),
        "turn_error_count": len(turn_error_lines),
        "provider_line_count": len(provider_lines),
        "turn_errors": turn_error_lines[:30],
        "errors": error_lines[:50],
        "warnings": warning_lines[:50],
        "provider_lines": provider_lines[:30],
        "tail": lines[-120:],
    }