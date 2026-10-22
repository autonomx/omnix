"""The desktop setup screen's API: what this machine can run, and installing it (desktop roadmap §4.5, DT-2.4).

    GET  /api/model-packs               hardware, bundles with verdicts, runtime packs and models
    POST /api/model-packs/selection     the download a selection of bundles needs (a shared runtime once)
    GET  /api/model-packs/capabilities  which capabilities are installed and answering, for the UI to adapt
    POST /api/model-packs/install       a models.install job for a bundle, runtime pack or model
    POST /api/model-packs/remove        a models.remove job
    POST /api/model-packs/verify        a models.verify job (every file against its digest)

Reads need ``settings:read``, so guests see the status but never the controls.
Installs go through the same submission policy as ``POST /api/jobs``
(``model_packs.check_submission``), and these routes return its reason
("only the workspace owner can install ...", "accept the licences first ...")
instead of a bare 403 or 422.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.jobs.models import JobRecord
from app.security.permissions import requires

logger = logging.getLogger(__name__)

# Bundle capability -> the gateway's service endpoint that serves it.
_SERVICE_OF_CAPABILITY = {"live_stt": "stt", "stt_batch": "stt", "tts": "tts", "image": "image"}


class PackVerdict(BaseModel):
    """One bundle on this machine: what it installs and whether it can run here."""

    bundle: str
    label: str
    description: str
    capability: str
    status: Literal["fits", "warn", "unavailable"]
    reasons: list[str] = Field(default_factory=list)
    action: dict[str, str] | None = None
    models: list[str] = Field(default_factory=list)
    runtimes: list[str] = Field(default_factory=list)
    installed: bool = False
    model_bytes: int = 0
    runtime_bytes: int = 0
    recommended: bool = False
    note: str = ""


class PackRuntimeStatus(BaseModel):
    id: str
    label: str
    kind: str
    platform: str
    accelerator: str
    base: str
    licences: list[str] = Field(default_factory=list)
    requires: dict[str, str] = Field(default_factory=dict)
    installed: bool
    current: bool
    installed_at: str = ""
    download_bytes: int = 0


class PackModelLicence(BaseModel):
    id: str
    url: str
    commercial_use: bool
    gated: bool
    output_terms: str = ""


class PackModelStatus(BaseModel):
    id: str
    label: str
    repo: str
    revision: str
    size_bytes: int
    installed: bool
    disk_bytes: int = 0
    licence: PackModelLicence
    accepted: bool = False


class ModelPacksStatus(BaseModel):
    """The setup screen's data. ``enabled`` is false outside the desktop app, and the rest is then empty."""

    enabled: bool
    platform: str = ""
    hardware: dict[str, Any] = Field(default_factory=dict)
    bundles: list[PackVerdict] = Field(default_factory=list)
    runtimes: list[PackRuntimeStatus] = Field(default_factory=list)
    models: list[PackModelStatus] = Field(default_factory=list)
    packs_folder: str = ""


class SelectionSize(BaseModel):
    model_bytes: int
    runtime_bytes: int
    total_bytes: int


class CapabilityState(BaseModel):
    bundle: str
    label: str
    installed: bool
    running: bool


class CapabilitiesResponse(BaseModel):
    desktop: bool
    capabilities: dict[str, CapabilityState]


class PackTarget(BaseModel):
    bundle_id: str = Field(default="", max_length=100)
    runtime_id: str = Field(default="", max_length=100)
    model_id: str = Field(default="", max_length=200)
    accept_terms: bool = False

    @model_validator(mode="after")
    def _one_target(self) -> PackTarget:
        named = [value for value in (self.bundle_id, self.runtime_id, self.model_id) if value.strip()]
        if len(named) != 1:
            raise ValueError("name exactly one of bundle_id, runtime_id or model_id")
        return self


class SelectionRequest(BaseModel):
    bundles: list[str] = Field(default_factory=list, max_length=20)


def _require_desktop() -> None:
    from app.models.packs import desktop_mode

    if not desktop_mode():
        raise HTTPException(status_code=404, detail="model_packs_not_available")


def _service_answers(service: str) -> bool:
    from app.runtime.config import get_runtime_config
    from app.runtime.http_client import shared_http_client

    endpoint = getattr(get_runtime_config(), service, None)
    if endpoint is None:
        return False
    try:
        response = shared_http_client(f"{service}-service").get(endpoint.url.rstrip("/") + "/health", timeout=1.5,
                                                                retry=False)
    except Exception:
        return False
    return response.status_code == 200


def capabilities() -> dict[str, Any]:
    """Per bundle capability: installed (desktop packs present; always true outside the desktop app) and running."""
    from app.models import catalog as model_catalog
    from app.models import packs

    catalog = model_catalog.load()
    platform = model_catalog.current_platform()
    answers: dict[str, bool] = {}
    found: dict[str, Any] = {}
    for bundle in catalog.bundles.values():
        service = _SERVICE_OF_CAPABILITY.get(bundle.capability, "")
        if service and service not in answers:
            answers[service] = _service_answers(service)
        installed = True
        if packs.desktop_mode():
            variant = bundle.variant(platform)
            if variant is None:
                installed = False
            else:
                runtimes, models = packs.runtime_store(catalog), packs.model_store(catalog)
                installed = all(models.installed(model_id) for model_id in variant.models) and all(
                    runtimes.current(pack.id) for pack in catalog.runtime_closure(variant.runtimes))
        found[bundle.capability] = {"bundle": bundle.id, "label": bundle.label, "installed": installed,
                                    "running": answers.get(service, False)}
    return {"desktop": packs.desktop_mode(), "capabilities": found}


def _submit(job_type: str, target: PackTarget) -> Any:
    from app.runtime.tenant_context import TenantAccessDenied

    from .job_submission import submit_job
    from .model_install import ModelInstallError

    payload: dict[str, Any] = {key: value for key, value in target.model_dump().items() if value}
    try:
        return submit_job({"module": "voice", "type": job_type, "resource_class": "cpu", "input_payload": payload})
    except TenantAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc) or "forbidden") from exc
    except ModelInstallError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"job_input_invalid:{type(exc).__name__}") from exc


def register_model_pack_routes(router: APIRouter, state: Any) -> None:
    del state

    @router.get("/api/model-packs", response_model=ModelPacksStatus, openapi_extra=requires("settings:read"))
    def model_packs_status() -> dict[str, Any]:
        """The setup screen: this machine, what it can run, and what is installed."""
        from app.models.packs import desktop_mode

        if not desktop_mode():
            return {"enabled": False}
        from .model_packs import setup_status

        return {"enabled": True, **setup_status()}

    @router.post("/api/model-packs/selection", response_model=SelectionSize, openapi_extra=requires("settings:read"))
    def model_packs_selection(request: SelectionRequest) -> dict[str, Any]:
        _require_desktop()
        from app.models import catalog as model_catalog
        from app.models import packs
        from app.models.verdicts import Installed, selection_size

        catalog = model_catalog.load()
        platform = model_catalog.current_platform()
        runtimes, models = packs.runtime_store(catalog), packs.model_store(catalog)
        unknown = [item for item in request.bundles if item not in catalog.bundles]
        if unknown:
            raise HTTPException(status_code=404, detail=f"unknown_bundles:{','.join(unknown)}")
        installed = Installed(
            runtimes=frozenset(pack.id for pack in catalog.runtimes.values() if runtimes.current(pack.id)),
            models=frozenset(entry.id for entry in catalog.models.values() if entry.pinned and models.installed(entry.id)),
        )
        return selection_size(catalog, request.bundles, platform, installed, runtimes.download_bytes)

    @router.get("/api/model-packs/capabilities", response_model=CapabilitiesResponse,
                openapi_extra=requires("settings:read"))
    def model_packs_capabilities() -> dict[str, Any]:
        return capabilities()

    @router.post("/api/model-packs/install", response_model=JobRecord, openapi_extra=requires("models:admin"))
    def model_packs_install(target: PackTarget) -> Any:
        _require_desktop()
        return _submit("models.install", target)

    @router.post("/api/model-packs/remove", response_model=JobRecord, openapi_extra=requires("models:admin"))
    def model_packs_remove(target: PackTarget) -> Any:
        _require_desktop()
        return _submit("models.remove", target)

    @router.post("/api/model-packs/verify", response_model=JobRecord, openapi_extra=requires("models:admin"))
    def model_packs_verify(target: PackTarget) -> Any:
        _require_desktop()
        return _submit("models.verify", target)


__all__ = ["capabilities", "register_model_pack_routes"]
