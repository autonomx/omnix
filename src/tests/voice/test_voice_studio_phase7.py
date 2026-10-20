"""Voice Studio Phase 7 without PostgreSQL: recipes, watch-folder paths, MCP, the client facade's wiring."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi import Request

# --- recipes ---------------------------------------------------------------------------------------


def test_recipe_steps_chain_what_each_step_makes() -> None:
    from app.platform.voice.automation import validate_steps

    steps = validate_steps([{"tool": "isolate", "settings": {"model": "demucs"}}, {"tool": "enhance"},
                            {"tool": "transcribe", "settings": {"speakers": 2}},
                            {"tool": "subtitles", "settings": {"formats": ["srt"]}}])
    assert [step["tool"] for step in steps] == ["isolate", "enhance", "transcribe", "subtitles"]
    assert steps[1]["settings"] == {}


@pytest.mark.parametrize(("steps", "message"), [
    ([], "one to twelve"),
    ([{"tool": "subtitles"}], "subtitles takes transcript"),
    ([{"tool": "transcribe"}, {"tool": "isolate"}], "isolate takes audio"),
    ([{"tool": "export"}, {"tool": "enhance"}], "makes nothing"),
    ([{"tool": "shell"}], "the tool must be one of"),
    ([{"tool": "isolate", "settings": {"model": "spleeter"}}], "roformer or demucs"),
    ([{"tool": "export", "settings": {"format": "exe"}}], "export formats"),
    ([{"tool": "transcribe", "settings": {"speakers": 40}}], "speakers"),
])
def test_recipe_steps_are_refused_when_they_cannot_run(steps: list[Any], message: str) -> None:
    from app.platform.voice.automation import RecipeError, validate_steps

    with pytest.raises(RecipeError, match=message):
        validate_steps(steps)


def test_each_step_submits_its_own_job() -> None:
    from app.platform.voice.automation import job_request

    transcribe = job_request({"tool": "transcribe", "settings": {"speakers": 2, "diarize": False}}, "audio:a",
                             item_id="vbitem:1")
    assert transcribe["type"] == "stt.transcribe" and transcribe["resource_class"] == "gpu:stt"
    assert transcribe["input_payload"] == {"asset_id": "audio:a", "batch_item_id": "vbitem:1", "timed": True,
                                           "diarize": False, "speakers": 2, "language": "", "save_transcript": True}
    subtitles = job_request({"tool": "subtitles", "settings": {"formats": ["vtt", "exe"]}}, "transcript:a",
                            item_id="vbitem:1")
    assert subtitles["type"] == "voice.subtitles" and subtitles["input_payload"]["formats"] == ["vtt"]


def test_the_step_after_isolation_works_on_the_vocal_stem() -> None:
    from types import SimpleNamespace

    from app.platform.voice.automation import _outputs_of

    job = SimpleNamespace(output_refs=[{"type": "audio", "kind": "stem_background", "asset_id": "audio:bed"},
                                       {"type": "audio", "kind": "stem_vocals", "asset_id": "audio:voice"}])
    outputs, next_asset = _outputs_of(job, {"tool": "isolate"})
    assert next_asset == "audio:voice"
    assert [output["kind"] for output in outputs] == ["stem_background", "stem_vocals"]
    assert _outputs_of(SimpleNamespace(output_refs=[{"type": "export"}]), {"tool": "export"})[1] == ""


def test_every_recipe_job_is_a_voice_job_type() -> None:
    from app.platform.voice.automation import TOOLS
    from app.platform.voice.feature import FEATURE

    registered = {spec.type: spec.resource_class.value for spec in FEATURE.job_handlers}
    for tool, spec in TOOLS.items():
        assert spec["job"] in registered, tool
        assert registered[spec["job"]] == spec["resource"], tool


# --- watch folders -------------------------------------------------------------------------------


def test_watch_folders_refuse_unc_relative_and_nested_paths(tmp_path: Path) -> None:
    from app.platform.voice.watch_folders import WatchFolder, WatchFolderRefused, safe_folder

    with pytest.raises(WatchFolderRefused, match="UNC"):
        safe_folder(r"\\server\share\in")
    with pytest.raises(WatchFolderRefused, match="UNC"):
        safe_folder("//server/share/in")
    with pytest.raises(WatchFolderRefused, match="absolute"):
        safe_folder("relative/in")
    (tmp_path / "in" / "out").mkdir(parents=True)
    entry = {"id": "talks", "path": str(tmp_path / "in"), "output": str(tmp_path / "in" / "out"),
             "recipe_id": "vrecipe:1", "workspace_id": "workspace:1", "owner_user_id": "user:1"}
    with pytest.raises(WatchFolderRefused, match="contain each other"):
        WatchFolder.from_entry(entry)
    with pytest.raises(WatchFolderRefused, match="ids are"):
        WatchFolder.from_entry({**entry, "id": "../talks", "output": str(tmp_path / "out")})


@pytest.mark.skipif(os.name != "nt", reason="junctions are a Windows feature")
def test_watch_folders_refuse_a_junction_anywhere_on_the_path(tmp_path: Path) -> None:
    from app.platform.voice.watch_folders import WatchFolderRefused, safe_folder

    (tmp_path / "real" / "in").mkdir(parents=True)
    link = tmp_path / "linked"
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(tmp_path / "real")], check=True, capture_output=True)
    try:
        with pytest.raises(WatchFolderRefused, match="junction or symlink"):
            safe_folder(str(link / "in"))
        assert safe_folder(str(tmp_path / "real" / "in")) == (tmp_path / "real" / "in").resolve()
    finally:
        os.rmdir(link)  # removes the junction, not its target


def test_watch_folder_configuration_leaves_out_refused_entries(tmp_path: Path) -> None:
    import json

    from app.platform.voice.watch_folders import configured_folders

    (tmp_path / "in").mkdir()
    (tmp_path / "out").mkdir()
    good = {"id": "talks", "path": str(tmp_path / "in"), "output": str(tmp_path / "out"), "recipe_id": "vrecipe:1",
            "workspace_id": "workspace:1", "owner_user_id": "user:1"}
    folders = configured_folders(json.dumps([good, {**good, "id": "share", "path": r"\\nas\in"}]))
    assert [folder.id for folder in folders] == ["talks"]


def test_watch_delivery_writes_only_under_the_output_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from app.platform.voice import watch_folders
    from app.platform.voice.watch_folders import WatchFolder, WatchFolders

    (tmp_path / "in").mkdir()
    (tmp_path / "out").mkdir()
    stem = tmp_path / "stem.wav"
    stem.write_bytes(b"RIFF-vocals")
    folder = WatchFolder("talks", (tmp_path / "in").resolve(), (tmp_path / "out").resolve(), "vrecipe:1", "w", "u")
    store = SimpleNamespace(get_asset=lambda asset_id: SimpleNamespace(storage_path=str(stem)) if asset_id else None)
    monkeypatch.setattr("app.assets.default_asset_store", lambda: store)
    monkeypatch.setattr("app.assets.content.open_asset", lambda asset: stem.open("rb"))
    watcher = WatchFolders([folder])
    outputs = [{"tool": "isolate", "kind": "stem_vocals", "asset_id": "audio:v"}]
    watcher.deliver({"watch_folder": "talks"}, {"output_name": "day1/talk.wav", "outputs": outputs})
    assert (tmp_path / "out" / "day1" / "talk.vocals.wav").read_bytes() == b"RIFF-vocals"
    watcher.deliver({"watch_folder": "talks"}, {"output_name": "../escape.wav", "outputs": outputs})
    assert not (tmp_path / "escape.vocals.wav").exists()
    assert watch_folders.inside(folder.output, tmp_path / "out" / "day1")


# --- MCP and the client facade -------------------------------------------------------------------


class _Tool:
    def __init__(self, name: str, capability: str) -> None:
        self.name, self.capability, self.description = name, capability, f"{name} tool"
        self.input_schema = {"type": "object", "properties": {}, "required": []}
        self.calls: list[dict[str, Any]] = []

    def call(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(arguments)
        return {"ok": True, "tool": self.name}


@pytest.fixture
def tools(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    from app.platform.voice import client_api

    registered = {"speak": _Tool("speak", "voice.speak"), "design_voice": _Tool("design_voice", "voice.design"),
                  "job_status": _Tool("job_status", "")}
    audits: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(client_api, "registered_tools", lambda: registered)
    monkeypatch.setattr("app.security.audit.record", lambda action, **values: audits.append((action, values)))
    return {"tools": registered, "audits": audits}


def test_mcp_lists_only_the_tools_a_credential_may_call(tools: dict[str, Any]) -> None:
    from app.platform.voice.automation_routes import MCP_PROTOCOL_VERSION, handle_mcp

    credential = {"id": "vclient:1", "capabilities": frozenset({"voice.speak"})}
    started = handle_mcp(credential, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert started is not None and started["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION
    listed = handle_mcp(credential, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert listed is not None and [tool["name"] for tool in listed["result"]["tools"]] == ["speak", "job_status"]
    assert handle_mcp(credential, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    unknown = handle_mcp(credential, {"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
    assert unknown is not None and unknown["error"]["code"] == -32601


def test_mcp_refuses_a_tool_without_its_grant_and_audits_it(tools: dict[str, Any]) -> None:
    from app.platform.voice.automation_routes import handle_mcp

    credential = {"id": "vclient:1", "capabilities": frozenset({"voice.speak"})}
    refused = handle_mcp(credential, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                      "params": {"name": "design_voice", "arguments": {"description": "warm"}}})
    assert refused is not None and refused["result"]["isError"] is True
    assert "voice.design" in refused["result"]["content"][0]["text"]
    assert tools["tools"]["design_voice"].calls == []
    assert tools["audits"] == [("voice.client.call", {"target_type": "voice_tool", "target_id": "design_voice",
                                                       "outcome": "denied",
                                                       "details": {"client_id": "vclient:1",
                                                                   "capability": "voice.design"}})]
    called = handle_mcp(credential, {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                                     "params": {"name": "speak", "arguments": {"text": "hi"}}})
    assert called is not None and called["result"]["structuredContent"] == {"ok": True, "tool": "speak"}
    assert tools["audits"][-1][1].get("outcome", "success") == "success"


def test_the_client_credential_sets_the_tenant_the_endpoint_sees(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dependency is async so the tenant it sets reaches the (threaded) endpoint."""
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from app.platform.voice import automation_routes, client_api
    from app.runtime.tenant_context import TenantContext, current_tenant

    context = TenantContext(user_id="user:owner", workspace_id="workspace:client", membership_id="m",
                            roles=frozenset({"member"}))
    monkeypatch.setattr(client_api, "authenticate",
                        lambda token: ({"id": "vclient:1", "capabilities": frozenset()}, context))
    app = FastAPI()

    @app.get("/probe")
    def probe(credential: dict[str, Any] = Depends(automation_routes._client)) -> dict[str, str]:  # noqa: B008
        return {"workspace": current_tenant().workspace_id, "client": credential["id"]}

    client = TestClient(app)
    assert client.get("/probe", headers={"Authorization": "Bearer omv_x"}).json() == {
        "workspace": "workspace:client", "client": "vclient:1"}
    missing = client.get("/probe")
    assert missing.status_code == 401 and missing.headers["www-authenticate"].startswith("Bearer")

    def refuse(_token: str) -> Any:
        raise client_api.ClientCredentialError("revoked")

    monkeypatch.setattr(client_api, "authenticate", refuse)
    assert client.get("/probe", headers={"Authorization": "Bearer omv_x"}).json() == {
        "detail": "voice_client_token_refused"}


def test_voice_and_dubbing_register_the_client_tools() -> None:
    from app.apps.dubbing.client_tool import DubStatusTool
    from app.apps.dubbing.feature import FEATURE as DUBBING
    from app.platform.voice.client_api import CAPABILITIES, VOICE_TOOL_NAMES, voice_tools
    from app.platform.voice.client_tools import VOICE_CLIENT_TOOLS
    from app.platform.voice.feature import FEATURE as VOICE

    contributed = [spec.factory(None) for spec in VOICE.contributions if spec.port is VOICE_CLIENT_TOOLS]
    assert tuple(tool.name for tool in contributed) == VOICE_TOOL_NAMES == tuple(tool.name for tool in voice_tools())
    assert [spec.factory(None).name for spec in DUBBING.contributions if spec.port is VOICE_CLIENT_TOOLS] == [
        "dub_status"]
    for tool in [*contributed, DubStatusTool()]:
        assert not tool.capability or tool.capability in CAPABILITIES, tool.name
        assert tool.input_schema["type"] == "object"


def test_the_client_facade_is_public_only_where_a_credential_is_required(tmp_path: Path) -> None:
    """Every ``/api/voice/v1`` and ``/mcp/voice`` route is a declared public path and refuses without a token."""
    from fastapi.testclient import TestClient
    from tests.support.in_memory_jobs import InMemoryJobStore

    from app.composition.gateway.main import create_gateway_app
    from app.platform.voice.feature import FEATURE

    app = create_gateway_app(job_store_factory=lambda: InMemoryJobStore(tmp_path / "jobs"))
    client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})
    assert client.get("/api/voice/v1/tools").status_code == 401
    paths = set(app.openapi()["paths"])
    assert {path for path in paths if path.startswith(("/api/voice/v1/", "/mcp/voice"))} == set(FEATURE.public_paths)
    assert set(FEATURE.public_paths) <= set(app.state.public_route_paths)
    session_routes = {path for path in paths if path.startswith(
        ("/api/voice/recipes", "/api/voice/batches", "/api/voice/clients", "/api/voice/dictate"))}
    assert len(session_routes) == 9 and not session_routes & set(app.state.public_route_paths)
    assert client.post("/mcp/voice", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 401
    assert client.get("/api/voice/v1/voices", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_dictation_warm_up_reports_a_provider_without_a_batch_engine(tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    from tests.support.in_memory_jobs import InMemoryJobStore

    from app.composition.gateway.main import create_gateway_app

    monkeypatch.setattr("app.providers.service.get_stt_provider", lambda: object())
    app = create_gateway_app(job_store_factory=lambda: InMemoryJobStore(tmp_path / "jobs"))
    client = TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "test"})
    answer = client.post("/api/voice/dictate/warm")
    assert answer.status_code == 200 and answer.json()["ready"] is False
    assert client.post("/api/voice/dictate", files={"file": ("a.webm", b"", "audio/webm")}).status_code == 422


def test_facade_routes_authenticate_and_bound_the_body_before_reading_it(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import APIRouter, Depends, FastAPI
    from fastapi.testclient import TestClient

    from app.platform.voice import automation_routes, client_api
    from app.runtime.tenant_context import TenantContext, current_tenant

    context = TenantContext(user_id="user:owner", workspace_id="workspace:client", membership_id="m",
                            roles=frozenset({"member"}))
    calls: list[str] = []

    def authenticate(token: str) -> Any:
        calls.append(token)
        if token != "omv_good":
            raise client_api.ClientCredentialError("unknown token")
        return {"id": "vclient:1", "capabilities": frozenset()}, context

    monkeypatch.setattr(client_api, "authenticate", authenticate)
    read: list[int] = []
    facade = APIRouter(route_class=automation_routes.CredentialFirstRoute)

    @facade.post("/api/voice/v1/echo")
    async def echo(request: Request, credential: dict[str, Any] = Depends(automation_routes._client)) -> dict[str, Any]:  # noqa: B008
        read.append(len(await request.body()))
        return {"workspace": current_tenant().workspace_id, "client": credential["id"]}

    app = FastAPI()
    app.include_router(facade)
    client = TestClient(app)
    anonymous = client.post("/api/voice/v1/echo", content=b"x" * 4096)
    assert anonymous.status_code == 401 and read == []   # refused before the body was read
    too_large = client.post("/api/voice/v1/echo", headers={"Authorization": "Bearer omv_good"},
                            content=b"x" * (automation_routes._FACADE_JSON_BYTES + 1))
    assert too_large.status_code == 413 and read == []
    ok = client.post("/api/voice/v1/echo", headers={"Authorization": "Bearer omv_good"}, json={"a": 1})
    assert ok.json() == {"workspace": "workspace:client", "client": "vclient:1"} and read == [7]
    assert calls.count("omv_good") == 2   # once per request: the dependency reuses the route's check


def test_a_client_sees_only_the_jobs_it_submitted(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from app.platform.voice import client_api

    jobs: dict[str, Any] = {}

    class _Store:
        def create_job(self, request: Any) -> Any:
            job = SimpleNamespace(id=f"job:{len(jobs) + 1}", type=request.type, status="queued", error=None,
                                  output_refs=[], compat=dict(request.compat))
            jobs[job.id] = job
            return job

        def get_job(self, job_id: str) -> Any:
            return jobs.get(job_id)

    monkeypatch.setattr("app.jobs.store.default_job_store", lambda: _Store())
    monkeypatch.setattr("app.security.audit.record", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(client_api, "registered_tools", lambda: {tool.name: tool for tool in client_api.voice_tools()})
    owner = {"id": "vclient:a", "capabilities": frozenset({"voice.isolate"})}
    other = {"id": "vclient:b", "capabilities": frozenset({"voice.list_voices"})}
    submitted = client_api.call_tool(owner, "isolate", {"asset_id": "audio:talk"})
    assert jobs[submitted["job_id"]].compat["voice_client_id"] == "vclient:a"
    assert client_api.call_tool(owner, "job_status", {"job_id": submitted["job_id"]})["status"] == "queued"
    with pytest.raises(LookupError):
        client_api.call_tool(other, "job_status", {"job_id": submitted["job_id"]})
    jobs["job:person"] = SimpleNamespace(id="job:person", type="stt.transcribe", status="completed", error=None,
                                         output_refs=[{"content": "private"}], compat={})
    with pytest.raises(LookupError):   # a person's job (no client tag) is never a client's to read
        client_api.call_tool(owner, "job_status", {"job_id": "job:person"})


@pytest.mark.parametrize(("arguments", "message"), [
    ({}, "missing asset_id"),
    ({"asset_id": "audio:a", "speakers": 40}, "speakers is 0 to 8"),
    ({"asset_id": "audio:a", "speakers": True}, "whole number"),
    ({"asset_id": "audio:a", "diarize": "yes"}, "true or false"),
    ({"asset_id": "audio:a", "path": "C:/secret.wav"}, "unknown argument path"),
    ("asset", "JSON object"),
])
def test_tool_arguments_are_checked_against_their_schema(arguments: Any, message: str) -> None:
    from app.platform.voice.client_api import check_arguments, voice_tool

    with pytest.raises(ValueError, match=message):
        check_arguments(voice_tool("transcribe").input_schema, arguments)
    assert check_arguments(voice_tool("isolate").input_schema, {"asset_id": "a", "model": "demucs"})
    with pytest.raises(ValueError, match="one of roformer, demucs"):
        check_arguments(voice_tool("isolate").input_schema, {"asset_id": "a", "model": "spleeter"})
