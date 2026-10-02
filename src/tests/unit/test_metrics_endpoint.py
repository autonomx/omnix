"""Gateway metrics: catalog, bounded labels and access (WP-10.3)."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.observability.metrics import HttpMetricsMiddleware, exposition, request_snapshot, status_class
from app.security.permissions import kernel_defaults_for

CATALOG = (
    "omnix_http_requests_total",
    "omnix_http_request_duration_seconds_bucket",
    "omnix_http_requests_in_flight",
)


def _text() -> str:
    body, content_type = exposition()
    assert content_type.startswith("text/plain")
    return body.decode()


def test_requests_are_labelled_by_route_template_and_status_class() -> None:
    app = FastAPI()

    @app.get("/metrics-probe/{item_id}")
    def item(item_id: str) -> dict:
        return {"id": item_id}

    app.add_middleware(HttpMetricsMiddleware)
    client = TestClient(app)
    before = request_snapshot()["request_count"]
    for item_id in ("one", "two", "three"):
        assert client.get(f"/metrics-probe/{item_id}").status_code == 200
    assert client.get("/metrics-probe-missing/raw-path-123").status_code == 404

    text = _text()
    assert 'route="/metrics-probe/{item_id}"' in text
    assert "one" not in text and "raw-path-123" not in text
    assert 'route="unmatched"' in text and 'status_class="4xx"' in text
    assert request_snapshot()["request_count"] - before == 4


def test_status_classes_are_bounded() -> None:
    assert [status_class(code) for code in (101, 204, 302, 404, 503, 999, 0)] == [
        "1xx", "2xx", "3xx", "4xx", "5xx", "5xx", "1xx",
    ]


def test_the_gateway_serves_the_catalog_to_metrics_admins(tmp_path: Path, monkeypatch) -> None:
    from app.gateway.main import create_gateway_app
    from app.persistence import runtime
    from tests.support.in_memory_jobs import InMemoryJobStore

    monkeypatch.setattr(runtime, "uses_postgresql_runtime", lambda: False)
    app = create_gateway_app(job_store_factory=lambda: InMemoryJobStore(tmp_path / "jobs.sqlite"))
    client = TestClient(app, base_url="http://127.0.0.1")
    assert client.get("/api/health").status_code == 200

    response = client.get("/metrics")

    assert response.status_code == 200
    assert all(name in response.text for name in CATALOG)
    assert 'route="/api/health"' in response.text
    assert kernel_defaults_for("/metrics") == ("admin:metrics", "admin:metrics")


def test_job_queue_gauges_come_from_the_snapshot() -> None:
    from app.observability.metrics import DurableStateCollector

    snapshot = {
        "active": [
            {"job_type": "image.generate", "status": "queued", "count": 3,
             "oldest_waiting_age_seconds": 42.5, "expired_leases": 0},
            {"job_type": "image.generate", "status": "running", "count": 1,
             "oldest_waiting_age_seconds": 0.0, "expired_leases": 1},
        ],
        "dead_letter_count": 2,
        "outbox": {"unpublished": 4, "oldest_unpublished_age_seconds": 1.5, "dead_letters": 0},
    }

    body, _ = exposition(DurableStateCollector(lambda: snapshot))
    text = body.decode()

    assert "omnix_jobs_snapshot_up 1.0" in text
    assert 'omnix_jobs_active{job_type="image.generate",status="queued"} 3.0' in text
    assert 'omnix_jobs_oldest_waiting_age_seconds{job_type="image.generate"} 42.5' in text
    assert 'omnix_jobs_expired_leases{job_type="image.generate"} 1.0' in text
    assert "omnix_job_dead_letters 2.0" in text
    assert "omnix_outbox_unpublished 4.0" in text
    assert "omnix_outbox_oldest_unpublished_age_seconds 1.5" in text
    assert "omnix_http_requests_in_flight" in text


def test_a_failed_job_snapshot_reports_down_without_the_error_text(caplog) -> None:
    from app.observability.metrics import DurableStateCollector

    def unavailable():
        raise OSError("postgresql://user:secret@db/omnix")

    body, _ = exposition(DurableStateCollector(unavailable))

    assert "omnix_jobs_snapshot_up 0.0" in body.decode()
    assert "secret" not in body.decode() and "secret" not in caplog.text


def test_pool_metrics_are_this_process_gauges_and_counters() -> None:
    from app.observability.metrics import PoolCollector

    stats = {"pool_size": 4, "pool_used": 3, "pool_max": 10, "requests_waiting": 1,
             "requests_num": 120, "requests_wait_ms": 2500, "requests_errors": 2, "connections_lost": 0}

    text = exposition(PoolCollector(lambda: stats))[0].decode()

    assert "omnix_db_pool_in_use 3.0" in text
    assert "omnix_db_pool_requests_waiting 1.0" in text
    assert "omnix_db_pool_requests_total 120.0" in text
    assert "omnix_db_pool_request_wait_seconds_total 2.5" in text
    assert "omnix_db_pool_request_errors_total 2.0" in text
    assert "omnix_db_pool_size" not in exposition(PoolCollector(dict))[0].decode()
