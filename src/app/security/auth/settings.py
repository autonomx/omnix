"""Authentication mode and session policy resolved from configuration (WP-4.1)."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import ipaddress
import logging

from app.config.env import env_bool, env_int, env_list, env_str

logger = logging.getLogger(__name__)

# Human gate (roadmap WP-4.1): existing installs keep today's unauthenticated
# behaviour until the operator approves enforcing local auth by default. An
# explicit OMNIX_AUTH_MODE always takes effect.
AUTH_ENFORCED_WHEN_UNSET = False


class AuthMode(str, Enum):
    LOCAL = "local"
    OIDC = "oidc"
    DISABLED = "disabled"


class AuthConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OidcSettings:
    issuer: str
    client_id: str
    client_secret: str | None
    redirect_uri: str
    scopes: tuple[str, ...]
    api_audience: str | None
    allowed_domains: tuple[str, ...]
    required_group: str | None
    groups_claim: str
    workspace_id: str
    default_role: str


@dataclass(frozen=True, slots=True)
class AuthSettings:
    mode: AuthMode
    enforced: bool
    explicit: bool
    cookie_secure: bool
    sliding_ttl_seconds: int
    absolute_ttl_seconds: int
    login_code_ttl_seconds: int
    oidc: OidcSettings | None = None


def _oidc_settings(env: Mapping[str, str] | None) -> OidcSettings:
    issuer = (env_str("OMNIX_OIDC_ISSUER", "", env=env) or "").strip().rstrip("/")
    client_id = (env_str("OMNIX_OIDC_CLIENT_ID", "", env=env) or "").strip()
    redirect_uri = (env_str("OMNIX_OIDC_REDIRECT_URI", "", env=env) or "").strip()
    if not issuer or not client_id or not redirect_uri:
        raise AuthConfigurationError(
            "OMNIX_AUTH_MODE=oidc requires OMNIX_OIDC_ISSUER, OMNIX_OIDC_CLIENT_ID "
            "and OMNIX_OIDC_REDIRECT_URI"
        )
    if not issuer.startswith("https://") and not _loopback_url(issuer):
        raise AuthConfigurationError("OMNIX_OIDC_ISSUER must use https")
    role = (env_str("OMNIX_OIDC_DEFAULT_ROLE", "member", env=env) or "member").strip()
    if role not in {"member", "viewer"}:
        # Just-in-time provisioning must never mint privileged roles.
        raise AuthConfigurationError("OMNIX_OIDC_DEFAULT_ROLE must be member or viewer")
    return OidcSettings(
        issuer=issuer,
        client_id=client_id,
        client_secret=(env_str("OMNIX_OIDC_CLIENT_SECRET", env=env) or None),
        redirect_uri=redirect_uri,
        scopes=env_list("OMNIX_OIDC_SCOPES", ("openid", "email", "profile"), env=env),
        api_audience=(env_str("OMNIX_OIDC_API_AUDIENCE", env=env) or None),
        allowed_domains=tuple(
            domain.strip().lower().lstrip("@")
            for domain in env_list("OMNIX_OIDC_ALLOWED_DOMAINS", (), env=env)
            if domain.strip()
        ),
        required_group=(env_str("OMNIX_OIDC_REQUIRED_GROUP", env=env) or None),
        groups_claim=(env_str("OMNIX_OIDC_GROUPS_CLAIM", "groups", env=env) or "groups"),
        workspace_id=(env_str("OMNIX_OIDC_WORKSPACE_ID", "workspace:local", env=env) or "workspace:local"),
        default_role=role,
    )


def _loopback_url(url: str) -> bool:
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def resolve_auth_settings(env: Mapping[str, str] | None = None) -> AuthSettings:
    raw = env_str("OMNIX_AUTH_MODE", env=env)
    explicit = raw is not None and bool(raw.strip())
    value = (raw or AuthMode.LOCAL.value).strip().lower()
    try:
        mode = AuthMode(value)
    except ValueError as exc:
        raise AuthConfigurationError(f"unsupported OMNIX_AUTH_MODE {value!r}") from exc
    enforced = mode is not AuthMode.DISABLED and (explicit or AUTH_ENFORCED_WHEN_UNSET)
    sliding_hours = env_int("OMNIX_AUTH_SESSION_IDLE_HOURS", 12, minimum=1, maximum=24 * 30, env=env)
    absolute_days = env_int("OMNIX_AUTH_SESSION_MAX_DAYS", 7, minimum=1, maximum=90, env=env)
    sliding = sliding_hours * 3600
    absolute = max(absolute_days * 86400, sliding)
    return AuthSettings(
        mode=mode,
        enforced=enforced,
        explicit=explicit,
        cookie_secure=env_bool("OMNIX_AUTH_COOKIE_SECURE", False, env=env),
        sliding_ttl_seconds=sliding,
        absolute_ttl_seconds=absolute,
        login_code_ttl_seconds=60,
        oidc=_oidc_settings(env) if enforced and mode is AuthMode.OIDC else None,
    )


def _loopback_host(host: str) -> bool:
    candidate = host.strip().strip("[]").lower()
    if candidate == "localhost":
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def assert_auth_startup_allowed(
    settings: AuthSettings,
    *,
    bind_host: str | None,
    env: Mapping[str, str] | None = None,
) -> None:
    """Fail startup when authentication is off outside a safe local context."""
    deployment = (env_str("OMNIX_ENV", "development", env=env) or "development").strip().lower()
    if settings.mode is AuthMode.DISABLED:
        if deployment == "test":
            return
        if deployment == "development" and bind_host is not None and _loopback_host(bind_host):
            return
        raise AuthConfigurationError(
            "OMNIX_AUTH_MODE=disabled is allowed only with OMNIX_ENV=test, or "
            "OMNIX_ENV=development bound to a loopback address"
        )
    if not settings.enforced:
        logger.warning(
            "authentication_not_enforced: OMNIX_AUTH_MODE is unset; set "
            "OMNIX_AUTH_MODE=local to require sign-in (pending the WP-4.1 default flip)"
        )
