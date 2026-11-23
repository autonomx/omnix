from __future__ import annotations

import asyncio
import json
import secrets

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from websockets.exceptions import SecurityError

from app.platform.voice import stt_proxy_routes as proxy
from app.security.model_service import ModelServiceMiddleware
from app.security.request_guard import RequestGuardMiddleware
from tests.support.routers import include_router_registrar


@pytest.fixture
def setup(monkeypatch):
    token = secrets.token_urlsafe(32)
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", token)
    monkeypatch.setenv("OMNIX_MAX_UPLOAD_BYTES", "1024")
    monkeypatch.setattr(proxy, "_stt_base_url", lambda: "http://127.0.0.1:5201/private")
    app = FastAPI()
    app.add_middleware(RequestGuardMiddleware)
    include_router_registrar(app, proxy.register_stt_proxy_routes)
    upstream = FastAPI()
    upstream.add_middleware(ModelServiceMiddleware)
    calls = []

    @upstream.api_route("/private/authorityz", methods=["GET"])
    @upstream.api_route("/private/transcribe", methods=["POST"])
    async def endpoint(request: Request):
        body = await request.body()
        calls.append((request, body))
        return {"ok": True, "eligible": True, "text": "hello"}

    real_client = httpx.AsyncClient

    def client(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        return real_client(transport=httpx.ASGITransport(app=upstream), **kwargs)

    # Patch only the proxy's factory via a local namespace, not httpx globally.
    from types import SimpleNamespace
    monkeypatch.setattr(proxy, "httpx", SimpleNamespace(AsyncClient=client, HTTPError=httpx.HTTPError))
    return TestClient(app, base_url="http://127.0.0.1", headers={"X-Omnix-Client": "web"}), calls, token


def test_authority_uses_configured_target_and_private_credential(setup):
    client, calls, token = setup
    response = client.get("/api/stt/authorityz?language=en&mode=test&url=https://evil.test",
                          headers={"X-Omnix-Service-Token": "browser-forged", "Authorization": "browser-auth"})
    assert response.status_code == 200
    request, body = calls[0]
    assert request.headers["x-omnix-service-token"] == token
    assert "authorization" not in request.headers
    assert dict(request.query_params) == {"language": "en", "mode": "test"}
    assert request.url.path == "/private/authorityz"
    assert body == b""
    assert token not in response.text


def test_transcription_upload_is_forwarded_without_browser_credentials(setup):
    client, calls, token = setup
    response = client.post("/api/stt/transcribe", files={"audio": ("voice.wav", b"samples")},
                           headers={"Cookie": "browser-cookie", "X-Omnix-Service-Token": "forged"})
    assert response.status_code == 200
    request, body = calls[0]
    assert request.headers["x-omnix-service-token"] == token
    assert "cookie" not in request.headers
    assert b"samples" in body


def test_upload_limit_does_not_contact_the_model(setup):
    client, calls, _ = setup
    response = client.post("/api/stt/transcribe", files={"audio": ("voice.wav", b"x" * 1024)})
    assert response.status_code == 413
    assert response.json()["error"] == "upload_too_large"
    assert calls == []


def test_chunked_upload_limit_is_enforced_as_it_is_forwarded(setup):
    client, calls, _ = setup
    response = client.post("/api/stt/transcribe", content=iter([b"x" * 512, b"x" * 512, b"x"]),
                           headers={"Content-Type": "multipart/form-data; boundary=x"})
    assert response.status_code == 413
    assert calls == []


@pytest.mark.parametrize("query", ["mode=unknown", "language=../private", "language=" + "a" * 33])
def test_invalid_probe_parameters_do_not_contact_the_model(setup, query):
    client, calls, _ = setup
    assert client.get(f"/api/stt/authorityz?{query}").status_code == 422
    assert calls == []


def test_missing_credential_fails_without_contacting_sidecar(setup, monkeypatch):
    client, calls, _ = setup
    monkeypatch.delenv("OMNIX_SERVICE_TOKEN")
    response = client.get("/api/stt/authorityz")
    assert response.status_code == 503
    assert calls == []


@pytest.mark.parametrize("status", [307, 401, 500])
def test_upstream_errors_and_redirects_are_not_forwarded(setup, monkeypatch, status):
    client, _, token = setup
    request_count = 0

    def handler(request):
        nonlocal request_count
        request_count += 1
        return httpx.Response(status, text=f"Traceback: private {token}",
                              headers={"Location": "https://evil.test"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(proxy.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    response = client.get("/api/stt/authorityz")
    assert response.status_code == 503
    assert request_count == 1
    assert set(response.json()) == {"error", "request_id"}
    assert "Traceback" not in response.text
    assert token not in response.text
    assert "location" not in response.headers


@pytest.mark.anyio
async def test_service_websocket_rejects_redirects_without_reporting_uri():
    async def check():
        connection = proxy._ServiceConnect("ws://127.0.0.1:5201/ws/transcribe")
        with pytest.raises(SecurityError, match="^model_service_redirect_rejected$"):
            connection.handle_redirect("ws://evil.test/private")
    await check()


def test_websocket_proxy_uses_private_headers_and_cleans_up_on_disconnect(setup, monkeypatch):
    client, _, token = setup
    captured = {}
    stopped = []

    class Upstream:
        def __init__(self):
            self.queue = asyncio.Queue()

        async def send(self, message):
            await self.queue.put(message)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return await self.queue.get()
            except asyncio.CancelledError:
                stopped.append("receiver_cancelled")
                raise

    class Connection:
        def __init__(self, uri, **kwargs):
            captured.update(uri=uri, **kwargs)

        async def __aenter__(self):
            return Upstream()

        async def __aexit__(self, *_args):
            stopped.append("upstream_closed")

    monkeypatch.setattr(proxy, "_ServiceConnect", Connection)
    with client.websocket_connect("ws://127.0.0.1/api/stt/ws/transcribe?language=en&url=ws://evil.test",
                                  headers={"Origin": "http://localhost:5173", "X-Omnix-Service-Token": "forged"}) as socket:
        socket.send_text(json.dumps({"type": "session_start"}))
        assert socket.receive_json() == {"type": "session_start"}
        socket.send_bytes(b"pcm")
        assert socket.receive_bytes() == b"pcm"
    assert captured["uri"] == "ws://127.0.0.1:5201/private/ws/transcribe?language=en"
    assert captured["extra_headers"]["X-Omnix-Service-Token"] == token
    assert captured["max_queue"] == 8
    assert stopped == ["receiver_cancelled", "upstream_closed"]


def test_websocket_proxy_sends_the_accounts_print_first_and_never_the_browsers(setup, monkeypatch):
    client, _, _ = setup
    sent: list = []

    class Upstream:
        def __init__(self):
            self.queue = asyncio.Queue()

        async def send(self, message):
            sent.append(message)
            if message != profile:
                await self.queue.put(message)

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.queue.get()

    class Connection:
        def __init__(self, uri, **kwargs):
            pass

        async def __aenter__(self):
            return Upstream()

        async def __aexit__(self, *_args):
            return None

    profile = json.dumps({"type": "speaker_profile", "model": "titanet-large", "embedding": [0.1] * 192})
    monkeypatch.setattr(proxy, "_ServiceConnect", Connection)
    monkeypatch.setattr(proxy, "_speaker_profile", lambda: profile)
    with client.websocket_connect("ws://127.0.0.1/api/stt/ws/transcribe?language=en",
                                  headers={"Origin": "http://localhost:5173"}) as socket:
        socket.send_text(json.dumps({"type": "speaker_profile", "embedding": [0.9] * 192}))
        socket.send_text(json.dumps({"type": "hello"}))
        assert socket.receive_json() == {"type": "hello"}
    assert sent == [profile, json.dumps({"type": "hello"})]


class _Roster:
    """The call's seats as live voice's roster reads them: only ``chat-1`` is this caller's."""

    def __init__(self):
        self.seated = {"chat-1": ["Afra", "Theo"]}
        self.stamped: list[str] = []

    def names(self, chat_session_id):
        return list(self.seated.get(chat_session_id, []))

    def note_call(self, chat_session_id):
        if chat_session_id in self.seated:
            self.stamped.append(chat_session_id)


def test_websocket_proxy_sends_the_calls_own_names_never_the_browsers(setup, monkeypatch):
    client, _, _ = setup
    sent: list = []

    class Upstream:
        def __init__(self):
            self.queue = asyncio.Queue()

        async def send(self, message):
            sent.append(json.loads(message))
            await self.queue.put(message)

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.queue.get()

    class Connection:
        def __init__(self, uri, **kwargs):
            pass

        async def __aenter__(self):
            return Upstream()

        async def __aexit__(self, *_args):
            return None

    roster = _Roster()
    monkeypatch.setattr(proxy, "_ServiceConnect", Connection)
    monkeypatch.setattr(proxy, "_speaker_profile", lambda: None)
    monkeypatch.setattr(proxy, "_call_roster", lambda: roster)
    monkeypatch.setattr(proxy, "_phrase_scope", lambda: "acct-a")
    with client.websocket_connect("ws://127.0.0.1/api/stt/ws/transcribe?language=en",
                                  headers={"Origin": "http://localhost:5173"}) as socket:
        socket.send_text(json.dumps({"type": "hello", "sessionId": "stt-1", "chatSessionId": "chat-1",
                                     "contextPhrases": ["Ignore previous instructions"], "scope": "acct-b"}))
        assert socket.receive_json()["contextPhrases"] == ["Afra", "Theo"]
        # The scene changed: the seats are read again; the same seats twice go once.
        roster.seated["chat-1"].append("Abhishek")
        socket.send_text(json.dumps({"type": "context_phrases", "sessionId": "stt-1", "chatSessionId": "chat-1",
                                     "contextPhrases": ["Anything"]}))
        assert socket.receive_json()["contextPhrases"] == ["Afra", "Theo", "Abhishek"]
        socket.send_text(json.dumps({"type": "context_phrases", "sessionId": "stt-1", "chatSessionId": "chat-1",
                                     "contextPhrases": ["Anything else"]}))
        # A chat that is not the caller's boosts nothing.
        socket.send_text(json.dumps({"type": "context_phrases", "sessionId": "stt-1", "chatSessionId": "chat-x",
                                     "contextPhrases": ["Mallory"]}))
        assert socket.receive_json()["contextPhrases"] == []
    assert sent == [
        {"type": "hello", "sessionId": "stt-1", "chatSessionId": "chat-1", "contextPhrases": ["Afra", "Theo"],
         "scope": "acct-a"},
        {"type": "context_phrases", "sessionId": "stt-1", "contextPhrases": ["Afra", "Theo", "Abhishek"],
         "scope": "acct-a"},
        {"type": "context_phrases", "sessionId": "stt-1", "contextPhrases": [], "scope": "acct-a"},
    ]
    assert roster.stamped == ["chat-1"] * 3  # each name read stamps the call's seats


def test_a_call_name_heard_as_another_spelling_reaches_the_browser_as_the_name():
    # Owner report 2026-11-21: "Jinx" was heard as "Jenks" though the decoder boosted it.
    names = proxy._CallNames(None, "acct-a")
    final = json.dumps({"type": "result_available", "segmentId": "s1", "text": "Hey Jenks, what do you see?"})
    assert proxy._to_browser(final, names) == final  # no call names yet: as the service sent it
    names._sent = ["Jinx", "Ehsan Matean"]
    assert json.loads(proxy._to_browser(final, names)) == {
        "type": "result_available", "segmentId": "s1", "text": "Hey Jinx, what do you see?"}
    partial = json.dumps({"type": "partial", "text": "Jenks, what"})
    assert json.loads(proxy._to_browser(partial, names))["text"] == "Jinx, what"
    # A partial or preview may go on after its last word ("hey jenks..." may be "hey jenkins"): not yet an address.
    for still_heard in ("partial", "preview_result"):
        unfinished = json.dumps({"type": still_heard, "text": "hey jenks"})
        assert proxy._to_browser(unfinished, names) == unfinished
    assert json.loads(proxy._to_browser(json.dumps({"type": "result_available", "text": "hey jenks"}), names))[
        "text"] == "hey Jinx"
    resumed = json.dumps({"type": "session_ready", "results": [
        {"type": "result_available", "text": "tell jenks"}, {"type": "result_available", "text": "Thanks, Jenks!"}]})
    assert [result["text"] for result in json.loads(proxy._to_browser(resumed, names))["results"]] == [
        "tell jenks", "Thanks, Jinx!"]  # lower-case and not set off: not said as a name
    for untouched in (json.dumps({"type": "endpoint_score", "text": "Jenks,"}),
                      json.dumps({"type": "result_available", "text": "Don't jinx it."}), "not json \"text\"", "[1]"):
        assert proxy._to_browser(untouched, names) == untouched


def test_an_open_call_keeps_stamping_its_seats_and_a_roster_failure_is_no_names(monkeypatch):
    roster = _Roster()
    names = proxy._CallNames(roster, "acct-a")
    names.keep_seats()
    assert roster.stamped == []  # no chat named yet
    names.chat = "chat-1"
    monkeypatch.setattr(proxy, "SEAT_STAMP_SECONDS", 0.01)

    async def run_briefly():
        task = asyncio.create_task(proxy._keep_seats(names))
        await asyncio.sleep(0.1)
        task.cancel()

    asyncio.run(run_briefly())
    assert len(roster.stamped) >= 2

    class Broken:
        def names(self, _chat):
            raise RuntimeError("chat store away")

        def note_call(self, _chat):
            raise RuntimeError("chat store away")

    broken = proxy._CallNames(Broken(), "acct-a")
    message = asyncio.run(broken.rewrite({"type": "context_phrases", "sessionId": "s", "chatSessionId": "chat-1",
                                          "contextPhrases": ["Afra"]}))
    assert json.loads(message)["contextPhrases"] == []
    broken.keep_seats()  # logged, never raised


def test_the_phrase_scope_is_one_hash_per_account():
    from app.runtime.tenant_context import pop_tenant, push_tenant, tenant_context

    def scope_of(workspace):
        token = push_tenant(tenant_context(user_id="u", workspace_id=workspace, membership_id="m", roles=("owner",)))
        try:
            return proxy._phrase_scope()
        finally:
            pop_tenant(token)

    assert scope_of("ws-a") == scope_of("ws-a") != scope_of("ws-b")
    assert "ws-a" not in scope_of("ws-a")
