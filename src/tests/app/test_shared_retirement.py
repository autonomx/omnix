from __future__ import annotations

from pathlib import Path

import pytest

from app.settings import access as settings_access


def test_shared_facade_and_file_backed_setting_constants_are_retired() -> None:
    app_root = Path("src/app")
    assert not (app_root / "shared.py").exists()

    forbidden = ("SETTINGS_" + "FILE", "SESSIONS_" + "FILE", "SECRETS_" + "FILE")
    offenders: list[str] = []
    for path in app_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(token in text for token in forbidden):
            offenders.append(path.as_posix())
    assert offenders == []


def test_settings_reads_fail_closed_without_installed_service(monkeypatch) -> None:
    monkeypatch.setattr(settings_access, "_SERVICE", None)
    with pytest.raises(RuntimeError, match="settings service is not installed"):
        settings_access.load_settings()
