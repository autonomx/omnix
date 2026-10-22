"""Desktop model packs: who may install what, licence acceptance, and the install and removal jobs (DT-2.2-2.4)."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from app.models import catalog as model_catalog
from app.models import packs
from app.platform.voice import licence_acceptances, model_pack_routes, model_packs
from app.platform.voice.model_install import ModelInstallError
from app.runtime.tenant_context import TenantAccessDenied, TenantContext, pop_tenant, push_tenant
from app.security.permissions import declared_permission, has_permission

REVISION = "0123456789abcdef0123456789abcdef01234567"
FILE = {"sha256": "a" * 64, "size": 1000}

CATALOG = model_catalog.parse_catalog({
    "runtimes": {
        "torch-win": {"label": "GPU runtime", "kind": "torch-layer", "platform": "windows-x64", "lock": "t", "accelerator": "cuda",
                      "files": "t.json"},
        "tts-win": {"label": "Voice output runtime", "kind": "overlay", "base": "torch-win", "accelerator": "cuda",
                    "platform": "windows-x64", "service": "tts", "lock": "tts", "files": "tts.json"},
        "stt-win": {"label": "Speech runtime", "kind": "overlay", "base": "torch-win", "platform": "windows-x64",
                    "service": "stt", "lock": "stt", "files": "stt.json"},
    },
    "bundles": {
        "voice-output": {"label": "Voice output", "capability": "tts", "variants": [
            {"platform": "windows-x64", "models": ["tts-model"], "runtimes": ["tts-win"], "accelerator": "cuda"}]},
        "voice-input": {"label": "Voice input", "capability": "live_stt", "variants": [
            {"platform": "windows-x64", "models": ["stt-model", "eou-model"], "runtimes": ["stt-win"]}]},
    },
    "models": {
        "tts-model": {"label": "TTS", "repo": "org/tts", "revision": REVISION, "service": "tts", "files": {"m": FILE},
                      "licence": {"id": "Apache-2.0", "url": "https://x"}},
        "stt-model": {"label": "STT", "repo": "org/stt", "revision": REVISION, "service": "stt", "files": {"m": FILE},
                      "licence": {"id": "CC-BY-4.0", "url": "https://y"}},
        "eou-model": {"label": "EOU", "repo": "org/eou", "revision": REVISION, "service": "stt", "files": {"m": FILE},
                      "licence": {"id": "NVIDIA Open Model License", "url": "https://z"}},
        "unbundled": {"label": "Unbundled", "repo": "org/u", "revision": REVISION, "service": "tts",
                      "files": {"m": FILE}},
    },
})


class _Runtimes:
    def __init__(self, installed: set[str] | None = None) -> None:
        self.have = set(installed or ())
        self.calls: list[str] = []
        self.root = "packs"

    def current(self, runtime_id: str) -> bool:
        return runtime_id in self.have

    installed = current

    def download_bytes(self, runtime_id: str) -> int:
        return 0
    present = current

    def install(self, runtime_id: str, **_: Any) -> dict:
        if CATALOG.runtime(runtime_id).base and CATALOG.runtime(runtime_id).base not in self.have:
            raise packs.PackError("base first")
        self.calls.append(f"install {runtime_id}")
        self.have.add(runtime_id)
        return {}

    def remove(self, runtime_id: str, *, needed_by=()) -> None:
        if list(needed_by):
            raise packs.PackError(f"needed by {', '.join(needed_by)}")
        self.calls.append(f"remove {runtime_id}")
        self.have.discard(runtime_id)


class _Models:
    def __init__(self, installed: set[str] | None = None) -> None:
        self.have = set(installed or ())
        self.calls: list[str] = []

    def installed(self, model_id: str) -> bool:
        return model_id in self.have

    present = installed

    def install(self, model_id: str, **_: Any) -> dict:
        self.calls.append(f"install {model_id}")
        self.have.add(model_id)
        return {}

    def remove(self, model_id: str) -> None:
        self.calls.append(f"remove {model_id}")
        self.have.discard(model_id)


@pytest.fixture
def desktop(monkeypatch, tmp_path):
    monkeypatch.setenv("OMNIX_PACKS_DIR", str(tmp_path))
    monkeypatch.setattr(model_catalog, "load", lambda *args, **kwargs: CATALOG)
    monkeypatch.setattr(model_catalog, "current_platform", lambda: "windows-x64")
    state = SimpleNamespace(runtimes=_Runtimes(), models=_Models(), accepted=set(), recorded=[])
    monkeypatch.setattr(packs, "runtime_store", lambda catalog=None: state.runtimes)
    monkeypatch.setattr(packs, "model_store", lambda catalog=None: state.models)
    monkeypatch.setattr(licence_acceptances, "available", lambda: True)
    monkeypatch.setattr(licence_acceptances, "record", lambda entries: state.recorded.extend(e.id for e in entries)
                        or state.accepted.update((e.id, e.revision) for e in entries))
    monkeypatch.setattr(licence_acceptances, "accepted", lambda model_id, revision, licence_id: (model_id, revision) in state.accepted)
    monkeypatch.setattr(model_packs, "_hub_token", lambda: None)
    state.facts = {"gpus": [{"name": "NVIDIA GeForce RTX 4090", "vendor": "nvidia", "vram_total_mb": 24564,
                             "vram_free_mb": 20000, "driver": "617.42"}], "nvidia_driver": "617.42"}
    monkeypatch.setattr(model_packs, "_hardware_facts", lambda: state.facts)
    return state


def _as(role: str):
    return push_tenant(TenantContext(user_id="user:a", workspace_id="workspace:a", membership_id="m:a",
                                     roles=frozenset({role})))


def test_only_the_owner_holds_the_runtime_permission() -> None:
    assert has_permission({"owner"}, "models:runtimes:admin")
    assert not has_permission({"admin"}, "models:runtimes:admin")
    assert has_permission({"admin"}, "models:admin")
    assert not has_permission({"member"}, "models:admin")


def test_a_member_cannot_install(desktop) -> None:
    token = _as("member")
    try:
        with pytest.raises(TenantAccessDenied):
            model_packs.check_submission("models.install", {"bundle_id": "voice-output", "accept_terms": True})
    finally:
        pop_tenant(token)


def test_an_admin_is_refused_a_bundle_whose_runtime_is_missing(desktop) -> None:
    token = _as("admin")
    try:
        with pytest.raises(TenantAccessDenied, match="only the workspace owner can install GPU runtime, Voice output runtime"):
            model_packs.check_submission("models.install", {"bundle_id": "voice-output", "accept_terms": True})
        with pytest.raises(TenantAccessDenied, match="only the workspace owner"):
            model_packs.check_submission("models.install", {"runtime_id": "torch-win"})
        # With the runtime there, an admin may install the bundle's models.
        desktop.runtimes.have.update({"torch-win", "tts-win"})
        model_packs.check_submission("models.install", {"bundle_id": "voice-output", "accept_terms": True})
    finally:
        pop_tenant(token)
    assert desktop.recorded == ["tts-model"]


def test_an_install_needs_the_licences_accepted(desktop) -> None:
    token = _as("owner")
    try:
        with pytest.raises(ModelInstallError, match="accept the licences first: TTS \\(Apache-2.0\\)"):
            model_packs.check_submission("models.install", {"bundle_id": "voice-output"})
        model_packs.check_submission("models.install", {"bundle_id": "voice-output", "accept_terms": True})
    finally:
        pop_tenant(token)
    assert ("tts-model", REVISION) in desktop.accepted


def test_a_bundle_this_computer_cannot_run_is_not_queued(desktop) -> None:
    desktop.facts = {"gpus": [], "adapters": [{"name": "AMD Radeon RX 7900 XTX"}]}
    token = _as("owner")
    try:
        with pytest.raises(ModelInstallError, match="Voice output cannot run on this computer: Needs an NVIDIA GPU"):
            model_packs.check_submission("models.install", {"bundle_id": "voice-output", "accept_terms": True})
    finally:
        pop_tenant(token)
    assert desktop.recorded == []  # nothing was accepted either


def test_the_disk_check_counts_only_what_is_still_to_download(desktop) -> None:
    desktop.facts = {**desktop.facts, "disk": {"free_bytes": 10}}
    token = _as("owner")
    try:
        with pytest.raises(ModelInstallError, match="Not enough disk space"):
            model_packs.check_submission("models.install", {"bundle_id": "voice-output", "accept_terms": True})
        desktop.models.have.add("tts-model")  # an update of the runtime only: the model is on disk already
        model_packs.check_submission("models.install", {"bundle_id": "voice-output", "accept_terms": True})
    finally:
        pop_tenant(token)


def test_a_model_without_a_desktop_runtime_is_refused(desktop) -> None:
    token = _as("owner")
    try:
        with pytest.raises(ModelInstallError, match="not available in the desktop app"):
            model_packs.check_submission("models.install", {"model_id": "unbundled", "accept_terms": True})
    finally:
        pop_tenant(token)


def _job(job_type: str, **payload: Any) -> Any:
    """A job as the owner submitted it: the submission policy authorized every runtime it plans."""
    payload.setdefault(model_packs.AUTHORIZED_RUNTIMES, list(CATALOG.runtimes))
    return SimpleNamespace(id="job-1", type=job_type, input_payload=payload)


def test_an_admins_job_never_installs_a_runtime_that_went_missing_after_submission(desktop) -> None:
    """Submitted while the runtime was current; by the time it runs, an app update changed its lock."""
    desktop.accepted.add(("tts-model", REVISION))
    desktop.runtimes.have.update({"torch-win"})  # tts-win is no longer current
    with pytest.raises(ModelInstallError, match="only the workspace owner can install it"):
        model_packs.execute(_job("models.install", bundle_id="voice-output", authorized_runtimes=[]))
    assert desktop.runtimes.calls == [] and desktop.models.calls == []


def test_an_admins_bundle_removal_keeps_the_runtimes(desktop) -> None:
    desktop.runtimes.have.update({"torch-win", "tts-win"})
    desktop.models.have.add("tts-model")
    model_packs.execute(_job("models.remove", bundle_id="voice-output", authorized_runtimes=[]))
    assert desktop.models.calls == ["remove tts-model"] and desktop.runtimes.calls == []


def test_the_submission_policy_replaces_a_client_supplied_authorization(desktop, monkeypatch) -> None:
    from app.jobs.models import CreateJobRequest
    from app.platform.voice.feature import voice_submission_defaults

    desktop.runtimes.have.update({"torch-win", "tts-win"})
    request = CreateJobRequest.model_validate({"module": "voice", "type": "models.install", "resource_class": "cpu",
        "input_payload": {"bundle_id": "voice-output", "accept_terms": True,
                          "authorized_runtimes": ["torch-win", "tts-win", "stt-win"]}})
    token = _as("admin")
    try:
        stored = voice_submission_defaults(request)
    finally:
        pop_tenant(token)
    assert stored.input_payload["authorized_runtimes"] == []
    token = _as("owner")
    try:
        stored = voice_submission_defaults(request)
    finally:
        pop_tenant(token)
    assert stored.input_payload["authorized_runtimes"] == ["torch-win", "tts-win"]


def test_a_bundle_installs_bases_first_then_runtimes_then_models(desktop) -> None:
    desktop.accepted.add(("tts-model", REVISION))
    result = model_packs.execute(_job("models.install", bundle_id="voice-output"))
    assert desktop.runtimes.calls == ["install torch-win", "install tts-win"]
    assert desktop.models.calls == ["install tts-model"]
    assert result["content"] == "Installed GPU runtime, Voice output runtime, TTS"


def test_a_download_that_broke_off_fails_the_attempt_retryably(desktop, monkeypatch) -> None:
    from app.platform.voice.jobs import _failure_code

    desktop.accepted.add(("tts-model", REVISION))

    def broken(runtime_id: str, **_: Any) -> dict:
        raise packs.PackDownloadError("download failed (503), try again later")

    monkeypatch.setattr(desktop.runtimes, "install", broken)
    with pytest.raises(packs.PackDownloadError) as failure:
        model_packs.execute(_job("models.install", bundle_id="voice-output"))
    assert _failure_code(failure.value)[1] is True


def test_the_job_refuses_a_model_whose_licence_was_not_recorded(desktop) -> None:
    with pytest.raises(ModelInstallError, match="has not been accepted for revision"):
        model_packs.execute(_job("models.install", bundle_id="voice-output"))
    assert desktop.runtimes.calls == [] and desktop.models.calls == []


def test_removing_a_bundle_keeps_the_torch_layer_another_bundle_uses(desktop) -> None:
    desktop.runtimes.have.update({"torch-win", "tts-win", "stt-win"})
    desktop.models.have.update({"tts-model", "stt-model", "eou-model"})
    model_packs.execute(_job("models.remove", bundle_id="voice-output"))
    assert desktop.models.calls == ["remove tts-model"]
    assert desktop.runtimes.calls == ["remove tts-win"]
    assert "torch-win" in desktop.runtimes.have


def test_removing_the_last_bundle_removes_the_torch_layer_too(desktop) -> None:
    desktop.runtimes.have.update({"torch-win", "tts-win"})
    desktop.models.have.add("tts-model")
    assert model_packs.runtimes_removed_with_bundle("voice-output", ["torch-win", "tts-win"]) == ["tts-win", "torch-win"]
    model_packs.execute(_job("models.remove", bundle_id="voice-output"))
    assert desktop.runtimes.calls == ["remove tts-win", "remove torch-win"]


def test_a_runtime_an_installed_bundle_needs_cannot_be_removed_directly(desktop) -> None:
    desktop.runtimes.have.update({"torch-win", "tts-win"})
    desktop.models.have.add("tts-model")
    with pytest.raises(ModelInstallError, match="needed by Voice output"):
        model_packs.execute(_job("models.remove", runtime_id="tts-win"))


def test_removing_a_bundle_that_takes_its_runtime_needs_the_owner(desktop) -> None:
    desktop.runtimes.have.update({"torch-win", "tts-win", "stt-win"})
    desktop.models.have.update({"tts-model", "stt-model", "eou-model"})
    token = _as("admin")
    try:
        # Voice output's overlay goes with it (nothing else runs on it), so only the owner may remove it.
        with pytest.raises(TenantAccessDenied, match="remove Voice output runtime"):
            model_packs.check_submission("models.remove", {"bundle_id": "voice-output"})
    finally:
        pop_tenant(token)


def test_the_routes_declare_their_permissions() -> None:
    from fastapi import APIRouter

    router = APIRouter()
    model_pack_routes.register_model_pack_routes(router, None)
    permissions = {(next(iter(route.methods)), route.path): declared_permission(route) for route in router.routes}
    assert permissions[("GET", "/api/model-packs")] == "settings:read"
    assert permissions[("POST", "/api/model-packs/install")] == "models:admin"
    assert permissions[("POST", "/api/model-packs/remove")] == "models:admin"


def test_the_install_route_returns_the_refusal_reason(desktop, monkeypatch) -> None:
    from app.platform.voice import job_submission

    def refuse(request: dict, **_: Any) -> Any:
        raise TenantAccessDenied("only the workspace owner can install GPU runtime; ask them to do it")

    monkeypatch.setattr(job_submission, "submit_job", refuse)
    with pytest.raises(HTTPException) as refused:
        model_pack_routes._submit("models.install", model_pack_routes.PackTarget(bundle_id="voice-output"))
    assert refused.value.status_code == 403 and "only the workspace owner" in refused.value.detail

    def needs_terms(request: dict, **_: Any) -> Any:
        raise ModelInstallError("accept the licences first: TTS (Apache-2.0)")

    monkeypatch.setattr(job_submission, "submit_job", needs_terms)
    with pytest.raises(HTTPException) as refused:
        model_pack_routes._submit("models.install", model_pack_routes.PackTarget(bundle_id="voice-output"))
    assert refused.value.status_code == 409


def test_a_target_names_exactly_one_thing() -> None:
    with pytest.raises(ValueError):
        model_pack_routes.PackTarget(bundle_id="a", model_id="b")
    with pytest.raises(ValueError):
        model_pack_routes.PackTarget()


def test_voice_studio_outside_the_desktop_records_and_checks_acceptance(monkeypatch) -> None:
    from app.jobs.models import CreateJobRequest, ResourceClass
    from app.platform.voice import model_install
    from app.platform.voice.feature import voice_submission_defaults
    from app.platform.voice.model_catalog import speech_model

    monkeypatch.delenv("OMNIX_PACKS_DIR", raising=False)
    accepted: set[tuple[str, str]] = set()
    monkeypatch.setattr(licence_acceptances, "available", lambda: True)
    monkeypatch.setattr(licence_acceptances, "record",
                        lambda entries: accepted.update((entry.id, entry.revision) for entry in entries))
    monkeypatch.setattr(licence_acceptances, "accepted", lambda model_id, revision, licence_id: (model_id, revision) in accepted)
    model = speech_model("qwen3-tts-1.7b-voicedesign")
    job = SimpleNamespace(id="job-1", type="models.install", input_payload={"model_id": model.id})
    with pytest.raises(ModelInstallError, match="has not been accepted"):
        model_install.execute_model_job(job)
    token = _as("admin")
    try:
        voice_submission_defaults(CreateJobRequest(module="voice", type="models.install", resource_class=ResourceClass.CPU,
                                                   input_payload={"model_id": model.id, "accept_terms": True}))
    finally:
        pop_tenant(token)
    assert (model.id, model.revision) in accepted
    monkeypatch.setattr(model_install, "install_model", lambda model_id, accept_terms: {
        "label": model.label, "status": "installed", "installed_revision": model.revision, "disk_bytes": 1})
    assert model_install.execute_model_job(job)["content"] == f"Installed {model.label}"


def test_bundles_and_runtimes_are_desktop_only(monkeypatch) -> None:
    from app.platform.voice import model_install

    monkeypatch.delenv("OMNIX_PACKS_DIR", raising=False)
    with pytest.raises(ModelInstallError, match="installed by the desktop app"):
        model_install.execute_model_job(SimpleNamespace(id="j", type="models.install", input_payload={"bundle_id": "x"}))
