"""Leased audiobook worker entrypoint; production work never runs at job creation."""
from __future__ import annotations

import logging
import time
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


_LOG = logging.getLogger(__name__)


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
            work.jobs.create_job_once(context, {
                "id": f"ab:analyze:{text_hash(revision.id)}", "module": "audiobook",
                "job_type": "audiobook.analyze", "resource_class": "cpu",
                "input_payload": {"project_id": payload["project_id"],
                                  "source_revision_id": revision.id},
                "max_attempts": 3,
            })
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
    try:
        with unit_of_work(database) as work:
            current = work.jobs.get_job(context, job_id)
            if current["status"] == "cancel_requested":
                work.jobs.acknowledge_cancel(
                    context, job_id=job_id, worker_id=worker_id, lease_token=token,
                )
            else:
                result = PostgresAudiobookAnalysisRepository(work.connection).prepare_review(
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
    except Exception as exc:
        _LOG.exception("Audiobook analysis failed for job %s", job_id)
        with unit_of_work(database) as work:
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
                    and not run_assemble_once(database, blobs, context, worker_id=worker_id)):
                time.sleep(1.0)
        except Exception:
            _LOG.exception("Audiobook ingest worker error")
            time.sleep(5.0)


if __name__ == "__main__":
    main()
