from __future__ import annotations

import pytest

from app.runtime.tenant_context import local_tenant_context
from app.settings import access as settings_access
from app.settings.registry import CORE_SETTING_SPECS
from app.settings.service import SettingsService


class _UnavailableDatabase:
    def connection(self):
        raise ConnectionError("PostgreSQL is unavailable")


def test_settings_reads_fail_closed_when_postgresql_is_unavailable(monkeypatch) -> None:
    service = SettingsService(
        _UnavailableDatabase(),
        local_tenant_context,
        specs=CORE_SETTING_SPECS,
    )
    monkeypatch.setattr(settings_access, "_SERVICE", service)

    with pytest.raises(ConnectionError, match="PostgreSQL is unavailable"):
        settings_access.load_settings()
