"""Private credential storage for connected assistant tools."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_CREDENTIALS_PATH = Path("resources/data/assistant_tool_credentials.json")
DEFAULT_OAUTH_CLIENTS_PATH = Path("resources/data/assistant_tool_oauth_clients.json")


class AssistantToolCredentialRecord(BaseModel):
    tool_id: str
    provider: str
    access_token: str = ""
    refresh_token: str | None = None
    token_type: str = "Bearer"
    scopes: list[str] = Field(default_factory=list)
    expires_at: str | None = None
    account_label: str | None = None
    account_email: str | None = None
    updated_at: str


class AssistantToolCredentialsPayload(BaseModel):
    credentials: list[AssistantToolCredentialRecord] = Field(default_factory=list)


class AssistantToolOAuthClientRecord(BaseModel):
    provider: str
    client_id: str
    client_secret: str
    updated_at: str


class AssistantToolOAuthClientsPayload(BaseModel):
    clients: list[AssistantToolOAuthClientRecord] = Field(default_factory=list)


def assistant_tool_credentials_path() -> Path:
    configured = os.environ.get("OMNIX_ASSISTANT_TOOLS_CREDENTIALS_PATH")
    return Path(configured) if configured else DEFAULT_CREDENTIALS_PATH


def assistant_tool_oauth_clients_path() -> Path:
    configured = os.environ.get("OMNIX_ASSISTANT_TOOLS_OAUTH_CLIENTS_PATH")
    return Path(configured) if configured else DEFAULT_OAUTH_CLIENTS_PATH


def load_assistant_tool_credentials(path: Path | None = None) -> AssistantToolCredentialsPayload:
    credentials_path = path or assistant_tool_credentials_path()
    if not credentials_path.exists():
        return AssistantToolCredentialsPayload()
    try:
        data = json.loads(credentials_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AssistantToolCredentialsPayload()
    return AssistantToolCredentialsPayload.model_validate(data)


def save_assistant_tool_credentials(payload: AssistantToolCredentialsPayload, path: Path | None = None) -> AssistantToolCredentialsPayload:
    credentials_path = path or assistant_tool_credentials_path()
    credentials_path.parent.mkdir(parents=True, exist_ok=True)
    credentials_path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    return payload


def load_assistant_tool_oauth_clients(path: Path | None = None) -> AssistantToolOAuthClientsPayload:
    clients_path = path or assistant_tool_oauth_clients_path()
    if not clients_path.exists():
        return AssistantToolOAuthClientsPayload()
    try:
        data = json.loads(clients_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AssistantToolOAuthClientsPayload()
    return AssistantToolOAuthClientsPayload.model_validate(data)


def save_assistant_tool_oauth_clients(payload: AssistantToolOAuthClientsPayload, path: Path | None = None) -> AssistantToolOAuthClientsPayload:
    clients_path = path or assistant_tool_oauth_clients_path()
    clients_path.parent.mkdir(parents=True, exist_ok=True)
    clients_path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    return payload


def oauth_client_for_provider(provider: str, path: Path | None = None) -> AssistantToolOAuthClientRecord | None:
    payload = load_assistant_tool_oauth_clients(path)
    normalized = provider.lower()
    return next((record for record in payload.clients if record.provider.lower() == normalized), None)


def upsert_oauth_client(record: AssistantToolOAuthClientRecord, path: Path | None = None) -> AssistantToolOAuthClientRecord:
    payload = load_assistant_tool_oauth_clients(path)
    normalized = record.provider.lower()
    payload.clients = [current for current in payload.clients if current.provider.lower() != normalized]
    payload.clients.append(record)
    save_assistant_tool_oauth_clients(payload, path)
    return record


def credential_for_tool(tool_id: str, path: Path | None = None) -> AssistantToolCredentialRecord | None:
    payload = load_assistant_tool_credentials(path)
    return next((record for record in payload.credentials if record.tool_id == tool_id), None)


def upsert_tool_credential(record: AssistantToolCredentialRecord, path: Path | None = None) -> AssistantToolCredentialRecord:
    payload = load_assistant_tool_credentials(path)
    payload.credentials = [current for current in payload.credentials if current.tool_id != record.tool_id]
    payload.credentials.append(record)
    save_assistant_tool_credentials(payload, path)
    return record


def delete_tool_credential(tool_id: str, path: Path | None = None) -> None:
    payload = load_assistant_tool_credentials(path)
    payload.credentials = [record for record in payload.credentials if record.tool_id != tool_id]
    save_assistant_tool_credentials(payload, path)


def expires_at_from_now(expires_in: object) -> str | None:
    try:
        seconds = int(expires_in) if isinstance(expires_in, (int, str, bytes, bytearray)) else 0
    except (TypeError, ValueError):
        seconds = 0
    if seconds <= 0:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def is_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        expiry = datetime.fromisoformat(expires_at)
    except ValueError:
        return True
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry <= datetime.now(timezone.utc) + timedelta(seconds=60)
