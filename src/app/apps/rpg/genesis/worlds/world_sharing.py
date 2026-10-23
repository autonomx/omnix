"""Sharing a world to the community catalog: a pull request from the author's own GitHub account.

The author signs in to GitHub once (a token they paste, or GitHub's device sign-in when an OAuth app is configured);
the token stays in Omnix's secret store. Sharing exports the world as a bundle, puts it on a release of the author's
fork of the catalog repository, and opens a pull request that adds a submission file naming that release file, its
size and its SHA-256. The catalog's maintainers review and merge it; the catalog's own workflow then checks the file
and lists it. Nothing reaches the catalog without that review.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

import certifi

from app.config.env import env_str
from app.persistence.unit_of_work import unit_of_work
from app.runtime.tenant_context import LOCAL_WORKSPACE_ID, current_tenant
from app.security.secrets import require_writable, secret_store

from .world_adoption import shared_world_state
from .world_bundle import MAX_WORLD_BUNDLE_BYTES
from .world_bundle_export import export_world_bundle
from .world_catalog import catalog_repo

SUBMISSION_SCHEMA = "omnix-world-submission-v1"
_API = "https://api.github.com"
_UPLOADS = "https://uploads.github.com"
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
_DEVICE_FLOWS: dict[str, dict[str, Any]] = {}
_DEVICE_LOCK = threading.Lock()


class GitHubError(ValueError):
    """GitHub refused a request; the message says which step and why."""


@dataclass(frozen=True)
class GitHubResponse:
    status: int
    body: Any


Transport = Callable[[str, str, Mapping[str, str], bytes | None], GitHubResponse]


def _transport(method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> GitHubResponse:
    request = urllib.request.Request(url, data=body, method=method, headers={"User-Agent": "Omnix-World-Sharing/1.0", **headers})
    try:
        with urllib.request.urlopen(request, timeout=300, context=_SSL_CONTEXT) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read(), exc.code
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError:
        parsed = {"message": raw[:200].decode("utf-8", "replace")}
    return GitHubResponse(status=status, body=parsed)


def _secret_name() -> str:
    try:
        workspace = current_tenant().workspace_id
    except RuntimeError:
        workspace = LOCAL_WORKSPACE_ID
    return f"rpg-world-sharing/{workspace}/github"


def _stored() -> dict[str, str]:
    raw = secret_store().get(_secret_name())
    return dict(json.loads(raw)) if raw else {}


class GitHub:
    def __init__(self, token: str, transport: Transport = _transport) -> None:
        self.token = token
        self.transport = transport

    def call(self, method: str, path: str, payload: Any = None, *, step: str, ok: tuple[int, ...] = (200, 201)) -> Any:
        url = path if path.startswith("https://") else f"{_API}{path}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Content-Type": "application/json"} if body is not None else {}),
        }
        response = self.transport(method, url, headers, body)
        if response.status not in ok:
            message = str(dict(response.body).get("message") or "") if isinstance(response.body, Mapping) else ""
            raise GitHubError(f"github_{step}_failed:{response.status}:{message[:200]}")
        return response.body

    def upload(self, url: str, content: bytes, *, step: str) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/zip",
        }
        response = self.transport("POST", url, headers, content)
        if response.status not in (200, 201):
            raise GitHubError(f"github_{step}_failed:{response.status}")
        return response.body


def device_client_id() -> str:
    """The OAuth app whose device sign-in Omnix offers; without one, the author pastes a token."""
    return (env_str("OMNIX_GITHUB_WORLD_SHARING_CLIENT_ID") or "").strip()


def sharing_status() -> dict[str, Any]:
    stored = _stored()
    return {
        "ok": True,
        "connected": bool(stored.get("token")),
        "login": stored.get("login") or None,
        "device_sign_in": bool(device_client_id()),
        "catalog_repo": catalog_repo(),
    }


def connect_with_token(token: str, *, transport: Transport = _transport) -> dict[str, Any]:
    token = token.strip()
    if not token:
        raise ValueError("github_token_required")
    user = GitHub(token, transport).call("GET", "/user", step="sign_in")
    login = str(dict(user).get("login") or "")
    if not login:
        raise GitHubError("github_sign_in_failed:no_login")
    require_writable(secret_store()).set(_secret_name(), json.dumps({"token": token, "login": login}))
    return sharing_status()


def disconnect() -> dict[str, Any]:
    secret_store().delete(_secret_name())
    return sharing_status()


def _form(url: str, values: Mapping[str, str], transport: Transport) -> dict[str, Any]:
    body = urllib.parse.urlencode(values).encode("utf-8")
    response = transport("POST", url, {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}, body)
    return dict(response.body) if isinstance(response.body, Mapping) else {}


def start_device_sign_in(*, transport: Transport = _transport) -> dict[str, Any]:
    client_id = device_client_id()
    if not client_id:
        raise ValueError("github_device_sign_in_not_configured")
    started = _form("https://github.com/login/device/code", {"client_id": client_id, "scope": "public_repo"}, transport)
    if not started.get("device_code"):
        raise GitHubError(f"github_device_sign_in_failed:{started.get('error') or 'no_code'}")
    flow_id = secrets.token_urlsafe(16)
    with _DEVICE_LOCK:
        # The device code stays on the server; the page only polls by this id.
        _DEVICE_FLOWS[flow_id] = {
            "device_code": str(started["device_code"]),
            "expires": time.monotonic() + int(started.get("expires_in") or 900),
        }
    return {
        "ok": True,
        "flow_id": flow_id,
        "user_code": str(started.get("user_code") or ""),
        "verification_uri": str(started.get("verification_uri") or "https://github.com/login/device"),
        "interval": int(started.get("interval") or 5),
    }


def poll_device_sign_in(flow_id: str, *, transport: Transport = _transport) -> dict[str, Any]:
    with _DEVICE_LOCK:
        flow = _DEVICE_FLOWS.get(flow_id)
    if flow is None or flow["expires"] < time.monotonic():
        raise ValueError("github_device_sign_in_expired")
    result = _form(
        "https://github.com/login/oauth/access_token",
        {
            "client_id": device_client_id(),
            "device_code": flow["device_code"],
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
        transport,
    )
    error = str(result.get("error") or "")
    if error in {"authorization_pending", "slow_down"}:
        return {**sharing_status(), "status": "pending"}
    with _DEVICE_LOCK:
        _DEVICE_FLOWS.pop(flow_id, None)
    if not result.get("access_token"):
        raise GitHubError(f"github_device_sign_in_failed:{error or 'no_token'}")
    return {**connect_with_token(str(result["access_token"]), transport=transport), "status": "connected"}


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:60].strip("-")
    return slug if len(slug) >= 3 else f"world-{slug}".strip("-")


def _fork(github: GitHub, repo: str, login: str) -> str:
    fork = dict(github.call("POST", f"/repos/{repo}/forks", {"default_branch_only": True}, step="fork", ok=(200, 202)))
    full_name = str(fork.get("full_name") or f"{login}/{repo.split('/')[1]}")
    for _ in range(30):
        try:
            github.call("GET", f"/repos/{full_name}", step="fork_ready")
            return full_name
        except GitHubError:
            time.sleep(2)
    raise GitHubError("github_fork_ready_failed:timeout")


def share_world(
    world_id: str,
    *,
    summary: str,
    database: Any | None = None,
    transport: Transport = _transport,
) -> dict[str, Any]:
    """Open a pull request that adds this world to the community catalog."""

    stored = _stored()
    if not stored.get("token"):
        raise ValueError("github_not_connected")
    context = current_tenant()
    with unit_of_work(database) as work:
        world = work.world_scenarios.get_world(context, world_id)
        playable = work.connection.execute(
            "SELECT 1 FROM omnix_rpg_world_releases WHERE workspace_id = %s AND world_id = %s "
            "AND document_jsonb -> 'certification' ->> 'launch_ready' = 'true' LIMIT 1",
            (context.workspace_id, world_id),
        ).fetchone()
        work.rollback()
    if world is None:
        raise KeyError(f"world_not_found:{world_id}")
    if playable is None:
        # Only a finished world is shared: whoever downloads it can play it straight after adopting it.
        raise ValueError("world_sharing_not_published")
    if shared_world_state(world)["shared"]:
        # Someone else's world, downloaded or imported here: its author shares it, not whoever installed it.
        raise ValueError("world_sharing_imported_world")
    bundle = export_world_bundle(world_id, database=database)
    if len(bundle.content) > MAX_WORLD_BUNDLE_BYTES:
        raise ValueError("world_bundle_size_limit_exceeded")
    digest = hashlib.sha256(bundle.content).hexdigest()

    github = GitHub(str(stored["token"]), transport)
    login = str(dict(github.call("GET", "/user", step="sign_in")).get("login") or stored.get("login") or "")
    repo = catalog_repo()
    fork = _fork(github, repo, login)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    slug = _slug(str(world.get("title") or world_id))
    tag = f"world-{slug}-{stamp}"
    filename = f"{slug}.omnix-world.zip"
    release = dict(
        github.call(
            "POST",
            f"/repos/{fork}/releases",
            {"tag_name": tag, "name": f"{world.get('title') or slug} (submission)", "prerelease": True,
             "body": "A world bundle submitted to the Omnix community catalog."},
            step="release",
        )
    )
    upload_url = f"{_UPLOADS}/repos/{fork}/releases/{int(release['id'])}/assets?name={urllib.parse.quote(filename)}"
    asset = dict(github.upload(upload_url, bundle.content, step="upload"))
    submission = {
        "schema_version": SUBMISSION_SCHEMA,
        "id": slug,
        "title": str(world.get("title") or slug),
        "summary": summary.strip()[:2000] or str(world.get("description") or "")[:2000],
        "genre": str(world.get("genre") or ""),
        "tone": str(world.get("tone") or ""),
        "author": login,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "bundle": {"url": str(asset.get("browser_download_url") or ""), "sha256": digest, "bytes": len(bundle.content)},
    }
    base = dict(github.call("GET", f"/repos/{repo}/git/ref/heads/main", step="branch_base"))
    branch = f"share/{slug}-{stamp}"
    github.call("POST", f"/repos/{fork}/git/refs", {"ref": f"refs/heads/{branch}", "sha": base["object"]["sha"]}, step="branch")
    github.call(
        "PUT",
        f"/repos/{fork}/contents/submissions/{slug}.json",
        {
            "message": f"Submit world: {submission['title']}",
            "branch": branch,
            "content": base64.b64encode((json.dumps(submission, indent=2) + "\n").encode("utf-8")).decode("ascii"),
        },
        step="submission",
    )
    pull = dict(
        github.call(
            "POST",
            f"/repos/{repo}/pulls",
            {
                "title": f"Add world: {submission['title']}",
                "head": f"{login}:{branch}",
                "base": "main",
                "body": (
                    f"{submission['summary']}\n\n"
                    f"- Bundle: {submission['bundle']['url']}\n"
                    f"- SHA-256: `{digest}` ({len(bundle.content):,} bytes)\n\n"
                    "Submitted from Omnix. The catalog workflow checks the bundle before it is listed."
                ),
                "maintainer_can_modify": True,
            },
            step="pull_request",
        )
    )
    return {
        "ok": True,
        "status": "submitted",
        "world_id": world_id,
        "catalog_id": slug,
        "pull_request_url": str(pull.get("html_url") or ""),
        "bundle_sha256": digest,
        "bundle_bytes": len(bundle.content),
    }


__all__ = [
    "GitHubError",
    "connect_with_token",
    "disconnect",
    "poll_device_sign_in",
    "share_world",
    "sharing_status",
    "start_device_sign_in",
]
