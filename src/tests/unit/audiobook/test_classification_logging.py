from __future__ import annotations

import json

from app.audiobook import annotation
from app.audiobook.classification_logging import classification_log
from app.audiobook.extraction import extract_source


def test_classification_log_writes_bounded_jsonl(monkeypatch, tmp_path) -> None:
    path = tmp_path / "audiobook" / "classifications.jsonl"
    monkeypatch.setenv("OMNIX_AUDIOBOOK_CLASSIFICATION_LOG_PATH", str(path))

    classification_log(
        "unit_test",
        project_id="book:test",
        raw_response="x" * 20_000,
        span_ids=["span-1"],
    )

    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["event"] == "unit_test"
    assert record["project_id"] == "book:test"
    assert record["span_ids"] == ["span-1"]
    assert record["raw_response"].endswith("…<truncated>")
    assert len(record["raw_response"]) < 20_000


def test_batch_classification_logs_request_response_and_fallback(monkeypatch) -> None:
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        annotation,
        "classification_log",
        lambda event, **details: events.append((event, details)),
    )
    revision = extract_source(
        project_id="book:logging",
        content=b'"Hello," said Nita.\n',
        source_format="txt",
    )

    def classifier(_context):
        return {
            "characters": [],
            "spans": [],
        }

    annotation.annotate_span_batches(
        project_id="book:logging",
        spans=revision.chapters[0].spans,
        speakers=[],
        classifier=classifier,
        log_context={"job_id": "job:logging"},
    )

    names = [event for event, _details in events]
    assert "classification_batch_request" in names
    assert "classification_batch_response" in names
    assert "classification_batch_parse_failed" in names
    assert "classification_batch_fallback" in names
    assert "classification_batches_completed" in names
    request = next(details for event, details in events
                   if event == "classification_batch_request")
    assert request["job_id"] == "job:logging"
    assert request["request"]["spans"][0]["source_text"] == '"Hello,"'
