"""Resumable chapter rendering over leased coarse jobs and immutable audio assets."""
from __future__ import annotations

import base64
import io
import logging
import tempfile
import sys
import time
import wave
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.assets.canonical_voice_clones import discover_canonical_voice_clone_assets
from app.assets.voice_clone_identity import voice_reference_revision
from app.persistence.blob_store import LocalBlobStore
from app.persistence.database import PostgresDatabase
from app.persistence.tenant import TenantContext
from app.persistence.unit_of_work import unit_of_work
from app.shared import get_tts_provider
from app.providers.tts_priority import generation_class, other_process_priority_pending

from .hashing import canonical_json, text_hash
from .render_cache import find_valid_render
from .render_planner import RenderUnit, load_chapter_units
from .model_identity import assert_model_revision


_LOG = logging.getLogger(__name__)
_HIGHER_PRIORITY = ("gpu:tts:realtime", "gpu:tts:preview", "gpu:tts")


class RenderFailure(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


def _generation_progress_callback(
    database: PostgresDatabase,
    context: TenantContext,
    *,
    job_id: str,
    worker_id: str,
    lease_token: str,
    completed: int,
    total: int,
) -> Any:
    """Persist throttled token-level progress for providers that expose it."""
    last_update = 0.0
    last_renewal = time.monotonic()
    disabled = False

    def report(current: int, token_total: int) -> None:
        nonlocal disabled, last_update, last_renewal
        if disabled:
            return
        now = time.monotonic()
        if current < token_total and now - last_update < 0.35:
            return
        last_update = now
        safe_total = max(1, int(token_total))
        fraction = min(1.0, max(0.0, float(current) / safe_total))
        try:
            with unit_of_work(database) as work:
                if now - last_renewal >= 60:
                    work.jobs.renew_lease(
                        context, job_id=job_id, worker_id=worker_id,
                        lease_token=lease_token, lease_seconds=3600,
                    )
                    last_renewal = now
                work.jobs.update_progress(
                    context, job_id=job_id, worker_id=worker_id,
                    lease_token=lease_token,
                    progress={
                        "current": min(float(total), completed + fraction),
                        "total": max(1, int(total)),
                        "unit_current": max(0, int(current)),
                        "unit_total": safe_total,
                        "message": (
                            f"Generating audio for unit {completed + 1} of {total} "
                            f"({max(0, int(current))}/{safe_total} codec steps)"
                        ),
                    },
                )
                work.commit()
        except Exception:
            # A progress write must never fail an otherwise valid TTS request.
            disabled = True
            _LOG.debug("unable to persist render progress for job %s", job_id, exc_info=True)

    return report


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


def _pause_if_requested(
    work: Any, context: TenantContext, *, job_id: str,
    worker_id: str, lease_token: str,
) -> bool:
    """Release a render lease when the UI requested pause at a safe boundary."""
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


def _voice_for(unit: RenderUnit, profiles: dict[str, Any], provider_id: str) -> str:
    profile = profiles.get(unit.voice_profile_id)
    if profile is None or not profile.storage_path:
        raise RenderFailure(f"voice profile {unit.voice_profile_id} is unavailable", retryable=False)
    if voice_reference_revision(profile.storage_path) != unit.voice_revision_hash:
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
    complete_preview: bool = True,
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
            if batch_id is None and complete_preview:
                work.jobs.complete(
                    context, job_id=job_id, worker_id=worker_id,
                    lease_token=lease_token,
                    output_refs=[{"render_id": render_id, "audio_asset_id": asset_id}],
                    progress={"current": 1, "total": 1, "message": "preview ready"},
                )
            elif batch_id is not None:
                _checkpoint(
                    work, context, job_id=job_id, worker_id=worker_id,
                    lease_token=lease_token, batch_id=batch_id, render_key=render_key,
                    completed=completed, total=total,
                    cache_hits=cache_hits, generated=generated,
                )
            else:
                work.jobs.renew_lease(context, job_id=job_id, worker_id=worker_id,
                                      lease_token=lease_token, lease_seconds=3600)
                work.jobs.update_progress(
                    context, job_id=job_id, worker_id=worker_id, lease_token=lease_token,
                    progress={"current": completed, "total": total,
                              "message": "generating span preview"},
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
            speaker = _voice_for(unit, profiles, payload["provider_id"])
            with unit_of_work(database) as work:
                current = work.jobs.get_job(context, job_id)
                if current["status"] == "cancel_requested":
                    work.jobs.acknowledge_cancel(
                        context, job_id=job_id, worker_id=worker_id, lease_token=token,
                    )
                    work.commit()
                    return True
                if _pause_if_requested(
                    work, context, job_id=job_id, worker_id=worker_id, lease_token=token,
                ):
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
                    if _pause_if_requested(
                        work, context, job_id=job_id, worker_id=worker_id, lease_token=token,
                    ):
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
                request = {
                    "text": unit.speech_plan.tts_input_text.strip(),
                    "speaker": speaker, "language": unit.language,
                    "parameters": {**settings, "instruct": unit.delivery},
                }
                generate_with_progress = getattr(provider, "generate_audio_with_progress", None)
                if callable(generate_with_progress):
                    callback = _generation_progress_callback(
                        database, context, job_id=job_id, worker_id=worker_id,
                        lease_token=token, completed=completed,
                        total=len(requests),
                    )
                    response = generate_with_progress(
                        request["text"], speaker=request["speaker"],
                        language=request["language"],
                        progress_callback=callback,
                        **request["parameters"],
                    )
                else:
                    response = provider.generate_audio_batch([request])[0]
            wall_seconds = time.perf_counter() - started_at
            _voice_for(unit, profiles, payload["provider_id"])
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
            current_run = work.connection.execute(
                "SELECT settings->>'current_render_run_id' FROM omnix_audiobook_projects WHERE workspace_id = %s AND id = %s FOR UPDATE",
                (context.workspace_id, payload["project_id"]),
            ).fetchone()
            if current_run and current_run[0] == payload["render_run_id"]:
                chapter_id = str(payload["chapter_id"])
                work.jobs.create_job_once(context, {
                    "id": f"ab:assemble:{text_hash(str(payload['render_run_id']) + ':' + chapter_id)}",
                    "module": "audiobook", "job_type": "audiobook.assemble-chapter",
                    "resource_class": "cpu", "priority": 0,
                    "input_payload": dict(payload), "max_attempts": 3,
                })
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


def _complete_span_preview(
    database: PostgresDatabase, blobs: LocalBlobStore, context: TenantContext, *,
    job_id: str, worker_id: str, lease_token: str, refs: list[dict[str, str]],
) -> None:
    """Publish one playable clip after every segment is attested."""
    output_ref: dict[str, Any] = dict(refs[0])
    storage_key = None
    persisted = False
    try:
        if len(refs) > 1:
            with unit_of_work(database) as work:
                assets = [work.connection.execute(
                    """SELECT storage_key, checksum_sha256 FROM omnix_assets
                        WHERE workspace_id = %s AND id = %s
                          AND lifecycle_status = 'active'""",
                    (context.workspace_id, ref["audio_asset_id"]),
                ).fetchone() for ref in refs]
                work.rollback()
            with tempfile.TemporaryDirectory(prefix="omnix-preview-", dir=blobs.root) as temporary:
                path = Path(temporary) / "preview.wav"
                concatenate_preview_audio(blobs, assets, path)
                asset_id = f"ab:preview-audio:{uuid4().hex}"
                storage_key = f"audiobook/preview/{uuid4().hex}.wav"
                blob = blobs.put_file(storage_key, path)
            output_ref = {"audio_asset_id": asset_id,
                          "render_ids": [ref["render_id"] for ref in refs]}
        with unit_of_work(database) as work:
            current = work.jobs.get_job(context, job_id)
            if current["status"] == "cancel_requested":
                work.jobs.acknowledge_cancel(context, job_id=job_id, worker_id=worker_id,
                                            lease_token=lease_token)
                work.commit()
                return
            if storage_key:
                work.assets.create(context, {
                    "id": asset_id, "module": "audiobook", "asset_type": "render",
                    "mime_type": "audio/wav", "byte_size": blob["byte_size"],
                    "checksum_sha256": blob["checksum_sha256"],
                    "storage_provider": blob["storage_provider"], "storage_key": storage_key,
                    "generation_job_id": job_id, "metadata": {"render_ids": output_ref["render_ids"]},
                })
            work.jobs.complete(
                context, job_id=job_id, worker_id=worker_id, lease_token=lease_token,
                output_refs=[output_ref],
                progress={"current": len(refs), "total": len(refs), "message": "preview ready"},
            )
            work.commit()
            persisted = True
    finally:
        if storage_key and not persisted:
            blobs.delete(storage_key)


def concatenate_preview_audio(blobs: LocalBlobStore, assets: list[Any], path: Path) -> None:
    """Concatenate lossless segments in source order without mastering or pauses."""
    if not assets or any(asset is None for asset in assets):
        raise RenderFailure("preview segment asset is unavailable")
    with wave.open(str(path), "wb") as writer:
        expected = None
        for asset in assets:
            with blobs.open_verified(str(asset[0]), expected_checksum=str(asset[1])) as handle:
                with wave.open(handle, "rb") as reader:
                    params = (reader.getnchannels(), reader.getsampwidth(), reader.getframerate())
                    if expected is None:
                        expected = params
                        writer.setnchannels(params[0])
                        writer.setsampwidth(params[1])
                        writer.setframerate(params[2])
                    elif params != expected:
                        raise RenderFailure("preview segment audio formats differ", retryable=False)
                    while frames := reader.readframes(65536):
                        writer.writeframesraw(frames)


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
                voice_profile_id=payload.get("voice_profile_id"),
                voice_revision_hash=payload.get("voice_revision_hash"),
            )
            work.rollback()
        if not units:
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
        profiles = {item.id: item for item in discover_canonical_voice_clone_assets()}
        refs = []
        for unit in units:
            speaker = _voice_for(unit, profiles, payload["provider_id"])
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
                work.jobs.renew_lease(context, job_id=job_id, worker_id=worker_id,
                                      lease_token=token, lease_seconds=3600)
                cached = find_valid_render(work.connection, context, blobs, key)
                work.commit()
            if cached is not None:
                refs.append({"render_id": cached["id"], "audio_asset_id": cached["audio_asset_id"]})
                continue
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
            _voice_for(unit, profiles, payload["provider_id"])
            audio, duration, sample_rate = decode_pcm_wav(response)
            refs.append(_save_render(
                database, blobs, context, job_id=job_id, worker_id=worker_id,
                lease_token=token, batch_id=None, unit=unit, render_key=key,
                provider_id=payload["provider_id"], model_id=payload["model_id"],
                model_revision=payload["model_revision"], generation_parameters=settings,
                seed=payload.get("seed"), audio=audio, duration=duration,
                sample_rate=sample_rate, completed=len(refs) + 1, total=len(units),
                complete_preview=False,
                actual_generation_parameters=dict(response.get("generation_parameters_used") or settings),
                diagnostics={"batch_size": 1,
                             "input_characters": len(unit.speech_plan.tts_input_text.strip()),
                             "generation_wall_seconds": wall_seconds,
                             "real_time_factor": wall_seconds / duration,
                             "generation_strategy_revision": response.get("generation_strategy_revision"),
                             "gpu_before_bytes": before_gpu,
                             "gpu_after_bytes": _gpu_memory_bytes()},
            ))
        _complete_span_preview(
            database, blobs, context, job_id=job_id, worker_id=worker_id,
            lease_token=token, refs=refs,
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
