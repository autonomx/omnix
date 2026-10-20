"""Inbound voice API clients (Voice Studio Phase 7): credentials, tools, ``/api/voice/v1`` and MCP.

Omnix's ``mcp_policy`` governs MCP servers Omnix calls out to; clients calling
in need their own model:

- A credential is a per-client token bound to a workspace, an owner and a set
  of capabilities (``CAPABILITIES``). Only its SHA-256 is stored; the token is
  shown once. An HMAC over its id, workspace, owner, capabilities and expiry
  (keyed from the secret store, never PostgreSQL) is stored with it and checked
  on use, so a credential altered in the database stops working; so does one
  whose owner is no longer a workspace admin. Credentials expire and can be
  revoked.
- The lookup by hash runs before the workspace is known, in the narrow system
  scope ``voice.client_credentials`` (the 0162 pattern); the request then runs
  in the credential's workspace as its owner.
- Capabilities are a ceiling, not a grant: a tool runs only when the
  credential holds its capability, and every call (refusals too) is audited.

Clients send ``Authorization: Bearer <token>`` and ``X-Omnix-Client: <name>``
(the gateway's request guard asks every unsafe request for one).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import uuid
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any

from .client_tools import VOICE_CLIENT_TOOLS, VoiceClientTool

logger = logging.getLogger(__name__)

# The credential a tool call runs for: jobs it submits are tagged with it, and ``job_status`` serves only those.
_CALLING_CLIENT: ContextVar[str] = ContextVar("omnix_voice_client", default="")

CAPABILITIES = frozenset({"voice.speak", "voice.transcribe", "voice.list_voices", "voice.design", "voice.isolate",
                          "dub.status"})
TOKEN_PREFIX = "omv_"


class ClientCredentialError(PermissionError):
    """The token is unknown, expired, revoked or altered."""


class ClientCapabilityRefused(PermissionError):
    """The credential does not hold the capability the tool needs."""


_KEY_NAME = "voice/client-credential-key"


def _signing_key() -> bytes:
    """The key that signs credential rows, from the secret store (made on first use; never in PostgreSQL)."""
    from app.security.secrets import SecretStoreUnavailable, secret_store

    store = secret_store()
    key = store.get(_KEY_NAME)
    if not key:
        if not store.writable:
            raise SecretStoreUnavailable(
                f"voice API clients need a writable secret store, or the secret {_KEY_NAME} set")
        store.set(_KEY_NAME, secrets.token_hex(32))
        key = store.get(_KEY_NAME)  # another process may have set it first: use the stored one
    if not key or len(key) < 32:
        raise SecretStoreUnavailable(f"the secret {_KEY_NAME} is missing or too short")
    return key.encode("utf-8")


def capabilities_digest(*, credential_id: str, workspace_id: str, owner_user_id: str,
                        capabilities: list[str] | frozenset[str], expires_at: datetime | None) -> str:
    """An HMAC over everything the credential grants: altering any of it in the database voids it."""
    document = json.dumps({
        "id": credential_id, "workspace": workspace_id, "owner": owner_user_id,
        "capabilities": sorted(set(capabilities)),
        "expires": int(expires_at.timestamp()) if expires_at is not None else None,
    }, sort_keys=True, separators=(",", ":"))
    return hmac.new(_signing_key(), document.encode("utf-8"), hashlib.sha256).hexdigest()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _work() -> Any:
    from app.persistence.database import default_database
    from app.persistence.unit_of_work import unit_of_work

    return unit_of_work(default_database())


_CREDENTIAL_COLUMNS = ("id", "name", "owner_user_id", "capabilities", "expires_at", "revoked_at", "last_used_at",
                       "created_at")


def _credential(row: Any) -> dict[str, Any]:
    value = dict(zip(_CREDENTIAL_COLUMNS, row))
    for key in ("expires_at", "revoked_at", "last_used_at", "created_at"):
        if value[key] is not None:
            value[key] = value[key].isoformat()
    value["capabilities"] = sorted(value["capabilities"] or [])
    return value


def issue_credential(*, name: str, capabilities: list[str], expires_in_days: int | None = 90) -> dict[str, Any]:
    """A new client credential in the current workspace; the token is in the result and nowhere else."""
    from app.runtime.tenant_context import current_tenant
    from app.security import audit

    context = current_tenant()
    context.require_role("owner", "admin")
    wanted = sorted(set(capabilities))
    unknown = [capability for capability in wanted if capability not in CAPABILITIES]
    if not wanted or unknown:
        raise ValueError(f"capabilities are some of {', '.join(sorted(CAPABILITIES))}")
    name = " ".join(str(name or "").split())[:120]
    if not name:
        raise ValueError("name the client")
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    credential_id = f"vclient:{uuid.uuid4().hex}"
    expires = datetime.now(timezone.utc) + timedelta(days=expires_in_days) if expires_in_days else None
    digest = capabilities_digest(credential_id=credential_id, workspace_id=context.workspace_id,
                                 owner_user_id=context.user_id, capabilities=wanted, expires_at=expires)
    with _work() as work:
        work.connection.execute(
            """INSERT INTO omnix_voice_client_credentials
                   (id, workspace_id, owner_user_id, name, token_hash, capabilities, caps_digest, expires_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (credential_id, context.workspace_id, context.user_id, name, token_hash(token), wanted, digest, expires))
        work.commit()
    audit.record("voice.client.issue", target_type="voice_client", target_id=credential_id,
                 details={"capabilities": wanted, "expires_in_days": expires_in_days})
    return {**next(item for item in list_credentials() if item["id"] == credential_id), "token": token}


def list_credentials() -> list[dict[str, Any]]:
    from app.runtime.tenant_context import current_tenant

    context = current_tenant()
    context.require_role("owner", "admin")
    with _work() as work:
        rows = work.connection.execute(
            f"SELECT {', '.join(_CREDENTIAL_COLUMNS)} FROM omnix_voice_client_credentials "
            "WHERE workspace_id = %s ORDER BY created_at DESC LIMIT 200", (context.workspace_id,)).fetchall()
        work.rollback()
    return [_credential(row) for row in rows]


def revoke_credential(credential_id: str) -> bool:
    from app.runtime.tenant_context import current_tenant
    from app.security import audit

    context = current_tenant()
    context.require_role("owner", "admin")
    with _work() as work:
        changed = work.connection.execute(
            """UPDATE omnix_voice_client_credentials SET revoked_at = clock_timestamp()
                WHERE workspace_id = %s AND id = %s AND revoked_at IS NULL""",
            (context.workspace_id, credential_id)).rowcount
        work.commit()
    if changed:
        audit.record("voice.client.revoke", target_type="voice_client", target_id=credential_id)
    return bool(changed)


def authenticate(token: str) -> tuple[dict[str, Any], Any]:
    """The credential a bearer token names, and the tenant it acts as; ``ClientCredentialError`` otherwise.

    A known credential that is refused (revoked, expired, altered, its owner
    gone) is audited in its own workspace; an unknown token has no workspace to
    audit in and is only logged.
    """
    from app.persistence.identity_service import PostgresIdentityRepository
    from app.persistence.tenant_scope import system_scope
    from app.security import audit

    if not token.startswith(TOKEN_PREFIX):
        raise ClientCredentialError("unknown token")
    refusal = ""
    with system_scope("voice.client_credentials"), _work() as work:
        row = work.connection.execute(
            """SELECT id, workspace_id, owner_user_id, capabilities, caps_digest,
                      revoked_at IS NOT NULL, expires_at IS NOT NULL AND expires_at <= clock_timestamp(), expires_at
                 FROM omnix_voice_client_credentials WHERE token_hash = %s""",
            (token_hash(token),)).fetchone()
        if row is None:
            work.rollback()
            logger.warning("Voice client: refused an unknown token")
            raise ClientCredentialError("unknown token")
        credential_id, workspace_id, owner, capabilities, digest, revoked, expired, expires_at = row
        context = None
        expected = capabilities_digest(credential_id=credential_id, workspace_id=workspace_id,
                                       owner_user_id=str(owner or ""), capabilities=list(capabilities or []),
                                       expires_at=expires_at)
        if revoked:
            refusal = "revoked"
        elif expired:
            refusal = "expired"
        elif not hmac.compare_digest(expected, str(digest or "")):
            refusal = "altered"
        else:
            try:
                context = PostgresIdentityRepository(work.connection).load_context(user_id=owner,
                                                                                   workspace_id=workspace_id)
            except Exception:
                refusal = "owner is no longer a member"
            else:
                if not context.has_role("owner", "admin"):
                    # Only admins issue credentials; one whose issuer lost that role stops working.
                    refusal, context = "owner is no longer a workspace admin", None
        if refusal:
            work.rollback()
        else:
            work.connection.execute(
                "UPDATE omnix_voice_client_credentials SET last_used_at = clock_timestamp() WHERE id = %s",
                (credential_id,))
            work.commit()
    if refusal:
        audit.record("voice.client.call", target_type="voice_client", target_id=credential_id, outcome="denied",
                     details={"reason": refusal}, actor_user_id=owner, workspace_id=workspace_id)
        raise ClientCredentialError(f"the credential is {refusal}" if refusal in {"revoked", "expired"}
                                    else f"the credential is refused: {refusal}")
    return {"id": credential_id, "workspace_id": workspace_id, "capabilities": frozenset(capabilities or [])}, context


# --- tools -----------------------------------------------------------------------------------------


def _submit(request: dict[str, Any]) -> dict[str, Any]:
    """Create a job as the jobs API would (``job_submission``), in the credential's workspace."""
    from .job_submission import submit_job

    client = _CALLING_CLIENT.get()
    if not client:
        raise RuntimeError("voice client tools submit jobs only inside call_tool")
    job = submit_job({**request, "compat": {**dict(request.get("compat") or {}), "voice_client_id": client}})
    return {"job_id": job.id, "status": str(getattr(job.status, "value", job.status))}


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


class _Tool:
    def __init__(self, name: str, capability: str, description: str, schema: dict[str, Any], run: Any) -> None:
        self.name, self.capability, self.description, self.input_schema, self._run = (
            name, capability, description, schema, run)

    def call(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._run(arguments)


def _speak(arguments: dict[str, Any]) -> dict[str, Any]:
    text = str(arguments.get("text") or "").strip()
    if not text:
        raise ValueError("text is required")
    payload: dict[str, Any] = {"text": text[:20_000], "language": str(arguments.get("language") or "en")}
    if arguments.get("voice"):
        payload["voice_id"] = str(arguments["voice"])  # a ``list_voices`` id (``voice-cloning:<id>``)
    if arguments.get("engine"):
        payload["provider_id"] = str(arguments["engine"])
    return _submit({"module": "voice", "type": "tts.synthesize", "resource_class": "gpu:tts", "priority": 0,
                    "input_payload": payload})


def _transcribe(arguments: dict[str, Any]) -> dict[str, Any]:
    asset_id = str(arguments.get("asset_id") or "")
    return _submit({"module": "stt", "type": "stt.transcribe", "resource_class": "gpu:stt", "priority": 0,
                    "input_ref": {"asset_id": asset_id},
                    "input_payload": {"asset_id": asset_id, "timed": True, "diarize": bool(arguments.get("diarize", True)),
                                      "speakers": int(arguments.get("speakers") or 0),
                                      "language": str(arguments.get("language") or ""), "save_transcript": True}})


def _list_voices(_arguments: dict[str, Any]) -> dict[str, Any]:
    """The library voices the studio lists (``/api/voice-library``); ``voice`` is what ``speak`` takes."""
    from app.assets.canonical_voice_clones import discover_canonical_voice_clone_assets

    voices = []
    for asset in discover_canonical_voice_clone_assets():
        metadata = asset.metadata or {}
        voices.append({"voice": asset.id, "name": str(metadata.get("profile_name") or asset.id),
                       "language": str(metadata.get("language") or ""), "gender": str(metadata.get("gender") or "")})
    return {"voices": voices}


def _design(arguments: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"description": str(arguments.get("description") or ""),
                               "preview_text": str(arguments.get("preview_text") or ""),
                               "language": str(arguments.get("language") or "en")}
    if arguments.get("seeds"):
        payload["seeds"] = [int(seed) for seed in arguments["seeds"]][:3]
    return _submit({"module": "voice", "type": "voice.design", "resource_class": "gpu:tts", "priority": 0,
                    "input_payload": payload})


def _isolate(arguments: dict[str, Any]) -> dict[str, Any]:
    asset_id = str(arguments.get("asset_id") or "")
    return _submit({"module": "voice", "type": "audio.isolate", "resource_class": "gpu:audio", "priority": 0,
                    "input_ref": {"asset_id": asset_id},
                    "input_payload": {"asset_id": asset_id, "model": str(arguments.get("model") or "roformer")}})


def _job_status(arguments: dict[str, Any]) -> dict[str, Any]:
    """A job this client submitted: its status, error and outputs (never another client's or a person's)."""
    from app.jobs.store import default_job_store

    job = default_job_store().get_job(str(arguments.get("job_id") or ""))
    client = _CALLING_CLIENT.get()
    if job is None or not client or (getattr(job, "compat", None) or {}).get("voice_client_id") != client:
        raise LookupError("no such job for this client")
    error = getattr(job, "error", None)
    return {"job_id": job.id, "type": job.type, "status": str(getattr(job.status, "value", job.status)),
            "error": getattr(error, "message", None) if error else None,
            "outputs": [{key: ref[key] for key in ("type", "kind", "asset_id", "title", "audio_url", "content")
                         if key in ref} for ref in (job.output_refs or []) if isinstance(ref, dict)]}


UPLOAD_CAPABILITIES = frozenset({"voice.transcribe", "voice.isolate"})
MAX_CLIENT_AUDIO_BYTES = 500 * 1024 * 1024
_AUDIO_TYPES = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac", ".ogg": "audio/ogg",
                ".opus": "audio/ogg", ".m4a": "audio/mp4", ".webm": "audio/webm", ".aac": "audio/aac"}


def store_client_audio(credential: dict[str, Any], filename: str, stream: Any) -> dict[str, Any]:
    """Store a client's recording as an audio asset in its workspace, for ``transcribe`` or ``isolate``."""
    from pathlib import Path

    from app.assets import AssetRecord, AssetType, default_asset_store
    from app.runtime.paths import resources_data_root
    from app.security import audit

    if not UPLOAD_CAPABILITIES & credential["capabilities"]:
        audit.record("voice.client.call", target_type="voice_tool", target_id="upload_audio", outcome="denied",
                     details={"client_id": credential["id"], "capability": "voice.transcribe|voice.isolate"})
        raise ClientCapabilityRefused("this client may not upload audio (needs voice.transcribe or voice.isolate)")
    suffix = Path(filename).suffix.lower()
    if suffix not in _AUDIO_TYPES:
        raise ValueError(f"audio files are {', '.join(sorted(_AUDIO_TYPES))}")
    asset_id = f"audio:client-{uuid.uuid4().hex}"
    target = resources_data_root() / "voice_studio" / "client_audio" / f"{asset_id.split(':', 1)[1]}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with target.open("wb") as handle:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_CLIENT_AUDIO_BYTES:
                    raise ValueError(f"the recording is too large (over {MAX_CLIENT_AUDIO_BYTES // 1024 ** 2} MB)")
                handle.write(chunk)
        if not size:
            raise ValueError("the recording is empty")
    except ValueError:
        target.unlink(missing_ok=True)
        raise
    title = " ".join(Path(filename).name.split())[:200] or "Client recording"
    record = default_asset_store().upsert_asset(AssetRecord(
        id=asset_id, module="voice", type=AssetType.AUDIO, mime_type=_AUDIO_TYPES[suffix], storage_path=str(target),
        metadata={"title": title, "source": "voice_client", "client_id": credential["id"], "file_name": title},
        created_at=datetime.now(timezone.utc).isoformat(), compat={"contract": "voice_client_audio_v1"},
    ))
    audit.record("voice.client.call", target_type="voice_tool", target_id="upload_audio",
                 details={"client_id": credential["id"], "asset_id": record.id, "bytes": size})
    return {"asset_id": record.id, "title": title, "mime_type": record.mime_type, "size": size}


def voice_tools(_context: Any = None) -> list[VoiceClientTool]:
    """Voice Studio's own client tools (registered through ``VOICE_CLIENT_TOOLS``)."""
    text = {"type": "string"}
    return [
        _Tool("speak", "voice.speak", "Render speech with a library voice (a list_voices id); returns a job to poll.",
              _schema({"text": {**text, "maxLength": 20000}, "voice": text, "language": text, "engine": text},
                      ["text"]), _speak),
        _Tool("transcribe", "voice.transcribe", "Timed, speaker-labelled transcript of a stored recording.",
              _schema({"asset_id": text, "language": text, "diarize": {"type": "boolean"},
                       "speakers": {"type": "integer", "minimum": 0, "maximum": 8}}, ["asset_id"]), _transcribe),
        _Tool("list_voices", "voice.list_voices",
              "The voice library on this Omnix (the voices the studio lists); pass one's id to speak.",
              _schema({}, []), _list_voices),
        _Tool("design_voice", "voice.design", "Design voice candidates from a description; returns a job to poll.",
              _schema({"description": {**text, "maxLength": 600}, "preview_text": text, "language": text,
                       "seeds": {"type": "array", "items": {"type": "integer"}, "maxItems": 3}}, ["description"]),
              _design),
        _Tool("isolate", "voice.isolate", "Separate a recording into vocal and background stems.",
              _schema({"asset_id": text, "model": {"type": "string", "enum": ["roformer", "demucs"]}}, ["asset_id"]),
              _isolate),
        _Tool("job_status", "", "Status and outputs of a job this client submitted.",
              _schema({"job_id": text}, ["job_id"]), _job_status),
    ]


def voice_tool(name: str) -> VoiceClientTool:
    """One of Voice Studio's tools, for its ``ContributionSpec``."""
    return next(tool for tool in voice_tools() if tool.name == name)


VOICE_TOOL_NAMES = ("speak", "transcribe", "list_voices", "design_voice", "isolate", "job_status")


def registered_tools() -> dict[str, VoiceClientTool]:
    """Every tool bound to ``VOICE_CLIENT_TOOLS`` (the first registration of a name wins)."""
    from app.runtime.ports import implementations

    tools: dict[str, VoiceClientTool] = {}
    for tool in implementations(VOICE_CLIENT_TOOLS):
        tools.setdefault(tool.name, tool)
    return tools


def check_arguments(schema: dict[str, Any], arguments: Any) -> dict[str, Any]:
    """Arguments as a tool's ``input_schema`` allows them; ``ValueError`` names the first problem.

    Covers what the tools' schemas use: required and unknown properties, types, string length and
    choices, integer bounds and short integer arrays.
    """
    if not isinstance(arguments, dict):
        raise ValueError("arguments are a JSON object")
    properties: dict[str, Any] = schema.get("properties") or {}
    missing = [key for key in schema.get("required") or [] if key not in arguments]
    if missing:
        raise ValueError(f"missing {', '.join(missing)}")
    unknown = [key for key in arguments if key not in properties]
    if unknown and schema.get("additionalProperties") is False:
        raise ValueError(f"unknown argument {', '.join(sorted(unknown))}")
    for key, value in arguments.items():
        rule = properties.get(key) or {}
        kind = rule.get("type")
        if kind == "string":
            if not isinstance(value, str):
                raise ValueError(f"{key} is a string")
            if "maxLength" in rule and len(value) > int(rule["maxLength"]):
                raise ValueError(f"{key} is at most {rule['maxLength']} characters")
        elif kind == "boolean" and not isinstance(value, bool):
            raise ValueError(f"{key} is true or false")
        elif kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{key} is a whole number")
            if "minimum" in rule and value < rule["minimum"] or "maximum" in rule and value > rule["maximum"]:
                raise ValueError(f"{key} is {rule.get('minimum', '')} to {rule.get('maximum', '')}")
        elif kind == "array":
            if not isinstance(value, list):
                raise ValueError(f"{key} is a list")
            if "maxItems" in rule and len(value) > int(rule["maxItems"]):
                raise ValueError(f"{key} has at most {rule['maxItems']} items")
            if (rule.get("items") or {}).get("type") == "integer" and not all(
                    isinstance(item, int) and not isinstance(item, bool) for item in value):
                raise ValueError(f"{key} holds whole numbers")
        if "enum" in rule and value not in rule["enum"]:
            raise ValueError(f"{key} is one of {', '.join(map(str, rule['enum']))}")
    return arguments


def call_tool(credential: dict[str, Any], name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run a tool for a credential: its capability first, then the call; audited either way."""
    from app.security import audit

    tool = registered_tools().get(name)
    if tool is None:
        raise LookupError(f"no tool named {name}")
    if tool.capability and tool.capability not in credential["capabilities"]:
        audit.record("voice.client.call", target_type="voice_tool", target_id=name, outcome="denied",
                     details={"client_id": credential["id"], "capability": tool.capability})
        raise ClientCapabilityRefused(f"this client may not {name} (needs {tool.capability})")
    arguments = check_arguments(tool.input_schema, arguments if arguments is not None else {})
    token = _CALLING_CLIENT.set(str(credential["id"]))
    try:
        result = tool.call(arguments)
    except Exception as exc:
        audit.record("voice.client.call", target_type="voice_tool", target_id=name, outcome="failure",
                     details={"client_id": credential["id"], "error_type": type(exc).__name__})
        raise
    finally:
        _CALLING_CLIENT.reset(token)
    audit.record("voice.client.call", target_type="voice_tool", target_id=name,
                 details={"client_id": credential["id"]})
    return result


async def bound_client(authorization: str | None) -> dict[str, Any]:
    """For a route dependency: authenticate the bearer token and act in its workspace for the rest of the request.

    Async on purpose: the tenant is set in the request's own context, which the
    endpoint (run in a worker thread) inherits; the request tenant middleware
    restores the previous tenant when the request ends.
    """
    from fastapi import HTTPException
    from starlette.concurrency import run_in_threadpool

    from app.runtime.tenant_context import push_tenant

    challenge = {"WWW-Authenticate": 'Bearer realm="omnix-voice"'}
    scheme, _, token = str(authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="voice_client_token_required", headers=challenge)
    from app.security.secrets import SecretStoreUnavailable

    try:
        credential, context = await run_in_threadpool(authenticate, token.strip())
    except ClientCredentialError as exc:
        raise HTTPException(status_code=401, detail="voice_client_token_refused", headers=challenge) from exc
    except SecretStoreUnavailable as exc:
        logger.warning("Voice API clients are unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="voice_clients_unavailable") from exc
    push_tenant(context)
    return credential


__all__ = [
    "CAPABILITIES",
    "ClientCapabilityRefused",
    "ClientCredentialError",
    "authenticate",
    "bound_client",
    "call_tool",
    "check_arguments",
    "issue_credential",
    "list_credentials",
    "registered_tools",
    "revoke_credential",
    "store_client_audio",
    "voice_tool",
    "voice_tools",
]
