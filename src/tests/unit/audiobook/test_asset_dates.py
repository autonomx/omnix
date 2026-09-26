from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from app.audiobook.service import AudiobookService
from app.persistence.tenant import local_tenant_context


def test_export_exposes_asset_creation_time_independently_of_export_time(monkeypatch):
    export_date = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)
    asset_date = datetime(2026, 9, 21, 11, tzinfo=timezone.utc)

    class Connection:
        def execute(self, sql, _params):
            if "FROM omnix_audiobook_exports" in sql:
                assert "a.created_at" in sql
                assert "a.workspace_id = e.workspace_id" in sql
                return SimpleNamespace(fetchall=lambda: [("export", "mp3", "hash", "asset", export_date, 3, asset_date)])
            return SimpleNamespace(fetchone=lambda: (1,))

    @contextmanager
    def work(_database):
        yield SimpleNamespace(connection=Connection(), rollback=lambda: None)

    monkeypatch.setattr("app.audiobook.service.unit_of_work", work)
    result = AudiobookService(None, None).list_exports(local_tenant_context(), "book")
    assert result[0]["created_at"] == export_date.isoformat()
    assert result[0]["asset_created_at"] == asset_date.isoformat()
