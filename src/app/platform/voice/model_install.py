"""``models.install`` and ``models.remove``: fetch or delete a catalogued speech model's weights.

Downloads come from the Hugging Face hub at the commit model catalog v2 pins,
resume after an interruption (the hub keeps partial files beside the target),
and every pinned file is checked against its catalogued SHA-256 before the
install counts. A model installs only when the request accepts its terms
(roadmap D-4); the acceptance, licence and commit are written to
``.omnix-model.json`` in the model folder.

Weights land under ``resources/models/<kind>/<repository name>``, the layout
the TTS and STT services already read. Environments are not installed here.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .model_catalog import SpeechModel, speech_model, speech_models

MARKER = ".omnix-model.json"


class ModelInstallError(ValueError):
    """The install request cannot succeed as asked (terms, token, source); retrying will not help."""


def models_root() -> Path:
    from app.runtime.paths import resources_models_root

    return resources_models_root()


def model_dir(model: SpeechModel) -> Path:
    return models_root() / model.kind / (model.folder or model.repo_id.split("/")[-1])


def _marker(model: SpeechModel) -> dict[str, Any] | None:
    path = model_dir(model) / MARKER
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _folder_bytes(folder: Path) -> int:
    total = 0
    for item in folder.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def service_environment(service: str, model_id: str = "") -> dict[str, Any]:
    """The model service's Python environment: whether it exists, and how to set it up when it does not.

    The install job downloads weights only; environments come from each service's
    hashed lock file (``src/services/<service>/<service>.lock.txt``). In the
    desktop app the environment is the model's runtime pack, ready when its
    manifest is current (desktop roadmap §4.5); the setup screen installs it.
    """
    from app.models import packs

    if packs.desktop_mode():
        return _pack_environment(model_id)
    from app.config.launcher import load_launcher_config
    from app.runtime.paths import repo_root

    launcher = load_launcher_config(repo_root())
    if service not in launcher.environments:
        return {"name": "", "ready": True, "setup": ""}
    python = Path(launcher.python(service))
    lock = Path("src") / "services" / service / f"{service}.lock.txt"
    name = launcher.environments[service]
    setup = ""
    if (repo_root() / lock).is_file():
        setup = (f"conda create -n {name} python=3.11 && conda run -n {name} "
                 f"python -m pip install --require-hashes -r {lock.as_posix()}")
    return {"name": name, "ready": python.is_file(), "setup": setup}


def _pack_environment(model_id: str) -> dict[str, Any]:
    from app.models import catalog as model_catalog
    from app.models import packs

    catalog = model_catalog.load()
    try:
        runtime_ids = catalog.runtimes_for_model(model_id, model_catalog.current_platform()) if model_id else []
    except KeyError:
        runtime_ids = []
    if not runtime_ids:
        return {"name": "", "ready": False, "setup": "", "available": False}
    store = packs.runtime_store(catalog)
    closure = [pack.id for pack in catalog.runtime_closure(runtime_ids)]
    missing = [catalog.runtime(item).label for item in closure if not store.current(item)]
    return {"name": catalog.runtime(runtime_ids[0]).label, "ready": not missing, "available": True,
            "setup": "" if not missing else "Install it from Settings, Models: " + ", ".join(missing)}


def _pack_status(model: SpeechModel) -> dict[str, Any]:
    from app.models import packs

    store = packs.model_store()
    installed = model.source == "huggingface" and store.installed(model.id)
    marker = store.marker(model.id) if installed else None
    status = "package" if model.source == "package" else "installed" if installed else "missing"
    return {
        **model.as_dict(),
        "status": status,
        "installed_revision": (marker or {}).get("commit", ""),
        "accepted_terms": installed,
        "disk_bytes": store.disk_bytes(model.id) if installed else 0,
        "environment": service_environment(model.service, model.id),
    }


def model_status(model: SpeechModel) -> dict[str, Any]:
    """Whether the weights are present, where they came from, and their disk use."""
    from app.models import packs

    if packs.desktop_mode():
        return _pack_status(model)
    folder = model_dir(model)
    marker = _marker(model)
    present = folder.is_dir() and any(entry.name != MARKER for entry in folder.iterdir()) if folder.exists() else False
    status = "installed" if marker and present else "present" if present else "missing"
    if model.source == "package":
        status = "package"
    return {
        **model.as_dict(),
        "status": status,
        "installed_revision": (marker or {}).get("commit", ""),
        "accepted_terms": bool((marker or {}).get("accepted_terms")),
        "disk_bytes": _folder_bytes(folder) if present else 0,
        "environment": service_environment(model.service),
    }


def list_model_status() -> list[dict[str, Any]]:
    return [model_status(model) for model in speech_models()]


def _hub_token() -> str | None:
    from app.security.provider_secret_store import load_model_hub_token

    return load_model_hub_token() or None


def install_model(model_id: str, *, accept_terms: bool = False, hub: Any = None) -> dict[str, Any]:
    """Download the model's weights; returns its status. ``hub`` is the huggingface_hub module (tests swap it)."""
    model = speech_model(model_id)
    if model.source != "huggingface":
        raise ModelInstallError(f"{model.label} is downloaded by its own package on first use, not installed here")
    if model.requires_acceptance and not accept_terms:
        reason = "is gated" if model.gated else f"is licensed {model.licence}" + (
            "" if model.commercial_use else " (not for commercial use)")
        raise ModelInstallError(f"{model.label} {reason}; accept its terms to install it")
    token = _hub_token()
    if model.gated and not token:
        raise ModelInstallError(f"{model.label} is gated; add a Hugging Face token and accept the terms on its model page")
    if hub is None:
        import huggingface_hub as hub

    folder = model_dir(model)
    folder.mkdir(parents=True, exist_ok=True)
    # The catalog pins the commit, so a resumed or repeated install fetches exactly the same files.
    commit = model.revision
    hub.snapshot_download(repo_id=model.repo_id, revision=commit, local_dir=str(folder), token=token,
                          allow_patterns=list(model.files) or None)
    _check_digests(model, folder)
    marker = {
        "model_id": model.id,
        "repo_id": model.repo_id,
        "revision": model.revision,
        "commit": commit,
        "licence": model.licence,
        "accepted_terms": bool(accept_terms) if model.requires_acceptance else False,
        "installed_at": datetime.now(timezone.utc).isoformat(),
    }
    (folder / MARKER).write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    return model_status(model)


def _require_recorded_acceptance(model: SpeechModel) -> None:
    """With PostgreSQL, the job also needs the acceptance the submission recorded (roadmap D-4)."""
    from . import licence_acceptances

    if model.requires_acceptance and licence_acceptances.available() and not licence_acceptances.accepted(
            model.id, model.revision):
        raise ModelInstallError(f"{model.label}'s licence ({model.licence}) has not been accepted for this revision; "
                                "accept it and install again")


def _check_digests(model: SpeechModel, folder: Path) -> None:
    """Every pinned file is in the folder with its catalogued SHA-256; anything else fails the install."""
    from app.models.catalog import load
    from app.models.downloads import sha256_file

    entry = load().model(model.id)
    for item in entry.files:
        target = folder / item.path
        if not target.is_file():
            raise ModelInstallError(f"{model.label}: {item.path} did not download")
        actual = sha256_file(target)
        if actual != item.sha256:
            target.unlink(missing_ok=True)
            raise ModelInstallError(f"{model.label}: {item.path} has SHA-256 {actual}, expected {item.sha256}")


def remove_model(model_id: str) -> dict[str, Any]:
    model = speech_model(model_id)
    folder = model_dir(model)
    root = models_root().resolve()
    resolved = folder.resolve()
    if root not in resolved.parents:
        raise ModelInstallError(f"refusing to delete {resolved}: it is outside {root}")
    if resolved.exists():
        shutil.rmtree(resolved)
    return model_status(model)


def execute_model_job(job: Any, *, job_store: Any = None) -> dict[str, Any]:
    from app.models import packs

    payload = job.input_payload or {}
    if packs.desktop_mode():
        from .model_packs import execute

        return execute(job, job_store=job_store)
    if payload.get("bundle_id") or payload.get("runtime_id"):
        raise ModelInstallError("bundles and runtime packs are installed by the desktop app")
    model_id = str(payload.get("model_id") or "").strip()
    if not model_id:
        raise ModelInstallError("model_id is required")
    try:
        speech_model(model_id)
    except KeyError as exc:
        raise ModelInstallError(str(exc)) from exc
    if job.type == "models.verify":
        raise ModelInstallError("verifying models is a desktop app tool")
    if job.type == "models.install":
        _require_recorded_acceptance(speech_model(model_id))
        status = install_model(model_id, accept_terms=bool(payload.get("accept_terms")))
        verb = "Installed"
    else:
        status = remove_model(model_id)
        verb = "Removed"
    return {
        "content": f"{verb} {status['label']}",
        "log_message": f"Speech model {verb.lower()}",
        "output_refs": [{"type": "model", "model_id": model_id, "status": status["status"],
                         "revision": status["installed_revision"], "disk_bytes": status["disk_bytes"]}],
    }


__all__ = [
    "MARKER",
    "ModelInstallError",
    "execute_model_job",
    "install_model",
    "list_model_status",
    "model_dir",
    "model_status",
    "models_root",
    "remove_model",
]
