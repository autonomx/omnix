from __future__ import annotations

import os
from pathlib import Path

from app.agent_runtime import debug_logging


def test_agent_debug_logging_is_opt_in(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(debug_logging.AGENT_DEBUG_ENABLED_ENV, raising=False)
    monkeypatch.setenv(debug_logging.AGENT_DEBUG_LOG_DIR_ENV, str(tmp_path / "agent-logs"))
    debug_logging._reset_agent_debug_logging_for_tests()

    assert not debug_logging.agent_debug_logging_enabled()
    debug_logging.configure_agent_debug_logging(force=True)
    debug_logging.log_agent_activity("should.not.persist", fields={"prompt": "private task text"})

    assert not (tmp_path / "agent-logs").exists()


def test_agent_debug_logging_remains_explicitly_enableable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(debug_logging.AGENT_DEBUG_ENABLED_ENV, "1")
    monkeypatch.setenv(debug_logging.AGENT_DEBUG_LOG_DIR_ENV, str(tmp_path / "agent-logs"))
    debug_logging._reset_agent_debug_logging_for_tests()

    debug_logging.configure_agent_debug_logging(force=True)
    debug_logging.log_agent_activity("enabled.trace", run_id="run-1")

    assert debug_logging.agent_debug_logging_enabled()
    assert (tmp_path / "agent-logs" / "run-run-1.jsonl").is_file()

    debug_logging._reset_agent_debug_logging_for_tests()
