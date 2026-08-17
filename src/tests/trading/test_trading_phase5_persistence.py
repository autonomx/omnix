from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.persistence.errors import RevisionConflict
from app.trading.api import create_trading_router


class RevisionedRepository:
    def __init__(self) -> None:
        self.records = {
            ("watchlist", "default"): {
                "record_type": "watchlist",
                "record_id": "default",
                "payload": {"name": "Default", "instrumentIds": ["btc"]},
                "revision": 2,
                "status": "active",
                "updated_at": "2026-08-05T00:00:00+00:00",
            }
        }

    def list(self, record_type: str, *, limit: int = 100):
        return [record for (kind, _), record in self.records.items() if kind == record_type and record["status"] == "active"][:limit]

    def get(self, record_type: str, record_id: str):
        return self.records.get((record_type, record_id))

    def create(self, record_type: str, record_id: str, payload: dict):
        record = {
            "record_type": record_type,
            "record_id": record_id,
            "payload": payload,
            "revision": 1,
            "status": "active",
            "updated_at": "2026-08-05T00:00:00+00:00",
        }
        self.records[(record_type, record_id)] = record
        return record

    def update(self, record_type: str, record_id: str, payload: dict, *, expected_revision: int):
        current = self.records[(record_type, record_id)]
        if current["revision"] != expected_revision:
            raise RevisionConflict("revision mismatch")
        current = {**current, "payload": payload, "revision": expected_revision + 1}
        self.records[(record_type, record_id)] = current
        return current

    def archive(self, record_type: str, record_id: str, *, expected_revision: int):
        current = self.records[(record_type, record_id)]
        if current["revision"] != expected_revision or current["status"] != "active":
            raise RevisionConflict("revision mismatch")
        current = {**current, "status": "archived", "revision": expected_revision + 1}
        self.records[(record_type, record_id)] = current
        return current


class EmptyMarketService:
    def diagnostics(self):
        return {}


def test_watchlist_archive_requires_current_revision() -> None:
    repository = RevisionedRepository()
    app = FastAPI()
    app.include_router(create_trading_router(lambda: repository, lambda: EmptyMarketService()))
    client = TestClient(app)

    conflict = client.delete("/api/trading/watchlists/default", headers={"If-Match": "1"})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["current_revision"] == 2

    archived = client.delete("/api/trading/watchlists/default", headers={"If-Match": "2"})
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["revision"] == 3
    assert client.get("/api/trading/watchlists").json()["records"] == []
