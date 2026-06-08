"""Write-time report size guard for autoplay artifacts.

End-of-run hooks can be bypassed by forced finalization paths.  This guard caps
large report artifacts at the moment they are materialized through common file,
copy, and ZIP write APIs.  It remains artifact-only and never affects runtime
state or gameplay truth.
"""
from __future__ import annotations

import builtins
import io
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from app.rpg.autoplay_report_size_guard import (
    REPORT_HTML_NAMES,
    REPORT_JSON_NAME,
    SIZE_GUARD_SOURCE,
    _compact_payload,
    _limit_for_name,
)

MATERIALIZATION_GUARD_SOURCE = "autoplay_report_materialization_guard_v3"
SUMMARY_NAME = "autoplay-report-size-guard-summary.json"
_INSTALLED = False
_OUTPUT_DIR: Optional[Path] = None
_ORIGINAL_WRITE_TEXT = Path.write_text
_ORIGINAL_WRITE_BYTES = Path.write_bytes
_ORIGINAL_COPYFILE = shutil.copyfile
_ORIGINAL_COPY2 = shutil.copy2
_ORIGINAL_ZIP_WRITE = zipfile.ZipFile.write
_ORIGINAL_ZIP_WRITESTR = zipfile.ZipFile.writestr
_ORIGINAL_OPEN = builtins.open
_ORIGINAL_IO_OPEN = io.open


def _is_report_name(value: str | Path) -> bool:
    name = Path(str(value)).name
    return name == REPORT_JSON_NAME or name in REPORT_HTML_NAMES


def _summary_path(path: str | Path | None = None) -> Optional[Path]:
    if _OUTPUT_DIR is not None:
        return _OUTPUT_DIR / SUMMARY_NAME
    if path is None:
        return None
    candidate = Path(path)
    if candidate.name:
        return candidate.parent / SUMMARY_NAME
    return candidate / SUMMARY_NAME


def _read_summary(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {
            "ok": True,
            "source": SIZE_GUARD_SOURCE,
            "materialization_guard_source": MATERIALIZATION_GUARD_SOURCE,
            "file_result": {"ok": True, "capped_files": [], "source": SIZE_GUARD_SOURCE},
            "zip_results": [],
        }
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
        return existing if isinstance(existing, dict) else {}
    except Exception:
        return {}


def _write_summary_event(kind: str, event: Dict[str, Any], *, path_hint: str | Path | None = None) -> None:
    summary = _summary_path(path_hint)
    if summary is None:
        return
    summary.parent.mkdir(parents=True, exist_ok=True)
    payload = _read_summary(summary)
    payload.setdefault("ok", True)
    payload.setdefault("source", SIZE_GUARD_SOURCE)
    payload.setdefault("materialization_guard_source", MATERIALIZATION_GUARD_SOURCE)
    payload.setdefault("file_result", {"ok": True, "capped_files": [], "source": SIZE_GUARD_SOURCE})
    payload.setdefault("zip_results", [])
    if kind == "file":
        payload["file_result"].setdefault("capped_files", []).append(event)
    else:
        zip_results = payload.setdefault("zip_results", [])
        if not zip_results:
            zip_results.append({"ok": True, "capped_members": [], "source": SIZE_GUARD_SOURCE})
        zip_results[0].setdefault("capped_members", []).append(event)
    _ORIGINAL_WRITE_TEXT(summary, json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _bytes_for_text(data: str, encoding: str | None) -> bytes:
    return data.encode(encoding or "utf-8")


def _cap_bytes_for_name(name: str | Path, raw: bytes) -> Optional[bytes]:
    if not _is_report_name(name):
        return None
    limit = _limit_for_name(name)
    if limit <= 0 or len(raw) <= limit:
        return None
    return _compact_payload(str(name), len(raw), limit)


def cap_report_materialization_bytes(path: str | Path, raw: bytes) -> bytes:
    capped = _cap_bytes_for_name(path, raw)
    if capped is None:
        return raw
    _write_summary_event(
        "file",
        {
            "path": str(path),
            "original_size_bytes": len(raw),
            "new_size_bytes": len(capped),
            "limit_bytes": _limit_for_name(path),
            "source": MATERIALIZATION_GUARD_SOURCE,
        },
        path_hint=path,
    )
    return capped


class _GuardedReportFile:
    def __init__(self, file_obj: Any, path: str | Path, *, binary: bool, encoding: str | None = None) -> None:
        self._file = file_obj
        self._path = Path(path)
        self._binary = binary
        self._encoding = encoding or "utf-8"
        self._limit = _limit_for_name(path)
        self._seen_bytes = 0
        self._capped = False
        self._summary_written = False
        self._written_bytes = 0

    def __enter__(self) -> "_GuardedReportFile":
        self._file.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Any:
        try:
            self.close()
        finally:
            return self._file.__exit__(exc_type, exc, tb)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._file, name)

    def _payload_bytes(self, data: Any) -> bytes:
        if isinstance(data, bytes):
            return data
        if isinstance(data, bytearray):
            return bytes(data)
        return str(data).encode(self._encoding)

    def _write_payload(self, payload: bytes) -> int:
        if self._binary:
            return self._file.write(payload)
        return self._file.write(payload.decode(self._encoding, errors="replace"))

    def write(self, data: Any) -> int:
        raw = self._payload_bytes(data)
        self._seen_bytes += len(raw)
        if self._limit <= 0:
            return self._file.write(data)
        if self._capped:
            return len(data) if isinstance(data, (str, bytes, bytearray)) else len(raw)
        if self._seen_bytes <= self._limit:
            self._written_bytes += len(raw)
            return self._file.write(data)
        payload = _compact_payload(str(self._path), self._seen_bytes, self._limit)
        try:
            self._file.seek(0)
            self._file.truncate(0)
        except Exception:
            pass
        self._written_bytes = self._write_payload(payload)
        self._capped = True
        return len(data) if isinstance(data, (str, bytes, bytearray)) else len(raw)

    def close(self) -> None:
        if self._capped and not self._summary_written:
            _write_summary_event(
                "file",
                {
                    "path": str(self._path),
                    "original_size_bytes": self._seen_bytes,
                    "new_size_bytes": self._written_bytes,
                    "limit_bytes": self._limit,
                    "source": MATERIALIZATION_GUARD_SOURCE,
                    "guarded_api": "open.write",
                },
                path_hint=self._path,
            )
            self._summary_written = True
        return self._file.close()


def _encoding_from_open_args(args: tuple[Any, ...], kwargs: Dict[str, Any]) -> str | None:
    if isinstance(kwargs.get("encoding"), str):
        return kwargs["encoding"]
    if len(args) >= 2 and isinstance(args[1], str):
        return args[1]
    return None


def _guarded_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
    file_obj = _ORIGINAL_OPEN(file, mode, *args, **kwargs)
    try:
        writing = any(token in mode for token in ("w", "a", "x", "+"))
        if not writing or not _is_report_name(file):
            return file_obj
        return _GuardedReportFile(
            file_obj,
            file,
            binary="b" in mode,
            encoding=_encoding_from_open_args(args, kwargs),
        )
    except Exception:
        return file_obj


def _guarded_io_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
    file_obj = _ORIGINAL_IO_OPEN(file, mode, *args, **kwargs)
    try:
        writing = any(token in mode for token in ("w", "a", "x", "+"))
        if not writing or not _is_report_name(file):
            return file_obj
        return _GuardedReportFile(
            file_obj,
            file,
            binary="b" in mode,
            encoding=_encoding_from_open_args(args, kwargs),
        )
    except Exception:
        return file_obj


def _guarded_write_text(self: Path, data: str, *args: Any, **kwargs: Any) -> int:
    encoding = kwargs.get("encoding")
    if len(args) >= 1 and isinstance(args[0], str):
        encoding = args[0]
    raw = _bytes_for_text(data, encoding)
    capped = _cap_bytes_for_name(self, raw)
    if capped is None:
        return _ORIGINAL_WRITE_TEXT(self, data, *args, **kwargs)
    self.parent.mkdir(parents=True, exist_ok=True)
    written = _ORIGINAL_WRITE_BYTES(self, capped)
    _write_summary_event(
        "file",
        {
            "path": str(self),
            "original_size_bytes": len(raw),
            "new_size_bytes": written,
            "limit_bytes": _limit_for_name(self),
            "source": MATERIALIZATION_GUARD_SOURCE,
        },
        path_hint=self,
    )
    return written


def _guarded_write_bytes(self: Path, data: bytes) -> int:
    capped = _cap_bytes_for_name(self, data)
    if capped is None:
        return _ORIGINAL_WRITE_BYTES(self, data)
    self.parent.mkdir(parents=True, exist_ok=True)
    written = _ORIGINAL_WRITE_BYTES(self, capped)
    _write_summary_event(
        "file",
        {
            "path": str(self),
            "original_size_bytes": len(data),
            "new_size_bytes": written,
            "limit_bytes": _limit_for_name(self),
            "source": MATERIALIZATION_GUARD_SOURCE,
        },
        path_hint=self,
    )
    return written


def _guarded_copyfile(src: str | Path, dst: str | Path, *args: Any, **kwargs: Any) -> str:
    dst_path = Path(dst)
    if _is_report_name(dst_path):
        try:
            raw = Path(src).read_bytes()
            capped = _cap_bytes_for_name(dst_path, raw)
            if capped is not None:
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                _ORIGINAL_WRITE_BYTES(dst_path, capped)
                _write_summary_event(
                    "file",
                    {
                        "path": str(dst_path),
                        "source_path": str(src),
                        "original_size_bytes": len(raw),
                        "new_size_bytes": len(capped),
                        "limit_bytes": _limit_for_name(dst_path),
                        "source": MATERIALIZATION_GUARD_SOURCE,
                    },
                    path_hint=dst_path,
                )
                return str(dst)
        except Exception:
            pass
    return _ORIGINAL_COPYFILE(src, dst, *args, **kwargs)


def _guarded_copy2(src: str | Path, dst: str | Path, *args: Any, **kwargs: Any) -> str:
    result = _guarded_copyfile(src, dst, *args, **kwargs)
    return result


def _zip_summary_hint(zip_file: zipfile.ZipFile) -> Optional[Path]:
    filename = getattr(zip_file, "filename", None)
    return Path(filename).parent if filename else _OUTPUT_DIR


def _guarded_zip_writestr(self: zipfile.ZipFile, zinfo_or_arcname: Any, data: Any, *args: Any, **kwargs: Any) -> None:
    arcname = zinfo_or_arcname.filename if isinstance(zinfo_or_arcname, zipfile.ZipInfo) else str(zinfo_or_arcname)
    raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    capped = _cap_bytes_for_name(arcname, raw)
    if capped is None:
        return _ORIGINAL_ZIP_WRITESTR(self, zinfo_or_arcname, data, *args, **kwargs)
    _write_summary_event(
        "zip",
        {
            "member": arcname,
            "zip_path": str(getattr(self, "filename", "")),
            "original_size_bytes": len(raw),
            "new_size_bytes": len(capped),
            "limit_bytes": _limit_for_name(arcname),
            "source": MATERIALIZATION_GUARD_SOURCE,
        },
        path_hint=_zip_summary_hint(self),
    )
    return _ORIGINAL_ZIP_WRITESTR(self, zinfo_or_arcname, capped, *args, **kwargs)


def _guarded_zip_write(self: zipfile.ZipFile, filename: str | Path, arcname: str | None = None, *args: Any, **kwargs: Any) -> None:
    member = arcname or Path(filename).name
    if _is_report_name(member):
        try:
            raw = Path(filename).read_bytes()
            capped = _cap_bytes_for_name(member, raw)
            if capped is not None:
                _write_summary_event(
                    "zip",
                    {
                        "member": str(member),
                        "zip_path": str(getattr(self, "filename", "")),
                        "original_size_bytes": len(raw),
                        "new_size_bytes": len(capped),
                        "limit_bytes": _limit_for_name(member),
                        "source": MATERIALIZATION_GUARD_SOURCE,
                    },
                    path_hint=_zip_summary_hint(self),
                )
                return _ORIGINAL_ZIP_WRITESTR(self, member, capped)
        except Exception:
            pass
    return _ORIGINAL_ZIP_WRITE(self, filename, arcname=arcname, *args, **kwargs)


def install_report_materialization_size_guard(*, output_dir: str | Path | None = None) -> bool:
    global _INSTALLED, _OUTPUT_DIR
    if output_dir is not None:
        _OUTPUT_DIR = Path(output_dir)
    if _INSTALLED:
        return False
    Path.write_text = _guarded_write_text  # type: ignore[assignment]
    Path.write_bytes = _guarded_write_bytes  # type: ignore[assignment]
    shutil.copyfile = _guarded_copyfile  # type: ignore[assignment]
    shutil.copy2 = _guarded_copy2  # type: ignore[assignment]
    zipfile.ZipFile.write = _guarded_zip_write  # type: ignore[assignment]
    zipfile.ZipFile.writestr = _guarded_zip_writestr  # type: ignore[assignment]
    builtins.open = _guarded_open  # type: ignore[assignment]
    io.open = _guarded_io_open  # type: ignore[assignment]
    _INSTALLED = True
    return True


def install_report_materialization_size_guard_from_argv(argv: Iterable[str]) -> bool:
    args = list(argv)
    output_dir: Optional[Path] = None
    for index, value in enumerate(args):
        if value == "--output-dir" and index + 1 < len(args):
            output_dir = Path(args[index + 1])
        elif value.startswith("--output-dir="):
            output_dir = Path(value.split("=", 1)[1])
    return install_report_materialization_size_guard(output_dir=output_dir)
