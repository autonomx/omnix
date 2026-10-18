"""Directed delivery notes and book/character performance against PostgreSQL."""
from __future__ import annotations

import os

import pytest

from app.apps.audiobook.analysis_repository import PostgresAudiobookAnalysisRepository
from app.apps.audiobook.annotation import SpanAnnotation
from app.apps.audiobook.performance_direction import queue_after_classification, run_direction_once
from app.apps.audiobook.review_repository import PostgresAudiobookReviewRepository
from app.apps.audiobook.service import AudiobookService
from app.apps.audiobook.worker import run_analyze_once, run_ingest_once
from app.persistence.blob_store import LocalBlobStore
from app.persistence.config import DatabaseSettings
from app.persistence.database import PostgresDatabase
from app.persistence.identity_service import ensure_local_identity
from app.persistence.migrations import apply_migrations
from app.persistence.unit_of_work import unit_of_work

pytestmark = pytest.mark.skipif(
    not os.environ.get("OMNIX_TEST_DATABASE_URL"),
    reason="OMNIX_TEST_DATABASE_URL is required for PostgreSQL integration tests",
)

SOURCE = b'Chapter 1\n"Get out!" Ann shouted at him.\n"Make me," Bob said with a grin.\n"Please go," Ann whispered.\n'


def _build_book(tmp_path, monkeypatch, *, resolve: bool):
    monkeypatch.setattr("app.apps.audiobook.worker.local_classifier", lambda: None)
    monkeypatch.setattr("app.apps.audiobook.service.assert_model_revision", lambda *_args: None)
    database = PostgresDatabase(DatabaseSettings(
        url=os.environ["OMNIX_TEST_DATABASE_URL"], pool_min=1, pool_max=3,
        connect_timeout_seconds=10, statement_timeout_ms=30_000,
        lock_timeout_ms=5_000, application_name="omnix-audiobook-performance-test",
    ))
    apply_migrations(database)
    context = ensure_local_identity(database)
    blobs = LocalBlobStore(tmp_path)
    service = AudiobookService(database, blobs)
    project = service.create_project(context, title="Performance Book")
    service.submit_source(context, project_id=project["id"], source_format="txt", content=SOURCE,
                          filename="performance.txt")
    assert run_ingest_once(database, blobs, context, worker_id="test:performance-ingest")
    with unit_of_work(database) as work:
        revision = work.connection.execute(
            "SELECT current_source_revision_id FROM omnix_audiobook_projects WHERE workspace_id = %s AND id = %s",
            (context.workspace_id, project["id"]),
        ).fetchone()[0]
        work.jobs.create_job(context, {
            "id": f"ab:test:classify:{project['id']}", "module": "audiobook", "job_type": "audiobook.analyze",
            "resource_class": "cpu", "input_payload": {"project_id": project["id"], "source_revision_id": str(revision)},
        })
        work.commit()
    assert run_analyze_once(database, context, worker_id="test:performance-analyze")
    ann = service.add_speaker(context, project_id=project["id"], canonical_name="Ann")["id"]
    bob = service.add_speaker(context, project_id=project["id"], canonical_name="Bob")["id"]
    chapter_id = service.get_project(context, project["id"])["chapters"][0]["id"]
    chapter = service.get_chapter(context, project_id=project["id"], chapter_id=chapter_id)
    dialogue = [span for span in chapter["spans"] if span["structural_kind"] == "dialogue"]
    assert len(dialogue) == 3
    speakers = {dialogue[0]["id"]: ann, dialogue[1]["id"]: bob, dialogue[2]["id"]: ann}
    for issue in (service.get_project(context, project["id"])["review_issues"] if resolve else []):
        speaker = speakers.get(issue["span_id"])
        narrator = next(item for item in service.get_project(context, project["id"])["speakers"]
                        if item["kind"] == "narrator")["id"]
        service.resolve_issue(context, project_id=project["id"], issue_id=issue["id"],
                              speaker_id=speaker or narrator, role="dialogue" if speaker else issue["structural_kind"])
    return database, blobs, context, service, project["id"], chapter_id, [span["id"] for span in dialogue], ann, bob


@pytest.fixture
def book(tmp_path, monkeypatch):
    built = _build_book(tmp_path, monkeypatch, resolve=True)
    try:
        yield built
    finally:
        built[0].close()


@pytest.fixture
def classified_book(tmp_path, monkeypatch):
    """Speakers set by the classifier, not by the user: re-classification may change them."""
    built = _build_book(tmp_path, monkeypatch, resolve=False)
    try:
        yield built
    finally:
        built[0].close()


def _direct(database, blobs, context, service, project_id, factory):
    """Request directing and run jobs until this project's job is done (others may share the database)."""
    job_id = service.direct_performance(context, project_id=project_id)["job_id"]
    for _ in range(10):
        run_direction_once(database, blobs, context, worker_id="test:direct", director_factory=factory)
        with unit_of_work(database) as work:
            status = work.jobs.get_job(context, job_id)["status"]
            work.rollback()
        if status not in {"queued", "waiting", "retrying", "leased", "running"}:
            return status
    raise AssertionError("the direction job did not run")


def _annotations(service, context, project_id, chapter_id):
    chapter = service.get_chapter(context, project_id=project_id, chapter_id=chapter_id)
    return {span["id"]: span["annotation"] for span in chapter["spans"] if span["annotation"]}


def test_directions_fill_dialogue_and_never_replace_what_the_user_wrote(book):
    database, blobs, context, service, project_id, chapter_id, (first, second, third), ann, _bob = book
    service.revise_span(context, project_id=project_id, span_id=third, speaker_id=ann, role="dialogue",
                        delivery="barely a whisper")
    before = _annotations(service, context, project_id, chapter_id)
    answers = {first: "Furious, Shouting", second: "mocking", third: "pleading"}

    def factory():
        def director(request):
            return {"directions": [{"span_id": span_id, "delivery": answers[span_id]}
                                   for span_id in request["target_span_ids"]]}
        return director, {"version": "test-director", "provider_id": "fake", "model": None}

    with unit_of_work(database) as work:
        queued = queue_after_classification(work, context, project_id=project_id,
                                            source_revision_id=service.get_project(context, project_id)["current_source_revision_id"],
                                            selected_engine=lambda: "fish-s2-pro")
        work.commit()
    with pytest.raises(ValueError, match="already being directed"):
        service.direct_performance(context, project_id=project_id)
    service.cancel_job(context, project_id=project_id, job_id=queued)
    assert _direct(database, blobs, context, service, project_id, factory) == "completed"

    after = _annotations(service, context, project_id, chapter_id)
    assert after[first]["delivery"] == "furious, shouting"
    assert after[second]["delivery"] == "mocking"
    assert after[third]["delivery"] == "barely a whisper"  # The user's note stays.
    # A directed revision keeps everything else, including the user's decision status.
    assert after[first]["revision"] == before[first]["revision"] + 1
    assert after[first]["review_status"] == before[first]["review_status"] == "user_resolved"
    assert after[first]["speaker_id"] == before[first]["speaker_id"]
    assert after[first]["evidence"]["delivery_source"] == "performance_director"
    job = next(item for item in service.get_project(context, project_id)["pipeline_jobs"]
               if item["type"] == "audiobook.direct-performance")
    assert job["status"] == "completed"
    assert job["progress"]["changed"] == 2 and job["progress"]["kept_user_delivery"] == 1

    # Directing again replaces earlier directions, including clearing a line now judged plain.
    answers.update({first: "neutral", second: "mocking"})
    assert _direct(database, blobs, context, service, project_id, factory) == "completed"
    again = _annotations(service, context, project_id, chapter_id)
    assert again[first]["delivery"] == ""
    assert again[second]["revision"] == after[second]["revision"]  # Unchanged: no new revision.


def test_book_and_character_performance_are_pinned_into_render_jobs(book):
    database, _blobs, context, service, project_id, _chapter_id, _spans, ann, bob = book
    with unit_of_work(database) as work:
        review = PostgresAudiobookReviewRepository(work.connection)
        for speaker in service.get_project(context, project_id)["speakers"]:
            review.assign_voice(context, project_id=project_id, speaker_id=speaker["id"],
                                voice_profile_id="voice-cloning:test", voice_revision_hash="a" * 64)
        work.commit()

    with pytest.raises(ValueError, match="unknown speaker"):
        service.set_performance(context, project_id=project_id,
                                performance={"speakers": {"00000000-0000-0000-0000-000000000000": {"stability": 0.1}}})
    stored = service.set_performance(context, project_id=project_id, performance={
        "stability": 0.5, "style": 0.35, "speakers": {ann: {"stability": 0.0, "style": 1.0}, bob: {}},
    })
    assert stored["changed"] is True
    assert service.get_project(context, project_id)["performance"] == {
        "stability": 0.5, "style": 0.35, "speakers": {ann: {"stability": 0.0, "style": 1.0}},
    }

    result = service.start_render(context, project_id=project_id, provider_id="fish-s2-pro",
                                  model_id="Fish-Audio-S2-Pro", model_revision="sha256:test")
    with unit_of_work(database) as work:
        job = work.jobs.get_job(context, result["job_ids"][0])
        work.rollback()
    payload = job["input_payload"]
    assert payload["generation_parameters"] == {"temperature": 0.8}
    assert payload["speaker_generation_parameters"] == {ann: {"temperature": 1.0, "top_p": 0.95}}

    # Saving the same performance again changes nothing; a new one drops the render run.
    assert service.set_performance(context, project_id=project_id, performance={
        "stability": 0.5, "speakers": {ann: {"stability": 0.0, "style": 1.0}},
    })["changed"] is False
    service.set_performance(context, project_id=project_id, performance={})
    with unit_of_work(database) as work:
        assert work.jobs.get_job(context, result["job_ids"][0])["status"] in {"canceled", "cancel_requested"}
        work.rollback()


def _reclassify(database, context, project_id, assignments):
    with unit_of_work(database) as work:
        revision = work.connection.execute(
            "SELECT current_source_revision_id FROM omnix_audiobook_projects WHERE workspace_id = %s AND id = %s",
            (context.workspace_id, project_id),
        ).fetchone()[0]
        PostgresAudiobookAnalysisRepository(work.connection).prepare_review(
            context, project_id=project_id, source_revision_id=str(revision), force_reclassify=True,
            classifier={"mode": "test_classifier"},
            annotations={span_id: SpanAnnotation(span_id, "dialogue", speaker, None, "", None, {})
                         for span_id, speaker in assignments.items()},
        )
        work.commit()


def test_reclassifying_keeps_a_direction_while_its_line_keeps_its_speaker(classified_book):
    database, _blobs, context, service, project_id, chapter_id, (first, second, third), ann, bob = classified_book
    _reclassify(database, context, project_id, {first: ann, second: bob, third: ann})
    with unit_of_work(database) as work:
        PostgresAudiobookReviewRepository(work.connection).apply_performance_directions(
            context, project_id=project_id, directions={first: "furious", second: "mocking"},
            director={"version": "test-director"},
        )
        work.commit()

    # Bob's line is re-assigned to Ann; Ann's first line keeps its speaker.
    _reclassify(database, context, project_id, {first: ann, second: ann, third: ann})

    current = _annotations(service, context, project_id, chapter_id)
    assert current[first]["delivery"] == "furious"
    assert current[first]["evidence"]["delivery_source"] == "performance_director"
    assert current[second]["delivery"] == ""  # Written for Bob: dropped with the new speaker.
    assert current[second]["speaker_id"] == ann


def test_classification_queues_directing_by_the_books_policy(book):
    database, _blobs, context, service, project_id, _chapter_id, _spans, _ann, _bob = book
    revision = service.get_project(context, project_id)["current_source_revision_id"]

    def queue(engine):
        with unit_of_work(database) as work:
            job_id = queue_after_classification(work, context, project_id=project_id,
                                                source_revision_id=revision, selected_engine=lambda: engine)
            work.commit()
        return job_id

    assert service.get_project(context, project_id)["auto_direct_performance"] == "fish"
    assert queue("faster-qwen3-tts") is None  # Default: only while Fish speaks the directions.
    first = queue("fish-s2-pro")
    assert first is not None
    assert queue("fish-s2-pro") is None  # Already directing.
    service.cancel_job(context, project_id=project_id, job_id=first)

    service.set_auto_direct(context, project_id=project_id, policy="never")
    assert queue("fish-s2-pro") is None
    service.set_auto_direct(context, project_id=project_id, policy="always")
    assert service.get_project(context, project_id)["auto_direct_performance"] == "always"
    leftover = queue("faster-qwen3-tts")
    assert leftover is not None
    service.cancel_job(context, project_id=project_id, job_id=leftover)  # Leave no work for other tests.
    with pytest.raises(ValueError):
        service.set_auto_direct(context, project_id=project_id, policy="sometimes")
