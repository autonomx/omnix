"""Durable audiobook export jobs bound to immutable chapter assemblies."""
from __future__ import annotations

import logging
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from uuid import uuid4

from app.persistence.blob_store import LocalBlobStore
from app.persistence.database import PostgresDatabase
from app.persistence.tenant import TenantContext
from app.persistence.unit_of_work import unit_of_work

from .export import (FORMAT_MIME, ffmetadata,
                     ffmpeg_binary, ffmpeg_command, ffmpeg_version,
                     freeze_manifest, manifest_hash)
from .hashing import canonical_json


_LOG = logging.getLogger(__name__)


def _stage_book_input(blobs: LocalBlobStore, assets: list[tuple[str, str]],
                      root: Path) -> Path:
    """Prepare verified chapter files for FFmpeg's concat demuxer."""
    if not assets:
        raise ValueError("book has no chapter audio")
    root.mkdir(parents=True, exist_ok=True)
    sample_rate = None
    lines = ["ffconcat version 1.0"]
    for index, (key, checksum) in enumerate(assets):
        name = f"chapter-{index:06d}.wav"
        staged = root / name
        blobs.stage_verified_to(key, staged, expected_checksum=checksum)
        with wave.open(str(staged), "rb") as reader:
            if (reader.getnchannels() != 1 or reader.getsampwidth() != 2
                    or reader.getcomptype() != "NONE" or reader.getnframes() <= 0):
                raise ValueError("chapter audio must be non-empty mono PCM16 WAV")
            if sample_rate is None:
                sample_rate = reader.getframerate()
            elif reader.getframerate() != sample_rate:
                raise ValueError("chapter sample rates differ")
        lines.append(f"file {name}")
    playlist = root / "chapters.ffconcat"
    playlist.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return playlist


def start_export(database: PostgresDatabase, blobs: LocalBlobStore,
                 context: TenantContext, *, project_id: str,
                 format: str = "m4b") -> dict[str, str]:
    if format not in FORMAT_MIME:
        raise ValueError("unsupported audiobook export format")
    executable = ffmpeg_binary()
    version = ffmpeg_version(executable)
    with unit_of_work(database) as work:
        project = work.connection.execute(
            """SELECT id, title, author, language, cover_asset_id,
                      current_source_revision_id, state,
                      settings->>'current_render_run_id'
                 FROM omnix_audiobook_projects
                WHERE workspace_id = %s AND id = %s AND deleted_at IS NULL FOR UPDATE""",
            (context.workspace_id, project_id),
        ).fetchone()
        if project is None:
            raise KeyError(project_id)
        if project[6] not in {"ready_to_export", "exported"}:
            raise ValueError("chapters are not ready for export")
        source = work.connection.execute(
            """SELECT id, canonical_hash FROM omnix_audiobook_source_revisions
                WHERE workspace_id = %s AND id = %s""",
            (context.workspace_id, project[5]),
        ).fetchone()
        if source is None:
            raise ValueError("canonical source is missing")
        chapter_rows = work.connection.execute(
            """SELECT id, ordinal, title, canonical_hash FROM omnix_audiobook_chapters
                WHERE workspace_id = %s AND source_revision_id = %s
                ORDER BY ordinal""",
            (context.workspace_id, source[0]),
        ).fetchall()
        chapters = []
        for chapter_id, ordinal, title, canonical_hash in chapter_rows:
            job = work.connection.execute(
                """SELECT output_refs FROM omnix_jobs
                    WHERE workspace_id = %s AND job_type = 'audiobook.assemble-chapter'
                      AND input_payload->>'render_run_id' = %s
                      AND input_payload->>'chapter_id' = %s AND status = 'completed'
                    ORDER BY completed_at DESC LIMIT 1""",
                (context.workspace_id, project[7], chapter_id),
            ).fetchone()
            if not job or not job[0]:
                raise ValueError(f"chapter {ordinal} has no completed assembly")
            assembly_id = job[0][0]["assembly_id"]
            assembly = work.connection.execute(
                """SELECT ca.assembly_key, ca.render_ids, ca.audio_asset_id,
                          ca.audio_checksum, ca.duration_seconds, ca.sample_rate,
                          ca.pause_policy, ca.loudness, ca.timeline,
                          a.storage_key
                     FROM omnix_audiobook_chapter_assemblies ca
                     JOIN omnix_assets a ON a.id = ca.audio_asset_id
                    WHERE ca.workspace_id = %s AND ca.id = %s
                      AND ca.chapter_id = %s AND a.lifecycle_status = 'active'""",
                (context.workspace_id, assembly_id, chapter_id),
            ).fetchone()
            if assembly is None:
                raise ValueError(f"chapter {ordinal} assembly asset is missing")
            with blobs.open_verified(str(assembly[9]), expected_checksum=str(assembly[3])):
                pass
            render_ids = [str(item) for item in assembly[1]]
            renders = []
            for render_id in render_ids:
                row = work.connection.execute(
                    """SELECT r.render_key, r.annotation_id, r.casting_id,
                              r.speech_plan_hash, r.provider, r.generation_settings,
                              r.audio_checksum, c.voice_profile_id, c.voice_revision_hash,
                              a.revision, c.revision
                         FROM omnix_audiobook_renders r
                         LEFT JOIN omnix_audiobook_castings c ON c.id = r.casting_id
                         JOIN omnix_audiobook_annotations a ON a.id = r.annotation_id
                        WHERE r.workspace_id = %s AND r.id = %s""",
                    (context.workspace_id, render_id),
                ).fetchone()
                if row is None:
                    raise ValueError("assembly references a missing render")
                renders.append({"id": render_id, "render_key": row[0],
                                "annotation_id": row[1], "casting_id": row[2],
                                "speech_plan_hash": row[3], "provider": row[4],
                                "generation_settings": row[5],
                                "audio_checksum": row[6],
                                "voice_profile_id": row[7],
                                "voice_revision_hash": row[8],
                                "annotation_revision": row[9],
                                "casting_revision": row[10]})
            chapters.append({
                "id": str(chapter_id), "ordinal": int(ordinal), "title": str(title),
                "canonical_hash": str(canonical_hash),
                "assembly_id": str(assembly_id), "assembly_key": str(assembly[0]),
                "render_ids": render_ids, "renders": renders,
                "audio_asset_id": str(assembly[2]), "audio_checksum": str(assembly[3]),
                "duration_seconds": float(assembly[4]), "sample_rate": int(assembly[5]),
                "pause_policy": assembly[6], "loudness": assembly[7],
                "timeline": assembly[8],
            })
        cover = None
        if project[4]:
            row = work.connection.execute(
                """SELECT id, checksum_sha256, mime_type, storage_key
                    FROM omnix_assets WHERE workspace_id = %s AND id = %s
                      AND lifecycle_status = 'active'""",
                (context.workspace_id, project[4]),
            ).fetchone()
            if row is None:
                raise ValueError("project cover asset is missing")
            with blobs.open_verified(str(row[3]), expected_checksum=str(row[1])):
                pass
            cover = {"asset_id": row[0], "checksum": row[1], "mime_type": row[2]}
        cast_rows = work.connection.execute(
            """SELECT display_name FROM omnix_audiobook_speakers
                WHERE workspace_id = %s AND project_id = %s AND status = 'active'
                ORDER BY display_name""", (context.workspace_id, project_id),
        ).fetchall()
        manifest = freeze_manifest(
            project={"id": project_id, "title": project[1], "author": project[2],
                     "language": project[3], "cover": cover,
                     "render_run_id": project[7],
                     "cast": [{"name": row[0]} for row in cast_rows]},
            source={"id": source[0], "canonical_hash": source[1]},
            chapters=chapters, format=format, encoder_version=version,
            settings={"codec": {"m4b": "aac", "flac": "flac",
                                "wav": "pcm_s16le", "mp3": "libmp3lame"}[format]},
        )
        job_id = f"ab:job:{uuid4().hex}"
        manifest_id = f"ab:manifest:{uuid4().hex}"
        work.jobs.create_job(context, {
            "id": job_id, "module": "audiobook", "job_type": "audiobook.export",
            "resource_class": "cpu", "priority": 0,
            "input_payload": {"manifest_id": manifest_id}, "max_attempts": 3,
        })
        work.connection.execute(
            """INSERT INTO omnix_audiobook_export_manifests
                 (id, workspace_id, project_id, source_revision_id, job_id,
                  format, manifest, manifest_hash)
                 VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)""",
            (manifest_id, context.workspace_id, project_id, source[0], job_id,
             format, canonical_json(manifest), manifest_hash(manifest)),
        )
        work.commit()
    return {"job_id": job_id, "manifest_id": manifest_id,
            "manifest_hash": manifest_hash(manifest)}


def run_export_once(database: PostgresDatabase, blobs: LocalBlobStore,
                    context: TenantContext, *, worker_id: str) -> bool:
    with unit_of_work(database) as work:
        job = work.jobs.claim_next(
            context, worker_id=worker_id, resource_classes=["cpu"],
            job_types=["audiobook.export"], lease_seconds=3600,
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
    storage_key = None
    persisted = False
    started_at = time.perf_counter()
    try:
        with unit_of_work(database) as work:
            row = work.connection.execute(
                """SELECT manifest, manifest_hash, project_id, source_revision_id
                    FROM omnix_audiobook_export_manifests
                    WHERE workspace_id = %s AND id = %s AND job_id = %s""",
                (context.workspace_id, job["input_payload"]["manifest_id"], job_id),
            ).fetchone()
            if row is None or manifest_hash(row[0]) != row[1]:
                raise ValueError("frozen export manifest is missing or corrupt")
            manifest = row[0]
            assets = []
            for chapter in manifest["chapters"]:
                asset = work.connection.execute(
                    """SELECT storage_key, checksum_sha256 FROM omnix_assets
                        WHERE workspace_id = %s AND id = %s AND lifecycle_status = 'active'""",
                    (context.workspace_id, chapter["audio_asset_id"]),
                ).fetchone()
                if asset is None or asset[1] != chapter["audio_checksum"]:
                    raise ValueError("frozen chapter asset is unavailable")
                assets.append((str(asset[0]), str(asset[1])))
            cover_asset = None
            if manifest.get("cover"):
                cover = manifest["cover"]
                cover_asset = work.connection.execute(
                    """SELECT storage_key, checksum_sha256 FROM omnix_assets
                        WHERE workspace_id = %s AND id = %s AND lifecycle_status = 'active'""",
                    (context.workspace_id, cover["asset_id"]),
                ).fetchone()
                if cover_asset is None or cover_asset[1] != cover["checksum"]:
                    raise ValueError("frozen cover asset is unavailable")
            work.rollback()
        executable = ffmpeg_binary()
        if ffmpeg_version(executable) != manifest["encoder"]["version"]:
            raise ValueError("FFmpeg version differs from frozen manifest")
        with tempfile.TemporaryDirectory(prefix="omnix-audiobook-",
                                         dir=blobs.root) as temporary:
            root = Path(temporary)
            input_path = _stage_book_input(blobs, assets, root)
            staged_audio_bytes = sum(path.stat().st_size for path in root.glob("chapter-*.wav"))
            metadata_path = root / "chapters.ffmeta"
            output_path = root / f"book.{manifest['format']}"
            metadata_path.write_text(ffmetadata(manifest), encoding="utf-8")
            cover_path = None
            if cover_asset is not None:
                cover_path = str(root / "cover")
                Path(cover_path).write_bytes(blobs.read_bytes(
                    str(cover_asset[0]), expected_checksum=str(cover_asset[1])))
            command = ffmpeg_command(
                executable, input_wav=str(input_path),
                metadata_path=str(metadata_path), output_path=str(output_path),
                format=manifest["format"], cover_path=cover_path,
                concat_input=True,
            )
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 7200
            try:
                while True:
                    try:
                        return_code = process.wait(timeout=30)
                        break
                    except subprocess.TimeoutExpired:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("audiobook export encoder timed out")
                        with unit_of_work(database) as work:
                            current = work.jobs.get_job(context, job_id)
                            if current["status"] == "cancel_requested":
                                process.kill()
                                process.wait()
                                work.jobs.acknowledge_cancel(
                                    context, job_id=job_id, worker_id=worker_id,
                                    lease_token=token,
                                )
                                work.commit()
                                return True
                            work.jobs.renew_lease(
                                context, job_id=job_id, worker_id=worker_id,
                                lease_token=token, lease_seconds=3600,
                            )
                            work.commit()
                if return_code != 0:
                    raise RuntimeError(f"FFmpeg encoder exited with code {return_code}")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
            if output_path.stat().st_size <= 0:
                raise ValueError("encoder produced an empty export")
            asset_id = f"ab:export-audio:{uuid4().hex}"
            export_id = f"ab:export:{uuid4().hex}"
            storage_key = f"audiobook/export/{uuid4().hex}.{manifest['format']}"
            blob = blobs.put_file(storage_key, output_path)
        with unit_of_work(database) as work:
            current = work.jobs.get_job(context, job_id)
            if current["status"] == "cancel_requested":
                work.jobs.acknowledge_cancel(
                    context, job_id=job_id, worker_id=worker_id, lease_token=token,
                )
                work.commit()
                return True
            work.assets.create(context, {
                "id": asset_id, "module": "audiobook", "asset_type": "export",
                "mime_type": FORMAT_MIME[manifest["format"]],
                "byte_size": blob["byte_size"],
                "checksum_sha256": blob["checksum_sha256"],
                "storage_provider": blob["storage_provider"], "storage_key": storage_key,
                "generation_job_id": job_id,
                "metadata": {"manifest_id": job["input_payload"]["manifest_id"],
                             "manifest_hash": row[1]},
            })
            work.connection.execute(
                """INSERT INTO omnix_audiobook_exports
                    (id, workspace_id, project_id, source_revision_id, job_id,
                     format, manifest, manifest_hash, output_asset_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)""",
                (export_id, context.workspace_id, row[2], row[3], job_id,
                 manifest["format"], canonical_json(manifest), row[1], asset_id),
            )
            work.jobs.complete(
                context, job_id=job_id, worker_id=worker_id, lease_token=token,
                output_refs=[{"export_id": export_id, "asset_id": asset_id}],
                progress={"current": 1, "total": 1, "message": "export encoded",
                          "chapter_count": len(assets),
                          "staged_audio_bytes": staged_audio_bytes,
                          "output_audio_bytes": blob["byte_size"],
                          "wall_seconds": round(time.perf_counter() - started_at, 3)},
            )
            work.connection.execute(
                """UPDATE omnix_audiobook_projects SET state = 'exported',
                          updated_at = CURRENT_TIMESTAMP
                    WHERE workspace_id = %s AND id = %s
                      AND current_source_revision_id = %s
                      AND settings->>'current_render_run_id' = %s""",
                (context.workspace_id, row[2], row[3], manifest["render_run_id"]),
            )
            work.commit()
            persisted = True
    except Exception as exc:
        _LOG.exception("Audiobook export failed for job %s", job_id)
        with unit_of_work(database) as work:
            work.jobs.fail(
                context, job_id=job_id, worker_id=worker_id, lease_token=token,
                error={"code": "export_failed", "message": str(exc),
                       "retryable": not isinstance(exc, ValueError)},
            )
            work.commit()
    finally:
        if storage_key and not persisted:
            blobs.delete(storage_key)
    return True
