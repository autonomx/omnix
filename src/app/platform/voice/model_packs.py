"""Installing what the desktop setup screen offers: bundles, runtime packs and models (desktop roadmap §4.5).

``models.install`` and ``models.remove`` jobs name one of

- ``bundle_id``: a capability (its models and the runtime packs they run in);
- ``runtime_id``: one runtime pack (and the Torch layer under it);
- ``model_id``: one model.

Submission (``check_submission``) enforces who may ask:

- model installs and licence acceptance need ``models:admin`` (owner or admin);
- anything that installs or removes a runtime pack needs ``models:runtimes:admin``,
  which only the owner holds: runtime packs are executable code. An admin who
  picks a bundle whose runtime is missing is refused with the runtime's name;
  nothing is queued on the owner's behalf;
- ``accept_terms`` records the user's acceptance of each model's licence at its
  pinned revision (migration 0168). The job refuses any model without one.

The job itself (``execute``) runs in the job worker: bases first, then the
runtime packs, then the models, with progress on the job and cancellation
honoured between files.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app.config.env import environment
from app.models import catalog as model_catalog
from app.models import packs
from app.models.catalog import Catalog, ModelEntry
from app.runtime.tenant_context import TenantAccessDenied, current_tenant

from .model_install import ModelInstallError

logger = logging.getLogger(__name__)

PROGRESS_INTERVAL_SECONDS = 1.0
CANCEL_CHECK_SECONDS = 2.0


def _catalog() -> Catalog:
    return model_catalog.load()


def _platform() -> str:
    return model_catalog.current_platform()


def _target(payload: dict[str, Any]) -> tuple[str, str]:
    for key in ("bundle_id", "runtime_id", "model_id"):
        value = str(payload.get(key) or "").strip()
        if value:
            return key, value
    raise ModelInstallError("name a bundle_id, runtime_id or model_id")


def _bundle_parts(catalog: Catalog, bundle_id: str) -> tuple[list[ModelEntry], list[str]]:
    """The bundle's models and runtime closure on this platform."""
    try:
        bundle = catalog.bundle(bundle_id)
    except KeyError as exc:
        raise ModelInstallError(str(exc)) from exc
    variant = bundle.variant(_platform())
    if variant is None:
        raise ModelInstallError(f"{bundle.label} is not available on this platform")
    models = [catalog.model(model_id) for model_id in variant.models]
    runtimes = [pack.id for pack in catalog.runtime_closure(variant.runtimes)]
    return models, runtimes


def plan(payload: dict[str, Any], *, removing: bool = False) -> dict[str, Any]:
    """What a job will touch: {"models": [...entries], "runtimes": [...ids]}."""
    catalog = _catalog()
    kind, value = _target(payload)
    if kind == "bundle_id":
        models, runtimes = _bundle_parts(catalog, value)
    elif kind == "runtime_id":
        try:
            pack = catalog.runtime(value)
        except KeyError as exc:
            raise ModelInstallError(str(exc)) from exc
        if pack.platform != _platform():
            raise ModelInstallError(f"{pack.label} is for {pack.platform}, not this computer")
        models, runtimes = [], [value] if removing else [item.id for item in catalog.runtime_closure([value])]
    else:
        try:
            entry = catalog.model(value)
        except KeyError as exc:
            raise ModelInstallError(str(exc)) from exc
        if not entry.pinned:
            raise ModelInstallError(f"{entry.label} is downloaded by its own package on first use, not installed here")
        if not catalog.runtimes_for_model(entry.id, _platform()):
            raise ModelInstallError(f"{entry.label} is not available in the desktop app on this platform yet")
        models, runtimes = [entry], []
    return {"kind": kind, "id": value, "models": models, "runtimes": runtimes}


def _missing_runtimes(runtimes: list[str]) -> list[str]:
    store = packs.runtime_store()
    return [runtime_id for runtime_id in runtimes if not store.current(runtime_id)]


AUTHORIZED_RUNTIMES = "authorized_runtimes"


def _hardware_facts() -> dict[str, Any]:
    from app.models.hardware import probe

    return probe(packs_folder=packs.runtime_store(_catalog()).root)


def _refuse_unavailable(bundle_id: str) -> None:
    """A bundle this computer cannot run (no NVIDIA GPU, an old driver, too little disk) is not queued at all."""
    from app.models.verdicts import bundle_verdict

    catalog = _catalog()
    store = packs.runtime_store(catalog)
    # What is installed already does not count toward the disk space the download needs.
    verdict = bundle_verdict(catalog.bundles[bundle_id], catalog, {"platform": _platform(), **_hardware_facts()},
                             _installed_set(catalog), store.download_bytes)
    if verdict.status == "unavailable":
        raise ModelInstallError(f"{verdict.label} cannot run on this computer: {' '.join(verdict.reasons)}")


def check_submission(job_type: str, payload: dict[str, Any]) -> list[str]:
    """Who may submit this install or removal, and record licence acceptances (desktop mode).

    Returns the runtime packs the submitter may install or remove. The submission policy stores that list in the
    job (replacing anything the client sent), and the job changes no other runtime when it runs: a retry after an
    app update, or after the owner removed a runtime, must not install one on an admin's authority."""
    from app.security.permissions import has_permission

    from . import licence_acceptances

    tenant = current_tenant()
    if not has_permission(tenant.roles, "models:admin"):
        raise TenantAccessDenied("installing models needs the workspace owner or an admin")
    planned = plan(payload, removing=job_type == "models.remove")
    catalog = _catalog()
    if job_type == "models.install":
        if planned["kind"] == "bundle_id":
            _refuse_unavailable(planned["id"])
        runtime_change = _missing_runtimes(planned["runtimes"])
    elif planned["kind"] == "runtime_id":
        runtime_change = list(planned["runtimes"])
    elif planned["kind"] == "bundle_id":
        runtime_change = runtimes_removed_with_bundle(planned["id"], planned["runtimes"])
    else:
        runtime_change = []
    runtime_owner = has_permission(tenant.roles, "models:runtimes:admin")
    if runtime_change and not runtime_owner:
        labels = ", ".join(catalog.runtime(runtime_id).label for runtime_id in runtime_change)
        verb = "install" if job_type == "models.install" else "remove"
        raise TenantAccessDenied(f"only the workspace owner can {verb} {labels}; ask them to do it")
    authorized = list(planned["runtimes"]) if runtime_owner else []
    if job_type != "models.install" or not planned["models"]:
        return authorized
    if not payload.get("accept_terms"):
        labels = ", ".join(f"{entry.label} ({entry.licence.id})" for entry in planned["models"])
        raise ModelInstallError(f"accept the licences first: {labels}")
    if licence_acceptances.available():
        licence_acceptances.record(planned["models"])
    return authorized


class _JobFeedback:
    """Throttled progress on the job, and whether the user asked to cancel it."""

    def __init__(self, job_store: Any, job: Any) -> None:
        self.job_store = job_store
        self.job = job
        self._last_progress = 0.0
        self._last_check = 0.0
        self._cancelled = False

    def progress(self, done: int, total: int, message: str) -> None:
        now = time.monotonic()
        if self.job_store is None or (now - self._last_progress < PROGRESS_INTERVAL_SECONDS and done < total):
            return
        self._last_progress = now
        from app.jobs.models import JobProgress

        try:
            self.job_store.update_progress(self.job.id, JobProgress(current=done, total=max(total, 1), message=message))
        except Exception:  # progress is best effort; the install goes on
            logger.debug("Could not report pack progress", exc_info=True)

    def cancelled(self) -> bool:
        if self._cancelled:
            return True
        now = time.monotonic()
        if self.job_store is None or now - self._last_check < CANCEL_CHECK_SECONDS:
            return False
        self._last_check = now
        from app.jobs.models import JobStatus

        try:
            current = self.job_store.get_job(self.job.id)
        except Exception:
            return False
        self._cancelled = current is not None and current.status in {JobStatus.CANCEL_REQUESTED, JobStatus.CANCELED}
        return self._cancelled


def _require_acceptance(entry: ModelEntry) -> None:
    from . import licence_acceptances

    if licence_acceptances.available() and not licence_acceptances.accepted(entry.id, entry.revision, entry.licence.id):
        raise ModelInstallError(f"{entry.label}'s licence ({entry.licence.id}) has not been accepted for revision "
                                f"{entry.revision[:12]}; accept it and install again")


def _hub_token() -> str | None:
    from app.security.provider_secret_store import load_model_hub_token

    return load_model_hub_token() or None


def _installed_bundles_needing(runtime_id: str, *, except_bundle: str = "") -> list[str]:
    """Labels of installed bundles on this platform that stand on ``runtime_id``."""
    catalog = _catalog()
    models = packs.model_store(catalog)
    labels = []
    for bundle in catalog.bundles.values():
        if bundle.id == except_bundle:
            continue
        variant = bundle.variant(_platform())
        if variant is None:
            continue
        closure = [pack.id for pack in catalog.runtime_closure(variant.runtimes)]
        if runtime_id in closure and all(models.installed(model_id) for model_id in variant.models):
            labels.append(bundle.label)
    return labels


def _models_of_other_installed_bundles(bundle_id: str) -> set[str]:
    catalog = _catalog()
    models = packs.model_store(catalog)
    keep: set[str] = set()
    for bundle in catalog.bundles.values():
        variant = bundle.variant(_platform())
        if bundle.id == bundle_id or variant is None:
            continue
        if all(models.installed(model_id) for model_id in variant.models):
            keep.update(catalog.canonical_id(model_id) for model_id in variant.models)
    return keep


STOP_WAIT_SECONDS = 60.0


def _wait_until_stopped(service: str, *, timeout: float = STOP_WAIT_SECONDS) -> None:
    """Waits until the model service no longer answers on its port (the gateway knows it as OMNIX_<SERVICE>_URL)."""
    import urllib.request

    url = (environment().get(f"OMNIX_{service.upper()}_URL") or "").rstrip("/")
    if not url:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2):  # noqa: S310 - the loopback service URL
                pass
        except OSError:
            return
        time.sleep(1.0)


def _wait_for_services_on(runtime_id: str) -> None:
    """Before an update replaces a pack: wait for every model service standing on it to stop."""
    catalog = _catalog()
    for item in [runtime_id, *catalog.dependents(runtime_id)]:
        service = catalog.runtime(item).service
        if service:
            _wait_until_stopped(service)


def runtimes_removed_with_bundle(bundle_id: str, closure: list[str]) -> list[str]:
    """The bundle's runtime packs that go with it: installed, and needed by no other installed bundle or overlay.

    Overlays come before the Torch layer, so a layer goes only once nothing left stands on it."""
    catalog = _catalog()
    store = packs.runtime_store(catalog)
    removed: list[str] = []
    for runtime_id in reversed(closure):
        if not store.present(runtime_id) or _installed_bundles_needing(runtime_id, except_bundle=bundle_id):
            continue
        standing = [item for item in catalog.dependents(runtime_id) if store.installed(item) and item not in removed]
        if not standing:
            removed.append(runtime_id)
    return removed


def execute(job: Any, *, job_store: Any = None) -> dict[str, Any]:
    payload = job.input_payload or {}
    removing = job.type == "models.remove"
    planned = plan(payload, removing=removing)
    # Written by the submission policy from the submitter's roles; a client-supplied value never survives it.
    authorized = set(payload.get(AUTHORIZED_RUNTIMES) or ())
    feedback = _JobFeedback(job_store, job)
    catalog = _catalog()
    runtimes = packs.runtime_store(catalog)
    models = packs.model_store(catalog)
    if job.type == "models.verify":
        # A full check: every runtime file against its wheel's RECORD, every model file against its digest.
        report: dict[str, list[str]] = {}
        for runtime_id in planned["runtimes"]:
            report[catalog.runtime(runtime_id).label] = runtimes.verify(runtime_id)
        for entry in planned["models"]:
            report[entry.label] = models.verify(entry.id)
        problems = {label: items for label, items in report.items() if items}
        summary = "Everything checks out" if not problems else "; ".join(
            f"{label}: {', '.join(items[:3])}" for label, items in problems.items())
        return {"content": summary, "log_message": "Model packs verified",
                "output_refs": [{"type": "model_pack_verification", "target": planned["id"], "problems": problems}]}
    if removing:
        removed: list[str] = []
        bundle_id = planned["id"] if planned["kind"] == "bundle_id" else ""
        keep = _models_of_other_installed_bundles(bundle_id) if bundle_id else set()
        for entry in planned["models"]:
            if entry.id not in keep and models.installed(entry.id):
                models.remove(entry.id)
                removed.append(entry.label)
        targets = runtimes_removed_with_bundle(bundle_id, planned["runtimes"]) if bundle_id else planned["runtimes"]
        for runtime_id in targets:
            if not runtimes.present(runtime_id):
                continue
            if runtime_id not in authorized:
                if planned["kind"] == "runtime_id":
                    raise ModelInstallError(f"only the workspace owner can remove {catalog.runtime(runtime_id).label}")
                continue  # the submitter could remove the bundle's models, not the runtime
            service = catalog.runtime(runtime_id).service
            if service:
                # The supervisor stops a service within seconds of its bundle's models going; wait for that.
                _wait_until_stopped(service)
            try:
                runtimes.remove(runtime_id, needed_by=_installed_bundles_needing(runtime_id, except_bundle=bundle_id))
            except packs.PackRetryable:
                raise
            except packs.PackError as exc:
                raise ModelInstallError(str(exc)) from exc
            removed.append(catalog.runtime(runtime_id).label)
        return {"content": "Removed " + (", ".join(removed) or "nothing"), "log_message": "Model packs removed",
                "output_refs": [{"type": "model_pack", "target": planned["id"], "removed": removed}]}
    for entry in planned["models"]:
        _require_acceptance(entry)
    installed: list[str] = []
    try:
        for runtime_id in planned["runtimes"]:
            if runtimes.current(runtime_id):
                continue
            if runtime_id not in authorized:
                raise ModelInstallError(f"{catalog.runtime(runtime_id).label} needs installing first, and only the "
                                        "workspace owner can install it")
            runtimes.install(runtime_id, progress=feedback.progress, cancelled=feedback.cancelled,
                             before_swap=_wait_for_services_on)
            installed.append(catalog.runtime(runtime_id).label)
        token = _hub_token()
        for entry in planned["models"]:
            if models.installed(entry.id):
                continue
            models.install(entry.id, token=token, progress=feedback.progress, cancelled=feedback.cancelled)
            installed.append(entry.label)
    except (packs.PackCancelled, packs.PackRetryable):
        raise  # cancelled, or worth retrying: the job framework retries a download that broke off
    except packs.PackError as exc:
        raise ModelInstallError(str(exc)) from exc
    return {"content": "Installed " + (", ".join(installed) or "nothing new"), "log_message": "Model packs installed",
            "output_refs": [{"type": "model_pack", "target": planned["id"], "installed": installed}]}


def _installed_set(catalog: Catalog) -> Any:
    from app.models.verdicts import Installed

    platform = _platform()
    runtime_store, model_store = packs.runtime_store(catalog), packs.model_store(catalog)
    return Installed(
        runtimes=frozenset(pack.id for pack in catalog.runtimes.values()
                           if pack.platform == platform and runtime_store.current(pack.id)),
        models=frozenset(entry.id for entry in catalog.models.values()
                         if entry.pinned and model_store.installed(entry.id)),
    )


def setup_status(*, include_hardware: bool = True) -> dict[str, Any]:
    """What the setup screen and Settings → Models show: hardware, bundles with verdicts, runtimes, models."""
    from app.models.hardware import probe
    from app.models.verdicts import verdicts

    catalog = _catalog()
    platform = _platform()
    runtime_store = packs.runtime_store(catalog)
    model_store = packs.model_store(catalog)
    facts = probe(packs_folder=runtime_store.root) if include_hardware else {"platform": platform}
    installed = _installed_set(catalog)
    found = verdicts(catalog, facts, installed, runtime_store.download_bytes)
    model_ids = sorted({catalog.canonical_id(model_id) for bundle in catalog.bundles.values()
                        for variant in bundle.variants if variant.platform == platform for model_id in variant.models})
    accepted: dict[str, set[tuple[str, str]]] = {}
    from . import licence_acceptances

    if licence_acceptances.available():
        try:
            accepted = licence_acceptances.accepted_models()
        except Exception:
            logger.warning("Could not read licence acceptances", exc_info=True)
    return {
        "platform": platform,
        "hardware": facts,
        "bundles": [item.as_dict() for item in found],
        "runtimes": [runtime_store.status(pack.id) for pack in catalog.runtimes.values() if pack.platform == platform],
        "models": [{
            "id": entry.id, "label": entry.label, "repo": entry.repo, "revision": entry.revision,
            "size_bytes": entry.size, "installed": model_store.installed(entry.id),
            "disk_bytes": model_store.disk_bytes(entry.id) if model_store.installed(entry.id) else 0,
            "licence": entry.licence.as_dict(),
            "accepted": (entry.revision, entry.licence.id) in accepted.get(entry.id, set()),
        } for entry in (catalog.model(model_id) for model_id in model_ids)],
        "packs_folder": str(runtime_store.root),
    }


__all__ = ["check_submission", "execute", "plan", "runtimes_removed_with_bundle", "setup_status"]
