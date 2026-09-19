"""Resumable chapter rendering over leased coarse jobs and immutable audio assets."""
from __future__ import annotations

import base64
import io
import logging
import sys
import time
import wave
from dataclasses import asdict
from typing import Any
from uuid import uuid4

from app.assets.canonical_voice_clones import discover_canonical_voice_clone_assets
from app.persistence.blob_store import LocalBlobStore
from app.persistence.database import PostgresDatabase
from app.persistence.tenant import TenantContext
from app.persistence.unit_of_work import unit_of_work
from app.shared import get_tts_provider
from app.providers.tts_priority import generation_class, other_process_priority_pending

from .hashing import bytes_hash, canonical_json
from .render_cache import find_valid_render
from .render_planner import RenderUnit, load_chapter_units
from .model_identity import assert_model_revision


_LOG = logging.getLogger(__name__)
_HIGHER_PRIORITY = ("gpu:tts:realtime", "gpu:tts:preview", "gpu:tts")


class RenderFailure(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


def _effective_generation_parameters(provider: Any, requested: dict[str, Any]) -> dict[str, Any]:
    resolver = getattr(provider, "resolve_generation_parameters", None)
    resolved = resolver(dict(requested)) if callable(resolver) else dict(requested)
    if not isinstance(resolved, dict):
        raise RenderFailure("TTS provider returned invalid effective generation parameters",
                            retryable=False)
    return dict(resolved)


def _persist_effective_generation_parameters(
    database: PostgresDatabase, context: TenantContext, *, job_id: str,
    effective: dict[str, Any],
) -> None:
    with unit_of_work(database) as work:
        work.connection.execute(
            """UPDATE omnix_jobs
                  SET input_payload = jsonb_set(
                          input_payload, '{generation_parameters}', %s::jsonb, true
                      ),
                      updated_at = CURRENT_TIMESTAMP
                WHERE workspace_id = %s AND id = %s
                  AND module = 'audiobook'""",
            (canonical_json(effective), context.workspace_id, job_id),
        )
        work.commit()


def _gpu_memory_bytes() -> dict[str, int]:
    torch = sys.modules.get("torch")
    if torch is None:
        return {}
    try:
        if torch.cuda.is_available():
            return {"allocated": int(torch.cuda.memory_allocated()),
                    "reserved": int(torch.cuda.memory_reserved()),
                    "peak_allocated": int(torch.cuda.max_memory_allocated())}
    except (AttributeError, RuntimeError):
        pass
    return {}


def decode_pcm_wav(response: dict[str, Any]) -> tuple[bytes, float, int]:
    if not response.get("success") or response.get("is_fallback"):
        raise RenderFailure(str(response.get("error") or "TTS provider returned no valid audio"))
    try:
        content = base64.b64decode(str(response["audio"]), validate=True)
        with wave.open(io.BytesIO(content), "rb") as reader:
            frames = reader.getnframes()
            sample_rate = reader.getframerate()
            sample_width = reader.getsampwidth()
            if reader.getcomptype() != "NONE" or frames <= 0 or sample_rate <= 0 or sample_width not in {2, 3, 4}:
                raise RenderFailure("TTS output must be non-empty lossless PCM WAV", retryable=False)
            duration = frames / sample_rate
    except (KeyError, ValueError, EOFError, wave.Error, TypeError) as exc:
        raise RenderFailure("TTS output is not valid PCM WAV", retryable=True) from exc
    return content, duration, sample_rate


def higher_priority_tts_pending(connection: Any, context: TenantContext) -> bool:
    row = connection.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM omnix_jobs
             WHERE workspace_id = %s AND resource_class = ANY(%s)
               AND (
                   (status IN ('queued', 'waiting', 'retrying')
                    AND available_at <= CURRENT_TIMESTAMP
                    AND attempt_count < max_attempts)
                   OR (status IN ('leased', 'running', 'cancel_requested')
                       AND lease_expires_at > CURRENT_TIMESTAMP)
               )
        )
        """, (context.workspace_id, list(_HIGHER_PRIORITY)),
    ).fetchone()
    return bool(row[0])


def _checkpoint(
    work: Any, context: TenantContext, *, job_id: str, worker_id: str,
    lease_token: str, batch_id: str, render_key: str, completed: int, total: int,
    cache_hits: int, generated: int,
) -> None:
    work.connection.execute(
        """
        UPDATE omnix_audiobook_render_batches
           SET completed_keys = completed_keys || %s::jsonb, updated_at = CURRENT_TIMESTAMP
         WHERE workspace_id = %s AND id = %s
           AND NOT completed_keys @> %s::jsonb
        """, (canonical_json([render_key]), context.workspace_id, batch_id,
              canonical_json([render_key])),
    )
    work.jobs.renew_lease(
        context, job_id=job_id, worker_id=worker_id,
        lease_token=lease_token, lease_seconds=3600,
    )
    work.jobs.update_progress(
        context, job_id=job_id, worker_id=worker_id, lease_token=lease_token,
        progress={"current": completed, "total": total,
                  "cache_hits": cache_hits, "generated": generated,
                  "message": f"{completed}/{total} render units complete"},
    )


def _voice_for(unit: RenderUnit, profiles: dict[str, Any], provider_id: str) -> str:
    profile = profiles.get(unit.voice_profile_id)
    if profile is None or not profile.storage_path:
        raise RenderFailure(f"voice profile {unit.voice_profile_id} is unavailable", retryable=False)
    from pathlib import Path

    if bytes_hash(Path(profile.storage_path).read_bytes()) != unit.voice_revision_hash:
        raise RenderFailure(f"voice profile {unit.voice_profile_id} changed since casting", retryable=False)
    if provider_id == "faster-qwen3-tts":
        return unit.voice_profile_id
    return str(profile.metadata.get("voice_clone_id") or profile.metadata.get("voice_id") or "")


def _save_render(
    database: PostgresDatabase, blobs: LocalBlobStore, context: TenantContext, *,
    job_id: str, worker_id: str, lease_token: str, batch_id: str | None,
    unit: RenderUnit, render_key: str, provider_id: str, model_id: str,
    model_revision: str, generation_parameters: dict[str, Any], seed: int | None,
    audio: bytes, duration: float, sample_rate: int, completed: int, total: int,
    diagnostics: dict[str, Any] | None = None,
    actual_generation_parameters: dict[str, Any] | None = None,
    cache_hits: int = 0, generated: int = 1,
) -> dict[str, str]:
    asset_id = f"ab:audio:{uuid4().hex}"
    storage_key = f"audiobook/render/{asset_id.split(':')[-1]}.wav"
    blob = blobs.put_bytes(storage_key, audio)
    render_id = f"ab:render:{uuid4().hex}"
    try:
        with unit_of_work(database) as work:
            work.assets.create(context, {
                "id": asset_id, "module": "audiobook", "asset_type": "render",
                "mime_type": "audio/wav", "byte_size": blob["byte_size"],
                "checksum_sha256": blob["checksum_sha256"],
                "storage_provider": blob["storage_provider"], "storage_key": storage_key,
                "generation_job_id": job_id,
                "metadata": {"render_key": render_key, "span_id": unit.span_id},
            })
            work.connection.execute(
                """
                INSERT INTO omnix_audiobook_renders
                    (id, workspace_id, span_id, render_key, annotation_id, casting_id,
                     speech_plan_hash, tts_input_text, transformations, provider,
                     generation_settings, audio_asset_id, audio_checksum,
                     duration_seconds, sample_rate, diagnostics)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb,
                        %s::jsonb, %s, %s, %s, %s, %s::jsonb)
                """,
                (render_id, context.workspace_id, unit.span_id,
                 render_key, unit.annotation_id, unit.casting_id,
                 unit.speech_plan.hash, unit.speech_plan.tts_input_text,
                 canonical_json([asdict(item) for item in unit.speech_plan.transformations]),
                 canonical_json({"id": provider_id, "model_id": model_id,
                                 "model_revision": model_revision}),
                 canonical_json({"parameters": generation_parameters,
                                 "actual_parameters": actual_generation_parameters or generation_parameters,
                                 "seed": seed}),
                 asset_id, blob["checksum_sha256"], duration, sample_rate,
                 canonical_json({"job_id": job_id, "cache_hit": False,
                                 **(diagnostics or {})})),
            )
            if batch_id is None:
                work.jobs.complete(
                    context, job_id=job_id, worker_id=worker_id,
                    lease_token=lease_token,
                    output_refs=[{"render_id": render_id, "audio_asset_id": asset_id}],
                    progress={"current": 1, "total": 1, "message": "preview ready"},
                )
            else:
                _checkpoint(
                    work, context, job_id=job_id, worker_id=worker_id,
                    lease_token=lease_token, batch_id=batch_id, render_key=render_key,
                    completed=completed, total=total,
                    cache_hits=cache_hits, generated=generated,
                )
            work.commit()
    except Exception:
        if blob["created"]:
            blobs.delete(storage_key)
        raise
    return {"render_id": render_id, "audio_asset_id": asset_id}


def run_render_once(
    database: PostgresDatabase, blobs: LocalBlobStore, context: TenantContext,
    *, worker_id: str,
) -> bool:
    with unit_of_work(database) as work:
        if higher_priority_tts_pending(work.connection, context) or other_process_priority_pending():
            work.rollback()
            return False
        job = work.jobs.claim_next(
            context, worker_id=worker_id, resource_classes=["gpu:tts:offline"],
            job_types=["audiobook.render-chapter"], lease_seconds=3600,
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
        assert_model_revision(payload["provider_id"], payload["model_id"],
                              payload["model_revision"])
        provider = get_tts_provider(payload["provider_id"])
        if provider is None:
            raise RenderFailure(f"TTS provider {payload['provider_id']} is unavailable")
        requested_settings = dict(payload.get("generation_parameters") or {})
        settings = _effective_generation_parameters(provider, requested_settings)
        if settings != requested_settings:
            _persist_effective_generation_parameters(
                database, context, job_id=job_id, effective=settings,
            )
            payload["generation_parameters"] = settings
        with unit_of_work(database) as work:
            units = load_chapter_units(
                work.connection, context, project_id=payload["project_id"],
                chapter_id=payload["chapter_id"],
            )
            work.rollback()
        profiles = {item.id: item for item in discover_canonical_voice_clone_assets()}
        requests = [
            (unit, unit.identity(
                provider_id=payload["provider_id"], model_id=payload["model_id"],
                model_revision=payload["model_revision"],
                generation_parameters=settings, seed=payload.get("seed"),
            ).key()) for unit in units
        ]
        batch_id = f"ab:batch:{job_id}"
        with unit_of_work(database) as work:
            work.connection.execute(
                """
                INSERT INTO omnix_audiobook_render_batches
                    (id, workspace_id, chapter_id, job_id, shard_ordinal,
                     start_ordinal, end_ordinal, desired_keys)
                VALUES (%s, %s, %s, %s, 0, 0, %s, %s::jsonb)
                ON CONFLICT (chapter_id, job_id, shard_ordinal)
                DO UPDATE SET desired_keys = EXCLUDED.desired_keys, updated_at = CURRENT_TIMESTAMP
                """, (batch_id, context.workspace_id, payload["chapter_id"], job_id,
                      max(1, len(requests)), canonical_json([key for _, key in requests])),
            )
            work.commit()
        completed = 0
        cache_hits = 0
        generated = 0
        for unit, key in requests:
            assert_model_revision(payload["provider_id"], payload["model_id"],
                                  payload["model_revision"])
            with unit_of_work(database) as work:
                current = work.jobs.get_job(context, job_id)
                if current["status"] == "cancel_requested":
                    work.jobs.acknowledge_cancel(
                        context, job_id=job_id, worker_id=worker_id, lease_token=token,
                    )
                    work.commit()
                    return True
                cached = find_valid_render(work.connection, context, blobs, key)
                if cached is not None:
                    completed += 1
                    cache_hits += 1
                    _checkpoint(
                        work, context, job_id=job_id, worker_id=worker_id,
                        lease_token=token, batch_id=batch_id, render_key=key,
                        completed=completed, total=len(requests),
                        cache_hits=cache_hits, generated=generated,
                    )
                    work.commit()
                    continue
                work.rollback()
            while True:
                with unit_of_work(database) as work:
                    current = work.jobs.get_job(context, job_id)
                    if current["status"] == "cancel_requested":
                        work.jobs.acknowledge_cancel(
                            context, job_id=job_id, worker_id=worker_id, lease_token=token,
                        )
                        work.commit()
                        return True
                    busy = (higher_priority_tts_pending(work.connection, context)
                            or other_process_priority_pending())
                    work.jobs.renew_lease(
                        context, job_id=job_id, worker_id=worker_id,
                        lease_token=token, lease_seconds=3600,
                    )
                    work.commit()
                if not busy:
                    break
                time.sleep(0.5)
            with unit_of_work(database) as work:
                cached = find_valid_render(work.connection, context, blobs, key)
                if cached is not None:
                    completed += 1
                    cache_hits += 1
                    _checkpoint(
                        work, context, job_id=job_id, worker_id=worker_id,
                        lease_token=token, batch_id=batch_id, render_key=key,
                        completed=completed, total=len(requests),
                        cache_hits=cache_hits, generated=generated,
                    )
                    work.commit()
                    continue
                work.rollback()
            speaker = _voice_for(unit, profiles, payload["provider_id"])
            before_gpu = _gpu_memory_bytes()
            started_at = time.perf_counter()
            with generation_class("offline"):
                response = provider.generate_audio_batch([{
                    "text": unit.speech_plan.tts_input_text.strip(),
                    "speaker": speaker, "language": unit.language,
                    "parameters": {**settings, "instruct": unit.delivery},
                }])[0]
            wall_seconds = time.perf_counter() - started_at
            audio, duration, sample_rate = decode_pcm_wav(response)
            completed += 1
            generated += 1
            _save_render(
                database, blobs, context, job_id=job_id, worker_id=worker_id,
                lease_token=token, batch_id=batch_id, unit=unit, render_key=key,
                provider_id=payload["provider_id"], model_id=payload["model_id"],
                model_revision=payload["model_revision"], generation_parameters=settings,
                seed=payload.get("seed"), audio=audio, duration=duration,
                sample_rate=sample_rate, completed=completed, total=len(requests),
                cache_hits=cache_hits, generated=generated,
                actual_generation_parameters=dict(
                    response.get("generation_parameters_used") or settings
                ),
                diagnostics={"batch_size": 1,
                             "input_characters": len(unit.speech_plan.tts_input_text.strip()),
                             "generation_wall_seconds": wall_seconds,
                             "real_time_factor": wall_seconds / duration,
                             "generation_strategy_revision":
                                 response.get("generation_strategy_revision"),
                             "gpu_before_bytes": before_gpu,
                             "gpu_after_bytes": _gpu_memory_bytes()},
            )
        with unit_of_work(database) as work:
            work.connection.execute(
                "UPDATE omnix_audiobook_render_batches SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE workspace_id = %s AND id = %s",
                (context.workspace_id, batch_id),
            )
            work.jobs.complete(
                context, job_id=job_id, worker_id=worker_id, lease_token=token,
                output_refs=[{"chapter_id": payload["chapter_id"], "render_count": completed}],
                progress={"current": completed, "total": completed,
                          "cache_hits": cache_hits, "generated": generated,
                          "message": "chapter rendered"},
            )
            incomplete = int(work.connection.execute(
                """
                SELECT count(*) FROM omnix_jobs
                 WHERE workspace_id = %s AND module = 'audiobook'
                   AND job_type = 'audiobook.render-chapter'
                   AND input_payload->>'render_run_id' = %s
                   AND status <> 'completed'
                """, (context.workspace_id, payload["render_run_id"]),
            ).fetchone()[0])
            if incomplete == 0:
                current_run = work.connection.execute(
                    "SELECT settings->>'current_render_run_id' FROM omnix_audiobook_projects WHERE workspace_id = %s AND id = %s FOR UPDATE",
                    (context.workspace_id, payload["project_id"]),
                ).fetchone()
                if current_run and current_run[0] == payload["render_run_id"]:
                    rendered_jobs = work.connection.execute(
                        """
                        SELECT input_payload FROM omnix_jobs
                         WHERE workspace_id = %s AND module = 'audiobook'
                           AND job_type = 'audiobook.render-chapter'
                           AND input_payload->>'render_run_id' = %s
                         ORDER BY input_payload->>'chapter_id'
                        """, (context.workspace_id, payload["render_run_id"]),
                    ).fetchall()
                    from .hashing import text_hash

                    for (render_input,) in rendered_jobs:
                        chapter_id = str(render_input["chapter_id"])
                        assembly_job_id = f"ab:assemble:{text_hash(str(payload['render_run_id']) + ':' + chapter_id)}"
                        work.jobs.create_job_once(context, {
                            "id": assembly_job_id,
                            "module": "audiobook", "job_type": "audiobook.assemble-chapter",
                            "resource_class": "cpu", "priority": 0,
                            "input_payload": dict(render_input), "max_attempts": 3,
                        })
                work.connection.execute(
                    """
                    UPDATE omnix_audiobook_projects SET state = 'mastering', updated_at = CURRENT_TIMESTAMP
                     WHERE workspace_id = %s AND id = %s
                       AND settings->>'current_render_run_id' = %s
                    """, (context.workspace_id, payload["project_id"], payload["render_run_id"]),
                )
            work.commit()
    except Exception as exc:
        _LOG.exception("Audiobook chapter rendering failed for job %s", job_id)
        with unit_of_work(database) as work:
            work.jobs.fail(
                context, job_id=job_id, worker_id=worker_id, lease_token=token,
                error={"code": "render_failed", "message": str(exc),
                       "retryable": getattr(exc, "retryable", True)},
            )
            work.commit()
    return True


def run_preview_once(
    database: PostgresDatabase, blobs: LocalBlobStore, context: TenantContext,
    *, worker_id: str,
) -> bool:
    """Render one explicitly requested span with the same identity as offline work."""
    with unit_of_work(database) as work:
        job = work.jobs.claim_next(
            context, worker_id=worker_id, resource_classes=["gpu:tts:preview"],
            job_types=["audiobook.preview-span"], lease_seconds=3600,
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
    try:
        assert_model_revision(payload["provider_id"], payload["model_id"],
                              payload["model_revision"])
        with unit_of_work(database) as work:
            current = work.connection.execute(
                "SELECT current_source_revision_id FROM omnix_audiobook_projects WHERE workspace_id = %s AND id = %s",
                (context.workspace_id, payload["project_id"]),
            ).fetchone()
            if current is None or str(current[0]) != payload["source_revision_id"]:
                raise RenderFailure("preview source revision is no longer current", retryable=False)
            units = load_chapter_units(
                work.connection, context, project_id=payload["project_id"],
                chapter_id=payload["chapter_id"], span_id=payload["span_id"],
            )
            work.rollback()
        unit = next((item for item in units if item.span_id == payload["span_id"]), None)
        if unit is None:
            raise RenderFailure("preview span is no longer renderable", retryable=False)
        provider = get_tts_provider(payload["provider_id"])
        if provider is None:
            raise RenderFailure(f"TTS provider {payload['provider_id']} is unavailable")
        requested_settings = dict(payload.get("generation_parameters") or {})
        settings = _effective_generation_parameters(provider, requested_settings)
        if settings != requested_settings:
            _persist_effective_generation_parameters(
                database, context, job_id=job_id, effective=settings,
            )
            payload["generation_parameters"] = settings
        key = unit.identity(
            provider_id=payload["provider_id"], model_id=payload["model_id"],
            model_revision=payload["model_revision"],
            generation_parameters=settings, seed=payload.get("seed"),
        ).key()
        with unit_of_work(database) as work:
            current_job = work.jobs.get_job(context, job_id)
            if current_job["status"] == "cancel_requested":
                work.jobs.acknowledge_cancel(
                    context, job_id=job_id, worker_id=worker_id, lease_token=token,
                )
                work.commit()
                return True
            cached = find_valid_render(work.connection, context, blobs, key)
            if cached is not None:
                work.jobs.complete(
                    context, job_id=job_id, worker_id=worker_id, lease_token=token,
                    output_refs=[{"render_id": cached["id"],
                                  "audio_asset_id": cached["audio_asset_id"]}],
                    progress={"current": 1, "total": 1, "message": "preview ready (cached)"},
                )
                work.commit()
                return True
            work.rollback()
        profiles = {item.id: item for item in discover_canonical_voice_clone_assets()}
        speaker = _voice_for(unit, profiles, payload["provider_id"])
        before_gpu = _gpu_memory_bytes()
        started_at = time.perf_counter()
        with generation_class("preview"):
            response = provider.generate_audio_batch([{
                "text": unit.speech_plan.tts_input_text.strip(),
                "speaker": speaker, "language": unit.language,
                "parameters": {**settings, "instruct": unit.delivery},
            }])[0]
        wall_seconds = time.perf_counter() - started_at
        audio, duration, sample_rate = decode_pcm_wav(response)
        _save_render(
            database, blobs, context, job_id=job_id, worker_id=worker_id,
            lease_token=token, batch_id=None, unit=unit, render_key=key,
            provider_id=payload["provider_id"], model_id=payload["model_id"],
            model_revision=payload["model_revision"], generation_parameters=settings,
            seed=payload.get("seed"), audio=audio, duration=duration,
            sample_rate=sample_rate, completed=1, total=1,
            actual_generation_parameters=dict(
                response.get("generation_parameters_used") or settings
            ),
            diagnostics={"batch_size": 1,
                         "input_characters": len(unit.speech_plan.tts_input_text.strip()),
                         "generation_wall_seconds": wall_seconds,
                         "real_time_factor": wall_seconds / duration,
                         "generation_strategy_revision":
                             response.get("generation_strategy_revision"),
                         "gpu_before_bytes": before_gpu,
                         "gpu_after_bytes": _gpu_memory_bytes()},
        )
    except Exception as exc:
        _LOG.exception("Audiobook span preview failed for job %s", job_id)
        with unit_of_work(database) as work:
            work.jobs.fail(
                context, job_id=job_id, worker_id=worker_id, lease_token=token,
                error={"code": "preview_failed", "message": str(exc),
                       "retryable": getattr(exc, "retryable", True)},
            )
            work.commit()
    return True
