"""Leased audiobook worker entrypoint; production work never runs at job creation."""
from __future__ import annotations

import logging
import time
from typing import Any
from uuid import uuid4

from app.persistence.blob_store import LocalBlobStore
from app.persistence.database import PostgresDatabase, default_database
from app.persistence.identity_service import bootstrap_local_tenant
from app.persistence.runtime import ensure_postgresql_runtime_ready
from app.persistence.tenant import TenantContext
from app.persistence.unit_of_work import unit_of_work

from .extraction import UnsupportedSource, extract_source
from .analysis_repository import PostgresAudiobookAnalysisRepository
from .hashing import text_hash
from .repository import PostgresAudiobookRepository
from .assembly_service import run_assemble_once
from .export_service import run_export_once
from .annotation import (
    Speaker, SpeakerAlias, SpanAnnotation, annotate_span_batches, narrator_id,
    normalize_speaker_name, proposed_speaker_id,
)
from .classifier import local_classifier
from .models import SourceSpan


_LOG = logging.getLogger(__name__)

class _AnalysisPaused(Exception):
    """Internal signal used after an analysis lease is safely paused."""


class _AnalysisCanceled(Exception):
    """Internal signal used after an analysis cancellation is acknowledged."""


def _pause_analysis_if_requested(
    work: Any, context: TenantContext, *, job_id: str,
    worker_id: str, lease_token: str,
) -> bool:
    """Release an analysis lease when the UI requested a safe pause."""
    current = work.jobs.get_job(context, job_id)
    if not current or current["status"] == "cancel_requested":
        return False
    if not bool((current.get("metadata") or {}).get("pause_requested")):
        return False
    row = work.connection.execute(
        """UPDATE omnix_jobs
              SET status = 'paused', lease_owner = NULL, lease_token = NULL,
                  lease_expires_at = NULL,
                  metadata = (metadata - 'pause_requested') || %s::jsonb,
                  updated_at = CURRENT_TIMESTAMP
            WHERE workspace_id = %s AND id = %s
              AND lease_owner = %s AND lease_token = %s
              AND status IN ('leased', 'running')
        RETURNING id""",
        ('{"paused":true}', context.workspace_id, job_id, worker_id, lease_token),
    ).fetchone()
    if row is None:
        return False
    work.connection.execute(
        """UPDATE omnix_job_attempts SET status = 'paused'
            WHERE job_id = %s AND lease_token = %s AND status IN ('leased', 'running')""",
        (job_id, lease_token),
    )
    return True


def run_ingest_once(
    database: PostgresDatabase, blobs: LocalBlobStore, context: TenantContext,
    *, worker_id: str,
) -> bool:
    with unit_of_work(database) as work:
        job = work.jobs.claim_next(
            context, worker_id=worker_id, resource_classes=["cpu"],
            job_types=["audiobook.ingest"], lease_seconds=3600,
        )
        if job is None:
            work.rollback()
            return False
        job = work.jobs.mark_running(
            context, job_id=job["id"], worker_id=worker_id, lease_token=job["lease_token"],
        )
        work.commit()
    job_id = job["id"]
    token = job["lease_token"]
    payload = job["input_payload"]
    try:
        with unit_of_work(database) as work:
            row = work.connection.execute(
                """
                SELECT storage_key, checksum_sha256 FROM omnix_assets
                 WHERE workspace_id = %s AND id = %s AND lifecycle_status = 'active'
                """, (context.workspace_id, payload["source_asset_id"]),
            ).fetchone()
            work.rollback()
        if row is None:
            raise UnsupportedSource("source asset is missing")
        content = blobs.read_bytes(str(row[0]), expected_checksum=str(row[1]))
        revision = extract_source(
            project_id=payload["project_id"], content=content,
            source_format=payload["source_format"],
            settings=payload.get("extraction_settings"),
        )
        with unit_of_work(database) as work:
            work.jobs.renew_lease(
                context, job_id=job_id, worker_id=worker_id,
                lease_token=token, lease_seconds=3600,
            )
            current = work.jobs.get_job(context, job_id)
            if current["status"] == "cancel_requested":
                work.jobs.acknowledge_cancel(
                    context, job_id=job_id, worker_id=worker_id, lease_token=token,
                )
                work.commit()
                return True
            PostgresAudiobookRepository(work.connection).append_source_revision(
                context, revision, original_asset_id=payload["source_asset_id"],
            )
            analysis_input = {
                "project_id": payload["project_id"],
                "source_revision_id": revision.id,
            }
            if bool(payload.get("force_reclassify")):
                analysis_input["force_reclassify"] = True
            analysis_payload = {
                "id": f"ab:analyze:{text_hash(revision.id)}", "module": "audiobook",
                "job_type": "audiobook.analyze", "resource_class": "cpu",
                "input_payload": analysis_input,
                "metadata": (
                    {"reason": "user_requested_reclassification"}
                    if bool(payload.get("force_reclassify")) else {}
                ),
                "max_attempts": 3,
            }
            analysis_job, _created = work.jobs.create_job_once(context, analysis_payload)
            if analysis_job["status"] in {"failed", "canceled", "stale"}:
                # Re-submitting identical source bytes must recover a terminal
                # analysis attempt without mutating the canonical revision.
                retry_id = f"ab:analyze-retry:{uuid4().hex}"
                work.jobs.create_job(context, {
                    **analysis_payload,
                    "id": retry_id,
                    "metadata": {"retry_of": analysis_job["id"]},
                })
                work.connection.execute(
                    """UPDATE omnix_jobs
                          SET metadata = metadata || %s::jsonb,
                              updated_at = CURRENT_TIMESTAMP
                        WHERE workspace_id = %s AND id = %s""",
                    ('{"superseded_by":"' + retry_id + '"}',
                     context.workspace_id, analysis_job["id"]),
                )
            work.jobs.complete(
                context, job_id=job_id, worker_id=worker_id, lease_token=token,
                output_refs=[{"source_revision_id": revision.id}],
                progress={"current": 1, "total": 1, "message": "canonical source verified"},
            )
            work.commit()
    except Exception as exc:
        _LOG.exception("Audiobook source ingestion failed for job %s", job_id)
        with unit_of_work(database) as work:
            work.jobs.fail(
                context, job_id=job_id, worker_id=worker_id, lease_token=token,
                error={"code": "source_invalid" if isinstance(exc, UnsupportedSource) else "ingest_failed",
                       "message": str(exc), "retryable": not isinstance(exc, UnsupportedSource)},
            )
            work.commit()
    return True


def run_analyze_once(
    database: PostgresDatabase, context: TenantContext, *, worker_id: str,
) -> bool:
    with unit_of_work(database) as work:
        job = work.jobs.claim_next(
            context, worker_id=worker_id, resource_classes=["cpu"],
            job_types=["audiobook.analyze"], lease_seconds=3600,
        )
        if job is None:
            work.rollback()
            return False
        job = work.jobs.mark_running(
            context, job_id=job["id"], worker_id=worker_id, lease_token=job["lease_token"],
        )
        work.commit()
    job_id, token = job["id"], job["lease_token"]
    payload = job["input_payload"]
    force_reclassify = bool(payload.get("force_reclassify"))
    try:
        with unit_of_work(database) as work:
            chapters = work.connection.execute(
                """SELECT c.id, count(s.id)
                     FROM omnix_audiobook_chapters c
                     LEFT JOIN omnix_audiobook_spans s
                       ON s.workspace_id = c.workspace_id AND s.chapter_id = c.id
                    WHERE c.workspace_id = %s AND c.source_revision_id = %s
                    GROUP BY c.id, c.ordinal ORDER BY c.ordinal""",
                (context.workspace_id, payload["source_revision_id"]),
            ).fetchall()
            speaker_rows = work.connection.execute(
                """SELECT id, canonical_name, kind, status
                     FROM omnix_audiobook_speakers
                    WHERE workspace_id = %s AND project_id = %s
                      AND status IN ('active', 'proposed')""",
                (context.workspace_id, payload["project_id"]),
            ).fetchall()
            alias_rows = work.connection.execute(
                """SELECT alias, speaker_id, status
                     FROM omnix_audiobook_speaker_aliases
                    WHERE workspace_id = %s AND project_id = %s
                      AND status IN ('confirmed', 'proposed')""",
                (context.workspace_id, payload["project_id"]),
            ).fetchall()
            work.rollback()
        speakers = [
            Speaker(str(row[0]), str(row[1]), str(row[2]), str(row[3]))
            for row in speaker_rows
        ]
        if not any(item.id == narrator_id(payload["project_id"]) for item in speakers):
            speakers.append(Speaker(narrator_id(payload["project_id"]), "Narrator", "narrator"))
        aliases = [SpeakerAlias(str(row[0]), str(row[1]), str(row[2])) for row in alias_rows]
        classifier = local_classifier()
        if force_reclassify and classifier is None:
            raise ValueError(
                "text reclassification requires a configured chat provider; "
                "no classifier was available, so the existing review state was preserved"
            )
        total_spans = sum(int(row[1]) for row in chapters)
        completed_spans = 0
        chapter_classified_spans: set[str] = set()

        def checkpoint_classification_progress(span_ids: object) -> None:
            """Persist span-level progress while a chapter is being classified."""
            if isinstance(span_ids, str):
                candidate_ids = [span_ids]
            elif isinstance(span_ids, (list, tuple)):
                candidate_ids = [
                    item for item in span_ids if isinstance(item, str) and item
                ]
            else:
                candidate_ids = []
            new_ids = [
                item for item in candidate_ids
                if item not in chapter_classified_spans
            ]
            if not new_ids:
                return
            chapter_classified_spans.update(new_ids)
            with unit_of_work(database) as progress_work:
                current = progress_work.jobs.get_job(context, job_id)
                if current["status"] == "cancel_requested":
                    progress_work.jobs.acknowledge_cancel(
                        context, job_id=job_id, worker_id=worker_id, lease_token=token,
                    )
                    progress_work.commit()
                    raise _AnalysisCanceled
                if _pause_analysis_if_requested(
                    progress_work, context, job_id=job_id,
                    worker_id=worker_id, lease_token=token,
                ):
                    progress_work.commit()
                    raise _AnalysisPaused
                progress_work.jobs.update_progress(
                    context, job_id=job_id, worker_id=worker_id,
                    lease_token=token,
                    progress={
                        "current": completed_spans + len(chapter_classified_spans),
                        "total": total_spans,
                        "message": "analyzing chapters",
                    },
                )
                progress_work.commit()

        def classify(context_payload: dict[str, object]) -> str | dict[str, Any]:
            with unit_of_work(database) as renewal:
                renewal.jobs.renew_lease(
                    context, job_id=job_id, worker_id=worker_id,
                    lease_token=token, lease_seconds=3600,
                )
                renewal.commit()
            try:
                return classifier[0](context_payload)
            finally:
                checkpoint_classification_progress(
                    context_payload.get("span_ids")
                    or context_payload.get("span_id")
                )

        for chapter_id, span_count in chapters:
            chapter_classified_spans.clear()
            with unit_of_work(database) as work:
                current = work.jobs.get_job(context, job_id)
                if current["status"] == "cancel_requested":
                    work.jobs.acknowledge_cancel(
                        context, job_id=job_id, worker_id=worker_id, lease_token=token,
                    )
                    work.commit()
                    return True
                if _pause_analysis_if_requested(
                    work, context, job_id=job_id,
                    worker_id=worker_id, lease_token=token,
                ):
                    work.commit()
                    return True
                existing = 0
                if not force_reclassify:
                    existing = work.connection.execute(
                        """SELECT count(a.id)
                             FROM omnix_audiobook_spans s
                             JOIN omnix_audiobook_annotations a
                               ON a.workspace_id = s.workspace_id AND a.span_id = s.id
                              AND a.revision = 1
                            WHERE s.workspace_id = %s AND s.chapter_id = %s""",
                        (context.workspace_id, chapter_id),
                    ).fetchone()[0]
                if not force_reclassify and int(existing) == int(span_count):
                    completed_spans += int(span_count)
                    work.jobs.renew_lease(
                        context, job_id=job_id, worker_id=worker_id,
                        lease_token=token, lease_seconds=3600,
                    )
                    work.jobs.update_progress(
                        context, job_id=job_id, worker_id=worker_id, lease_token=token,
                        progress={"current": completed_spans, "total": total_spans,
                                  "message": "analyzing chapters"},
                    )
                    work.commit()
                    continue
                rows = work.connection.execute(
                    """SELECT id, chapter_id, ordinal, start_offset, end_offset,
                              source_text, source_hash, structural_kind, detector_version
                         FROM omnix_audiobook_spans
                        WHERE workspace_id = %s AND chapter_id = %s
                        ORDER BY ordinal""",
                    (context.workspace_id, chapter_id),
                ).fetchall()
                work.rollback()
            chapter_spans = [
                SourceSpan(str(row[0]), str(row[1]), int(row[2]), int(row[3]),
                           int(row[4]), str(row[5]), str(row[6]), str(row[7]), str(row[8]))
                for row in rows
            ]
            annotations: dict[str, SpanAnnotation] = {}
            discoveries = ()
            if classifier is not None:
                batch_analysis = annotate_span_batches(
                    project_id=payload["project_id"], spans=chapter_spans,
                    speakers=speakers, aliases=aliases, classifier=classify,
                )
                failed_dialogue = [
                    annotation
                    for annotation in batch_analysis.annotations
                    if (
                        annotation.role == "dialogue"
                        and annotation.review_reason in {
                            "FALLBACK_NARRATOR",
                            "AI_VERIFICATION_UNAVAILABLE",
                        }
                    )
                ]
                if force_reclassify and failed_dialogue:
                    raise RuntimeError(
                        "text reclassification could not classify "
                        f"{len(failed_dialogue)} dialogue spans in chapter {chapter_id}; "
                        "existing annotations for this chapter were preserved"
                    )
                discoveries = batch_analysis.discovered_speakers
                for annotation in batch_analysis.annotations:
                    annotations[annotation.span_id] = annotation

                # Carry AI-discovered identities into later chapters immediately.
                # They remain provisional metadata until user confirmation/casting,
                # but high-confidence dialogue may already reference them.
                known = {
                    normalize_speaker_name(item.canonical_name) for item in speakers
                }
                for discovery in discoveries:
                    normalized = normalize_speaker_name(discovery.canonical_name)
                    if not normalized or normalized in known:
                        continue
                    speaker = Speaker(
                        proposed_speaker_id(payload["project_id"],
                                            discovery.canonical_name),
                        discovery.canonical_name, "character", "proposed",
                    )
                    speakers.append(speaker)
                    aliases.extend(
                        SpeakerAlias(alias, speaker.id, "proposed")
                        for alias in discovery.aliases
                    )
                    known.add(normalized)
            with unit_of_work(database) as work:
                current = work.jobs.get_job(context, job_id)
                if current["status"] == "cancel_requested":
                    work.jobs.acknowledge_cancel(
                        context, job_id=job_id, worker_id=worker_id, lease_token=token,
                    )
                    work.commit()
                    return True
                if _pause_analysis_if_requested(
                    work, context, job_id=job_id,
                    worker_id=worker_id, lease_token=token,
                ):
                    work.commit()
                    return True
                analysis_repository = PostgresAudiobookAnalysisRepository(work.connection)
                if discoveries:
                    analysis_repository.register_proposed_speakers(
                        context, project_id=payload["project_id"],
                        discoveries=discoveries,
                    )
                analysis_repository.prepare_review(
                    context, project_id=payload["project_id"],
                    source_revision_id=payload["source_revision_id"],
                    annotations=annotations,
                    classifier=classifier[1] if classifier else None,
                    chapter_id=str(chapter_id), finalize=False,
                    force_reclassify=force_reclassify,
                )
                completed_spans += int(span_count)
                work.jobs.renew_lease(
                    context, job_id=job_id, worker_id=worker_id,
                    lease_token=token, lease_seconds=3600,
                )
                work.jobs.update_progress(
                    context, job_id=job_id, worker_id=worker_id, lease_token=token,
                    progress={"current": completed_spans, "total": total_spans,
                              "message": "analyzing chapters"},
                )
                work.commit()
        with unit_of_work(database) as work:
            current = work.jobs.get_job(context, job_id)
            if current["status"] == "cancel_requested":
                work.jobs.acknowledge_cancel(
                    context, job_id=job_id, worker_id=worker_id, lease_token=token,
                )
            elif _pause_analysis_if_requested(
                work, context, job_id=job_id,
                worker_id=worker_id, lease_token=token,
            ):
                work.commit()
                return True
            else:
                result = PostgresAudiobookAnalysisRepository(work.connection).finalize_review(
                    context, project_id=payload["project_id"],
                    source_revision_id=payload["source_revision_id"],
                )
                work.jobs.complete(
                    context, job_id=job_id, worker_id=worker_id, lease_token=token,
                    output_refs=[result],
                    progress={"current": result["spans"], "total": result["spans"],
                              "message": "review queue prepared"},
                )
            work.commit()
    except (_AnalysisPaused, _AnalysisCanceled):
        _LOG.info("Audiobook analysis job %s stopped by operator control", job_id)
        return True
    except Exception as exc:
        _LOG.exception("Audiobook analysis failed for job %s", job_id)
        with unit_of_work(database) as work:
            if force_reclassify:
                work.connection.execute(
                    """UPDATE omnix_audiobook_projects
                          SET state = 'review_required', updated_at = CURRENT_TIMESTAMP
                        WHERE workspace_id = %s AND id = %s
                          AND state = 'analyzing'""",
                    (context.workspace_id, payload["project_id"]),
                )
            work.jobs.fail(
                context, job_id=job_id, worker_id=worker_id, lease_token=token,
                error={"code": "analysis_failed", "message": str(exc),
                       "retryable": not isinstance(exc, ValueError)},
            )
            work.commit()
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    database = default_database()
    ensure_postgresql_runtime_ready(database)
    context = bootstrap_local_tenant(database)
    blobs = LocalBlobStore()
    worker_id = f"audiobook:ingest:{uuid4().hex}"
    while True:
        try:
            if (not run_ingest_once(database, blobs, context, worker_id=worker_id)
                    and not run_analyze_once(database, context, worker_id=worker_id)
                    and not run_assemble_once(database, blobs, context, worker_id=worker_id)
                    and not run_export_once(database, blobs, context, worker_id=worker_id)):
                time.sleep(1.0)
        except Exception:
            _LOG.exception("Audiobook ingest worker error")
            time.sleep(5.0)


if __name__ == "__main__":
    main()
