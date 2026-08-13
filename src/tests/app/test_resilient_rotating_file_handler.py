from __future__ import annotations

import logging
import logging.handlers

from app.gateway.resilient_rotating_file_handler import ResilientRotatingFileHandler


def test_permission_error_uses_copy_truncate_fallback(tmp_path, monkeypatch) -> None:
    log_path = tmp_path / "diagnostics.log"
    original = b'{"event":"before-rollover"}\n'
    log_path.write_bytes(original)
    handler = ResilientRotatingFileHandler(
        log_path,
        maxBytes=10,
        backupCount=2,
        encoding="utf-8",
    )

    def blocked_rename(_handler: logging.handlers.RotatingFileHandler) -> None:
        if _handler.stream is not None:
            _handler.stream.close()
            _handler.stream = None
        raise PermissionError("reader blocks rename")

    monkeypatch.setattr(logging.handlers.RotatingFileHandler, "doRollover", blocked_rename)
    handler.doRollover()

    assert (tmp_path / "diagnostics.log.1").read_bytes() == original
    assert log_path.read_bytes() == b""
    assert handler.stream is not None
    handler.close()
