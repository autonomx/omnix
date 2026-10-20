"""Recipes and batch runs (Voice Studio Phase 7).

A recipe is a named, versioned list of tool steps (isolate -> enhance ->
transcribe -> subtitles, say). A batch run takes one item per input; each item
submits ordinary jobs, one step at a time, and the ``BatchAdvancer`` moves it
on when a job finishes. No parent job holds a pool slot while items wait.
Failed steps are retried per item; an input already done with the same recipe
version is skipped, keeping its earlier outputs.

The advancer serves every workspace (system scope ``voice.automation``) and
acts inside each run's own workspace and owner, so the jobs it submits carry
that tenant.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

TICK_SECONDS = 3.0
MAX_ATTEMPTS = 2
ACTIVE_PER_RUN = 4
MAX_BATCH_ITEMS = 1000

# Each tool: the job it submits, its resource class and module, what it takes and what it makes.
TOOLS: dict[str, dict[str, str]] = {
    "isolate": {"job": "audio.isolate", "resource": "gpu:audio", "module": "voice", "takes": "audio", "makes": "audio"},
    "enhance": {"job": "audio.enhance", "resource": "gpu:audio", "module": "voice", "takes": "audio", "makes": "audio"},
    "transcribe": {"job": "stt.transcribe", "resource": "gpu:stt", "module": "stt", "takes": "audio",
                   "makes": "transcript"},
    "subtitles": {"job": "voice.subtitles", "resource": "cpu", "module": "voice", "takes": "transcript",
                  "makes": "subtitles"},
    "watermark-check": {"job": "audio.watermark-detect", "resource": "gpu:audio", "module": "voice", "takes": "audio",
                        "makes": "report"},
    "export": {"job": "voice.export", "resource": "cpu", "module": "voice", "takes": "audio", "makes": "export"},
}
_EXPORT_FORMATS = {"wav16", "wav24", "flac", "mp3", "opus"}


class RecipeError(ValueError):
    """A recipe that cannot run: an unknown tool, or a step that cannot take what the one before made."""


class AutomationNotFound(LookupError):
    pass


def validate_steps(steps: list[Any]) -> list[dict[str, Any]]:
    """Normalised steps; each must take what the step before it made (the input is audio)."""
    if not isinstance(steps, list) or not 1 <= len(steps) <= 12:
        raise RecipeError("a recipe has one to twelve steps")
    normalised, holding = [], "audio"
    for index, raw in enumerate(steps, start=1):
        if not isinstance(raw, dict) or str(raw.get("tool") or "") not in TOOLS:
            raise RecipeError(f"step {index}: the tool must be one of {', '.join(TOOLS)}")
        tool = str(raw["tool"])
        settings: dict[str, Any] = raw["settings"] if isinstance(raw.get("settings"), dict) else {}
        spec = TOOLS[tool]
        if spec["takes"] != holding:
            raise RecipeError(f"step {index}: {tool} takes {spec['takes']}, but the step before makes {holding}")
        if tool == "isolate" and settings.get("model", "roformer") not in {"roformer", "demucs"}:
            raise RecipeError(f"step {index}: isolate uses roformer or demucs")
        if tool == "export" and settings.get("format", "mp3") not in _EXPORT_FORMATS:
            raise RecipeError(f"step {index}: export formats are {', '.join(sorted(_EXPORT_FORMATS))}")
        if tool == "transcribe" and not 0 <= int(settings.get("speakers", 0) or 0) <= 8:
            raise RecipeError(f"step {index}: speakers is 0 (automatic) to 8")
        normalised.append({"tool": tool, "settings": {key: settings[key] for key in sorted(settings)}})
        holding = spec["makes"] if spec["makes"] in {"audio", "transcript"} else "nothing"
    return normalised


def job_request(step: dict[str, Any], asset_id: str, *, item_id: str) -> dict[str, Any]:
    """The ``CreateJobRequest`` fields for one step of one item."""
    spec, settings = TOOLS[step["tool"]], step.get("settings") or {}
    payload: dict[str, Any] = {"asset_id": asset_id, "batch_item_id": item_id}
    if step["tool"] == "isolate":
        payload["model"] = settings.get("model", "roformer")
    elif step["tool"] == "transcribe":
        payload.update(timed=True, diarize=bool(settings.get("diarize", True)),
                       speakers=int(settings.get("speakers", 0) or 0), language=str(settings.get("language") or ""),
                       save_transcript=True)
    elif step["tool"] == "subtitles":
        payload["formats"] = [fmt for fmt in settings.get("formats", ["srt", "vtt"]) if fmt in {"srt", "vtt", "txt"}]
    elif step["tool"] == "export":
        payload.update(format=settings.get("format", "mp3"), loudness=settings.get("loudness", "none"))
    return {"module": spec["module"], "type": spec["job"], "resource_class": spec["resource"], "priority": 0,
            "input_ref": {"asset_id": asset_id}, "input_payload": payload}


def content_hash(asset: Any) -> str:
    from app.assets.content import open_asset

    digest = hashlib.sha256()
    with open_asset(asset) as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


# --- repository ------------------------------------------------------------------------------------


_RUN_COLUMNS = ("id", "workspace_id", "owner_user_id", "recipe_id", "recipe_version", "steps", "title", "watch_folder",
                "status", "created_at", "updated_at")
_ITEM_COLUMNS = ("id", "run_id", "position", "source_asset_id", "input_hash", "current_asset_id", "step_index",
                 "status", "job_id", "attempts", "outputs", "error", "output_name", "updated_at")


def _row(columns: tuple[str, ...], row: Any) -> dict[str, Any]:
    value = dict(zip(columns, row))
    for key in ("created_at", "updated_at"):
        if key in value and value[key] is not None and not isinstance(value[key], str):
            value[key] = value[key].isoformat()
    return value


def _work() -> Any:
    from app.persistence.database import default_database
    from app.persistence.unit_of_work import unit_of_work

    return unit_of_work(default_database())


def _tenant() -> Any:
    from app.runtime.tenant_context import current_tenant

    return current_tenant()


def save_recipe(*, name: str, steps: list[Any], recipe_id: str = "") -> dict[str, Any]:
    """Create a recipe, or change one; changed steps make a new version (earlier runs keep theirs)."""
    normalised = validate_steps(steps)
    name = " ".join(str(name or "").split())[:120]
    if not name:
        raise RecipeError("name the recipe")
    context = _tenant()
    with _work() as work:
        if recipe_id:
            row = work.connection.execute(
                "SELECT steps FROM omnix_voice_recipes WHERE workspace_id = %s AND id = %s FOR UPDATE",
                (context.workspace_id, recipe_id)).fetchone()
            if row is None:
                raise AutomationNotFound(recipe_id)
            changed = row[0] != normalised
            work.connection.execute(
                """UPDATE omnix_voice_recipes SET name = %s, steps = %s::jsonb,
                          version = version + %s, updated_at = clock_timestamp()
                    WHERE workspace_id = %s AND id = %s""",
                (name, json.dumps(normalised), 1 if changed else 0, context.workspace_id, recipe_id))
        else:
            recipe_id = f"vrecipe:{uuid.uuid4().hex}"
            work.connection.execute(
                "INSERT INTO omnix_voice_recipes (id, workspace_id, name, steps) VALUES (%s, %s, %s, %s::jsonb)",
                (recipe_id, context.workspace_id, name, json.dumps(normalised)))
        work.commit()
    return get_recipe(recipe_id)


def get_recipe(recipe_id: str) -> dict[str, Any]:
    context = _tenant()
    with _work() as work:
        row = work.connection.execute(
            "SELECT id, name, version, steps, created_at, updated_at FROM omnix_voice_recipes "
            "WHERE workspace_id = %s AND id = %s", (context.workspace_id, recipe_id)).fetchone()
        work.rollback()
    if row is None:
        raise AutomationNotFound(recipe_id)
    return _row(("id", "name", "version", "steps", "created_at", "updated_at"), row)


def list_recipes() -> list[dict[str, Any]]:
    context = _tenant()
    with _work() as work:
        rows = work.connection.execute(
            "SELECT id, name, version, steps, created_at, updated_at FROM omnix_voice_recipes "
            "WHERE workspace_id = %s ORDER BY updated_at DESC, id LIMIT 200", (context.workspace_id,)).fetchall()
        work.rollback()
    return [_row(("id", "name", "version", "steps", "created_at", "updated_at"), row) for row in rows]


def delete_recipe(recipe_id: str) -> None:
    context = _tenant()
    with _work() as work:
        deleted = work.connection.execute("DELETE FROM omnix_voice_recipes WHERE workspace_id = %s AND id = %s",
                                          (context.workspace_id, recipe_id)).rowcount
        work.commit()
    if not deleted:
        raise AutomationNotFound(recipe_id)


def start_batch(*, recipe_id: str, asset_ids: list[str], title: str = "", watch_folder: str = "",
                output_names: dict[str, str] | None = None) -> dict[str, Any]:
    """A run of ``recipe_id`` over the assets: one item each, skipped when done before at this version."""
    from app.assets import default_asset_store

    if not 1 <= len(asset_ids) <= MAX_BATCH_ITEMS:
        raise RecipeError(f"a batch takes one to {MAX_BATCH_ITEMS} inputs")
    recipe = get_recipe(recipe_id)
    store = default_asset_store()
    inputs = []
    for asset_id in dict.fromkeys(asset_ids):
        asset = store.get_asset(asset_id)
        if asset is None or not str(asset.mime_type or "").startswith("audio/"):
            raise RecipeError(f"{asset_id} is not a stored recording")
        inputs.append((asset_id, content_hash(asset)))
    context = _tenant()
    run_id = f"vbatch:{uuid.uuid4().hex}"
    with _work() as work:
        work.connection.execute(
            """INSERT INTO omnix_voice_batch_runs (id, workspace_id, owner_user_id, recipe_id, recipe_version, steps,
                                                   title, watch_folder)
               VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)""",
            (run_id, context.workspace_id, context.user_id, recipe["id"], recipe["version"], json.dumps(recipe["steps"]),
             title or recipe["name"], watch_folder))
        for position, (asset_id, digest) in enumerate(inputs):
            earlier = work.connection.execute(
                """SELECT item.outputs FROM omnix_voice_batch_items AS item
                     JOIN omnix_voice_batch_runs AS run ON run.workspace_id = item.workspace_id AND run.id = item.run_id
                    WHERE item.workspace_id = %s AND item.input_hash = %s AND item.status = 'done'
                      AND run.recipe_id = %s AND run.recipe_version = %s
                    ORDER BY item.updated_at DESC LIMIT 1""",
                (context.workspace_id, digest, recipe["id"], recipe["version"])).fetchone()
            work.connection.execute(
                """INSERT INTO omnix_voice_batch_items (id, workspace_id, run_id, position, source_asset_id, input_hash,
                                                        current_asset_id, status, outputs, output_name)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)""",
                (f"vbitem:{uuid.uuid4().hex}", context.workspace_id, run_id, position, asset_id, digest, asset_id,
                 "skipped" if earlier else "pending", json.dumps(earlier[0] if earlier else []),
                 (output_names or {}).get(asset_id, "")))
        work.commit()
    return get_run(run_id)


def get_run(run_id: str) -> dict[str, Any]:
    context = _tenant()
    with _work() as work:
        row = work.connection.execute(
            f"SELECT {', '.join(_RUN_COLUMNS)} FROM omnix_voice_batch_runs WHERE workspace_id = %s AND id = %s",
            (context.workspace_id, run_id)).fetchone()
        items = work.connection.execute(
            f"SELECT {', '.join(_ITEM_COLUMNS)} FROM omnix_voice_batch_items WHERE workspace_id = %s AND run_id = %s "
            "ORDER BY position, id", (context.workspace_id, run_id)).fetchall()
        work.rollback()
    if row is None:
        raise AutomationNotFound(run_id)
    run = _row(_RUN_COLUMNS, row)
    run["items"] = [_row(_ITEM_COLUMNS, item) for item in items]
    counts: dict[str, int] = {}
    for item in run["items"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    run["counts"] = counts
    return run


def list_runs() -> list[dict[str, Any]]:
    context = _tenant()
    with _work() as work:
        rows = work.connection.execute(
            f"SELECT {', '.join(_RUN_COLUMNS)} FROM omnix_voice_batch_runs WHERE workspace_id = %s "
            "ORDER BY created_at DESC, id LIMIT 100", (context.workspace_id,)).fetchall()
        work.rollback()
    return [_row(_RUN_COLUMNS, row) for row in rows]


def cancel_run(run_id: str) -> dict[str, Any]:
    context = _tenant()
    with _work() as work:
        changed = work.connection.execute(
            """UPDATE omnix_voice_batch_runs SET status = 'cancelled', updated_at = clock_timestamp()
                WHERE workspace_id = %s AND id = %s AND status = 'running'""", (context.workspace_id, run_id)).rowcount
        running: list[str] = []
        if changed:
            running = [str(row[0]) for row in work.connection.execute(
                """UPDATE omnix_voice_batch_items SET status = 'failed', error = 'cancelled', updated_at = clock_timestamp()
                    WHERE workspace_id = %s AND run_id = %s AND status IN ('pending', 'running')
                    RETURNING job_id""", (context.workspace_id, run_id)).fetchall() if row[0]]
        work.commit()
    if running:
        _cancel_jobs(running)
    return get_run(run_id)


def _cancel_jobs(job_ids: list[str]) -> None:
    """Ask the jobs a cancelled run left running to stop (best effort: the run is already cancelled)."""
    from app.jobs.models import CancelJobRequest
    from app.jobs.store import default_job_store

    try:
        store = default_job_store()
    except RuntimeError:
        return
    cancel = getattr(store, "request_cancel", None)
    for job_id in job_ids:
        try:
            if cancel is not None:
                cancel(job_id, CancelJobRequest(reason="batch run cancelled"))
        except Exception:
            logger.warning("Job %s of a cancelled batch could not be cancelled", job_id, exc_info=True)


# --- the advancer -----------------------------------------------------------------------------------


def _outputs_of(job: Any, step: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    """What a finished step made, and the asset the next step takes (empty when it made none)."""
    refs = [dict(ref) for ref in (getattr(job, "output_refs", None) or []) if isinstance(ref, dict)]
    outputs = [{"tool": step["tool"], **{key: ref[key] for key in ("asset_id", "kind", "type", "title", "detected",
                                                                    "probability", "message") if key in ref}}
               for ref in refs]
    # Isolation makes two stems: the next step works on the voice, never the background.
    preferred = [ref for ref in refs if ref.get("kind") == "stem_vocals"] or refs
    next_asset = next((str(ref["asset_id"]) for ref in preferred if ref.get("asset_id")), "")
    return outputs, next_asset


class BatchAdvancer:
    """Moves every running batch one step: finished jobs on, failed ones retried, pending ones submitted."""

    def __init__(self, *, job_store_factory: Callable[[], Any] | None = None,
                 on_item_done: Callable[[dict[str, Any], dict[str, Any]], None] | None = None) -> None:
        self.job_store_factory = job_store_factory or self._default_store
        self.on_item_done = on_item_done

    @staticmethod
    def _default_store() -> Any:
        from app.jobs.store import default_job_store

        return default_job_store()

    def tick(self) -> dict[str, int]:
        from app.persistence.tenant_scope import system_scope

        with system_scope("voice.automation"), _work() as work:
            runs = work.connection.execute(
                "SELECT id, workspace_id, owner_user_id FROM omnix_voice_batch_runs WHERE status = 'running' "
                "ORDER BY updated_at LIMIT 50").fetchall()
            work.rollback()
        from app.runtime.tenant_context import TenantAccessDenied

        totals: dict[str, int] = {}
        for run_id, workspace_id, owner in runs:
            try:
                for key, value in self._advance_as(str(run_id), str(workspace_id), str(owner or "")).items():
                    totals[key] = totals.get(key, 0) + value
            except TenantAccessDenied:
                # Its owner left the workspace: nobody can run it any more, so it stops instead of waiting forever.
                self._abandon(str(run_id), "the run's owner is no longer a member of this workspace")
            except Exception:
                logger.warning("Batch run %s could not be advanced", run_id, exc_info=True)
                self._requeue(str(run_id))  # behind the other runs, so a failing run never starves them
        return totals

    @staticmethod
    def _abandon(run_id: str, reason: str) -> None:
        from app.persistence.tenant_scope import system_scope

        with system_scope("voice.automation"), _work() as work:
            work.connection.execute(
                """UPDATE omnix_voice_batch_items SET status = 'failed', error = %s, job_id = '',
                          updated_at = clock_timestamp()
                    WHERE run_id = %s AND status IN ('pending', 'running')""", (reason, run_id))
            work.connection.execute(
                """UPDATE omnix_voice_batch_runs SET status = 'failed', updated_at = clock_timestamp()
                    WHERE id = %s AND status = 'running'""", (run_id,))
            work.commit()

    @staticmethod
    def _requeue(run_id: str) -> None:
        from app.persistence.tenant_scope import system_scope

        try:
            with system_scope("voice.automation"), _work() as work:
                work.connection.execute(
                    "UPDATE omnix_voice_batch_runs SET updated_at = clock_timestamp() WHERE id = %s AND status = 'running'",
                    (run_id,))
                work.commit()
        except Exception:
            logger.warning("Batch run %s could not be moved back in the queue", run_id, exc_info=True)

    def _advance_as(self, run_id: str, workspace_id: str, owner: str) -> dict[str, int]:
        from app.persistence.identity_service import PostgresIdentityRepository
        from app.persistence.tenant_scope import system_scope
        from app.runtime.tenant_context import pop_tenant, push_tenant

        with system_scope("voice.automation"), _work() as work:
            context = PostgresIdentityRepository(work.connection).load_context(user_id=owner, workspace_id=workspace_id)
            work.rollback()
        token = push_tenant(context)
        try:
            return self.advance(run_id)
        finally:
            pop_tenant(token)

    def advance(self, run_id: str) -> dict[str, int]:
        """One pass over a run, in its own workspace (the tenant is already set).

        Every job-worker process runs an advancer, so each transition is a
        compare-and-set on the item's state as this pass read it, and a step's
        job is created once per item, step and attempt (``create_job_once``):
        two advancers never submit an item twice or move it on twice.
        """
        run = get_run(run_id)
        steps, store, moved = run["steps"], self.job_store_factory(), {"submitted": 0, "done": 0, "retried": 0, "failed": 0}
        for item in [entry for entry in run["items"] if entry["status"] == "running"]:
            if not item["job_id"]:
                # Claimed but its job id never recorded (a crash in between): the same key finds the same job.
                self._submit(store, steps, item, moved)
                continue
            job = store.get_job(item["job_id"])
            status = str(getattr(getattr(job, "status", None), "value", getattr(job, "status", "")) or "")
            if job is not None and status == "completed":
                outputs, next_asset = _outputs_of(job, steps[item["step_index"]])
                index = item["step_index"] + 1
                finished = index >= len(steps)
                if not self._move_item(item, status="done" if finished else "pending", step_index=index,
                                       current_asset_id=next_asset or item["current_asset_id"],
                                       outputs=item["outputs"] + outputs, attempts=0, job_id="", error=""):
                    continue  # another advancer moved it first
                if finished:
                    moved["done"] += 1
                    if self.on_item_done is not None and run.get("watch_folder"):
                        try:
                            self.on_item_done(run, {**item, "outputs": item["outputs"] + outputs})
                        except Exception:  # the item is done; a delivery failure must not stall the run
                            logger.warning("Batch item %s: its outputs could not be delivered", item["id"],
                                           exc_info=True)
            elif job is None or status in {"failed", "canceled", "cancelled", "stale"}:
                error = str(getattr(getattr(job, "error", None), "message", "") or status) if job else "the job is gone"
                retryable = bool(getattr(getattr(job, "error", None), "retryable", True)) if job else True
                if item["attempts"] + 1 < MAX_ATTEMPTS and retryable and status not in {"canceled", "cancelled"}:
                    if self._move_item(item, status="pending", attempts=item["attempts"] + 1, error=error, job_id=""):
                        moved["retried"] += 1
                elif self._move_item(item, status="failed", error=error, job_id=""):
                    moved["failed"] += 1
        run = get_run(run_id)
        active = sum(1 for entry in run["items"] if entry["status"] == "running")
        for item in [entry for entry in run["items"] if entry["status"] == "pending"][: max(0, ACTIVE_PER_RUN - active)]:
            if self._move_item(item, status="running", job_id=""):
                self._submit(store, steps, {**item, "status": "running", "job_id": ""}, moved)
        run = get_run(run_id)
        if all(entry["status"] in {"done", "failed", "skipped"} for entry in run["items"]):
            finished = "failed" if run["items"] and all(entry["status"] == "failed" for entry in run["items"]) else "done"
            self._finish_run(run_id, finished)
        else:
            self._touch_run(run_id)
        return moved

    def _submit(self, store: Any, steps: list[dict[str, Any]], item: dict[str, Any], moved: dict[str, int]) -> None:
        """Create the claimed item's job (once per item, step and attempt) and record it."""
        from .job_submission import submit_job

        step = steps[item["step_index"]]
        request = job_request(step, item["current_asset_id"], item_id=item["id"])
        try:
            job = submit_job(request, job_store=store,
                             idempotency_key=f"voice-batch:{item['id']}:{item['step_index']}:{item['attempts']}")
        except Exception as exc:  # a step the registry refuses fails its item, not the run
            logger.warning("Batch item %s: the %s step could not be submitted", item["id"], step["tool"], exc_info=True)
            if self._move_item(item, status="failed", error=f"could not submit: {type(exc).__name__}"):
                moved["failed"] += 1
            return
        if self._move_item(item, job_id=job.id):
            moved["submitted"] += 1
        else:
            # The item moved on while its job was created (its run was cancelled): nobody waits for this job.
            _cancel_jobs([job.id])

    @staticmethod
    def _move_item(item: dict[str, Any], **values: Any) -> bool:
        """Update the item only if it is still as this pass read it (status, step, attempt, job)."""
        context = _tenant()
        assignments, parameters = ["updated_at = clock_timestamp()"], []
        for key, value in values.items():
            assignments.append(f"{key} = %s::jsonb" if key == "outputs" else f"{key} = %s")
            parameters.append(json.dumps(value) if key == "outputs" else value)
        with _work() as work:
            changed = work.connection.execute(
                f"""UPDATE omnix_voice_batch_items SET {', '.join(assignments)}
                     WHERE workspace_id = %s AND id = %s AND status = %s AND step_index = %s AND attempts = %s
                       AND job_id = %s""",
                (*parameters, context.workspace_id, item["id"], item["status"], item["step_index"], item["attempts"],
                 item["job_id"])).rowcount
            work.commit()
        return bool(changed)

    @staticmethod
    def _touch_run(run_id: str) -> None:
        """Record the pass, so ``tick`` serves the runs it saw least recently first."""
        context = _tenant()
        with _work() as work:
            work.connection.execute(
                """UPDATE omnix_voice_batch_runs SET updated_at = clock_timestamp()
                    WHERE workspace_id = %s AND id = %s AND status = 'running'""", (context.workspace_id, run_id))
            work.commit()

    @staticmethod
    def _finish_run(run_id: str, status: str) -> None:
        context = _tenant()
        with _work() as work:
            work.connection.execute(
                """UPDATE omnix_voice_batch_runs SET status = %s, updated_at = clock_timestamp()
                    WHERE workspace_id = %s AND id = %s AND status = 'running'""", (status, context.workspace_id, run_id))
            work.commit()


class AutomationLoop:
    """Runs the batch advancer (and the watch folders it is given) every few seconds in a worker process."""

    def __init__(self, ticks: list[Callable[[], Any]], *, interval: float = TICK_SECONDS) -> None:
        self.ticks = ticks
        self.interval = interval
        self.last_error = ""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="omnix-voice-automation", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            for tick in self.ticks:
                try:
                    tick()
                    self.last_error = ""
                except Exception as exc:  # one bad tick must not stop the loop
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    logger.warning("Voice automation tick failed: %s", exc)
            self._stop.wait(self.interval)

    def snapshot(self) -> dict[str, Any]:
        return {"last_error": self.last_error, "running": bool(self._thread and self._thread.is_alive()),
                "at": time.time()}


def create_automation_worker(runtime_state: Any = None) -> Any:
    """The voice feature's batch and watch-folder worker, in each job-worker process (PostgreSQL only)."""
    import asyncio

    from app.persistence.runtime import uses_postgresql_runtime
    from app.runtime.background import BackgroundWorker
    from app.runtime.capabilities import RuntimeCapability

    if not uses_postgresql_runtime():
        return None
    from .job_submission import use_job_registry
    from .watch_folders import WatchFolders

    if runtime_state is not None:
        use_job_registry(lambda: getattr(runtime_state, "job_handler_registry", None))

    watch = WatchFolders.from_configuration()
    advancer = BatchAdvancer(on_item_done=watch.deliver if watch else None)
    loop = AutomationLoop([advancer.tick, *([watch.tick] if watch else [])])

    async def startup() -> None:
        await asyncio.to_thread(loop.start)

    async def shutdown() -> None:
        await asyncio.to_thread(loop.stop)

    return BackgroundWorker(name="voice-automation", monitor=loop, startup=(startup,), shutdown=(shutdown,),
                            requires=frozenset({RuntimeCapability.RUN_JOB_WORKERS}))


__all__ = [
    "AutomationNotFound",
    "BatchAdvancer",
    "RecipeError",
    "TOOLS",
    "cancel_run",
    "create_automation_worker",
    "delete_recipe",
    "get_recipe",
    "get_run",
    "job_request",
    "list_recipes",
    "list_runs",
    "save_recipe",
    "start_batch",
    "validate_steps",
]
