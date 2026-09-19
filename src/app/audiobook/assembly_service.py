"""Leased chapter assembly from attested, immutable render assets."""
from __future__ import annotations

import logging
from dataclasses import asdict
from uuid import uuid4

from app.persistence.blob_store import BlobIntegrityError, LocalBlobStore
from app.persistence.database import PostgresDatabase
from app.persistence.tenant import TenantContext
from app.persistence.unit_of_work import unit_of_work

from .assembly import AudioSpan, PausePolicy, assemble_chapter
from .hashing import canonical_json
from .render_cache import find_valid_render
from .render_planner import load_chapter_units


_LOG = logging.getLogger(__name__)


def run_assemble_once(
    database: PostgresDatabase, blobs: LocalBlobStore, context: TenantContext,
    *, worker_id: str,
) -> bool:
    with unit_of_work(database) as work:
        job = work.jobs.claim_next(
            context, worker_id=worker_id, resource_classes=["cpu"],
            job_types=["audiobook.assemble-chapter"], lease_seconds=3600,
        )
        if job is None:
            work.rollback()
            return False
        job = work.jobs.mark_running(
            context, job_id=job["id"], worker_id=worker_id,
            lease_token=job["lease_token"],
        )
        work.commit()
    job_id, token = job["id"], job["lease_token"]
    payload = job["input_payload"]
    storage_key: str | None = None
    blob_created = False
    persisted = False
    try:
        with unit_of_work(database) as work:
            current = work.connection.execute(
                """SELECT current_source_revision_id, settings->>'current_render_run_id'
                     FROM omnix_audiobook_projects
                    WHERE workspace_id = %s AND id = %s""",
                (context.workspace_id, payload["project_id"]),
            ).fetchone()
            if current is None or current[0] != payload["source_revision_id"] or current[1] != payload["render_run_id"]:
                raise ValueError("assembly run no longer matches the current source")
            units = load_chapter_units(
                work.connection, context, project_id=payload["project_id"],
                chapter_id=payload["chapter_id"],
            )
            spans: list[AudioSpan] = []
            render_ids: list[str] = []
            for unit in units:
                key = unit.identity(
                    provider_id=payload["provider_id"], model_id=payload["model_id"],
                    model_revision=payload["model_revision"],
                    generation_parameters=dict(payload.get("generation_parameters") or {}),
                    seed=payload.get("seed"),
                ).key()
                render = find_valid_render(work.connection, context, blobs, key)
                if render is None:
                    raise ValueError(f"render is missing or corrupt for span {unit.span_id}")
                asset = work.connection.execute(
                    """SELECT storage_key FROM omnix_assets
                        WHERE workspace_id = %s AND id = %s""",
                    (context.workspace_id, render["audio_asset_id"]),
                ).fetchone()
                if asset is None:
                    raise ValueError("render asset disappeared")
                audio = blobs.read_bytes(str(asset[0]), expected_checksum=render["audio_checksum"])
                spans.append(AudioSpan(
                    render["id"], key, unit.speaker_id,
                    unit.speech_plan.source_text, audio,
                ))
                render_ids.append(render["id"])
            work.rollback()
        result = assemble_chapter(spans, policy=PausePolicy())
        with unit_of_work(database) as work:
            cached = work.connection.execute(
                """SELECT ca.id, ca.audio_asset_id, ca.audio_checksum, a.storage_key
                     FROM omnix_audiobook_chapter_assemblies ca
                     JOIN omnix_assets a ON a.id = ca.audio_asset_id AND a.workspace_id = ca.workspace_id
                    WHERE ca.workspace_id = %s AND ca.chapter_id = %s AND ca.assembly_key = %s
                    ORDER BY ca.created_at DESC""",
                (context.workspace_id, payload["chapter_id"], result.assembly_key),
            ).fetchall()
            selected = None
            for row in cached:
                try:
                    blobs.read_bytes(str(row[3]), expected_checksum=str(row[2]))
                    selected = (str(row[0]), str(row[1]))
                    break
                except (FileNotFoundError, BlobIntegrityError, OSError):
                    continue
            work.rollback()
        if selected is None:
            asset_id = f"ab:chapter-audio:{uuid4().hex}"
            assembly_id = f"ab:assembly:{uuid4().hex}"
            storage_key = f"audiobook/chapter/{uuid4().hex}.wav"
            blob = blobs.put_bytes(storage_key, result.wav_bytes)
            blob_created = bool(blob["created"])
        with unit_of_work(database) as work:
            current_job = work.jobs.get_job(context, job_id)
            if current_job["status"] == "cancel_requested":
                work.jobs.acknowledge_cancel(
                    context, job_id=job_id, worker_id=worker_id, lease_token=token,
                )
                work.commit()
                return True
            if selected is None:
                work.assets.create(context, {
                    "id": asset_id, "module": "audiobook", "asset_type": "chapter-audio",
                    "mime_type": "audio/wav", "byte_size": blob["byte_size"],
                    "checksum_sha256": blob["checksum_sha256"],
                    "storage_provider": blob["storage_provider"], "storage_key": storage_key,
                    "generation_job_id": job_id,
                    "metadata": {"assembly_key": result.assembly_key},
                })
                work.connection.execute(
                    """INSERT INTO omnix_audiobook_chapter_assemblies
                       (id, workspace_id, chapter_id, assembly_key, render_ids,
                        audio_asset_id, audio_checksum, duration_seconds, sample_rate,
                        pause_policy, loudness, timeline)
                       VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s,
                               %s::jsonb, %s::jsonb, %s::jsonb)""",
                    (assembly_id, context.workspace_id, payload["chapter_id"],
                     result.assembly_key, canonical_json(render_ids), asset_id,
                     blob["checksum_sha256"], result.duration_seconds, result.sample_rate,
                     canonical_json(asdict(PausePolicy())),
                     canonical_json({"target_rms_dbfs": -20.0,
                                     "measured_rms_dbfs": result.measured_rms_dbfs,
                                     "applied_gain_db": result.applied_gain_db,
                                     "peak_dbfs": result.peak_dbfs}),
                     canonical_json([asdict(item) for item in result.timeline])),
                )
                selected = (assembly_id, asset_id)
            work.jobs.complete(
                context, job_id=job_id, worker_id=worker_id, lease_token=token,
                output_refs=[{"assembly_id": selected[0], "audio_asset_id": selected[1]}],
                progress={"current": 1, "total": 1, "message": "chapter assembled"},
            )
            remaining = work.connection.execute(
                """SELECT count(*) FROM omnix_jobs
                    WHERE workspace_id = %s AND job_type = 'audiobook.assemble-chapter'
                      AND input_payload->>'render_run_id' = %s AND status <> 'completed'""",
                (context.workspace_id, payload["render_run_id"]),
            ).fetchone()[0]
            if int(remaining) == 0:
                work.connection.execute(
                    """UPDATE omnix_audiobook_projects SET state = 'ready_to_export',
                              updated_at = CURRENT_TIMESTAMP
                         WHERE workspace_id = %s AND id = %s
                           AND settings->>'current_render_run_id' = %s""",
                    (context.workspace_id, payload["project_id"], payload["render_run_id"]),
                )
            work.commit()
            persisted = True
    except Exception as exc:
        _LOG.exception("Audiobook chapter assembly failed for job %s", job_id)
        with unit_of_work(database) as work:
            work.jobs.fail(
                context, job_id=job_id, worker_id=worker_id, lease_token=token,
                error={"code": "assembly_failed", "message": str(exc),
                       "retryable": not isinstance(exc, ValueError)},
            )
            work.commit()
    finally:
        if blob_created and storage_key is not None and not persisted:
            blobs.delete(storage_key)
    return True
