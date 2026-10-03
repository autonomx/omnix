"""Session, install-credential and login-code authentication (WP-4.1)."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import hmac
import logging
import secrets
from typing import TYPE_CHECKING, Any, Protocol

from app.runtime.tenant_context import (
    LOCAL_USER_ID,
    LOCAL_WORKSPACE_ID,
    TenantAccessDenied,
    TenantContext,
)

from .repository import PostgresAuthRepository, SessionSummary
from .settings import AuthMode, AuthSettings

if TYPE_CHECKING:
    from .oidc import OidcClient

logger = logging.getLogger(__name__)

SESSION_COOKIE = "omnix_session"
# The session cookie's name over HTTPS: the browser accepts it only with
# Secure, Path=/ and no Domain, so no other host can set or read it (ASVS 3.4.4).
SECURE_SESSION_COOKIE = "__Host-omnix_session"
CSRF_COOKIE = "omnix_csrf"
CSRF_HEADER = "x-omnix-csrf"

_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MAXMEM = 64 * 1024 * 1024


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def csrf_token_for(*, csrf_secret: str, session_id: str) -> str:
    return hmac.new(csrf_secret.encode("ascii"), session_id.encode("ascii"), hashlib.sha256).hexdigest()


def _scrypt(credential: str, salt: bytes, *, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        credential.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_SCRYPT_MAXMEM, dklen=32
    )


# Signing other devices out needs a fresh proof of identity (ASVS 3.3.4): the
# install credential in local mode, a sign-in this recent in OIDC mode.
REAUTHENTICATION_WINDOW_SECONDS = 10 * 60


class ReauthenticationRequired(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """The authenticated caller. WP-4.2 builds request tenancy on top of this."""

    user_id: str
    context: TenantContext
    auth_method: str
    session_id: str | None = None
    csrf_token: str | None = None


@dataclass(frozen=True, slots=True)
class IssuedSession:
    token: str
    csrf_token: str
    principal: AuthenticatedPrincipal
    max_age_seconds: int


class Authenticator(Protocol):
    """What the request middleware needs; tests substitute an in-memory fake."""

    settings: AuthSettings

    def authenticate_session(self, token: str) -> AuthenticatedPrincipal | None: ...

    def authenticate_bearer(self, token: str) -> AuthenticatedPrincipal | None: ...


class AuthService:
    def __init__(
        self,
        settings: AuthSettings,
        *,
        database: Any | None = None,
        oidc: Any | None = None,
        unit_of_work_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self._database = database
        self._oidc = oidc
        self._unit_of_work_factory = unit_of_work_factory

    # Infrastructure -------------------------------------------------------

    @contextmanager
    def _work(self) -> Iterator[Any]:
        # Sessions and login codes are looked up before the caller's
        # workspace is known, so they bypass row-level security (WP-4.4).
        from app.persistence.tenant_scope import system_scope

        with system_scope("auth.sessions"), self._unit_of_work() as work:
            yield work

    def _unit_of_work(self) -> Any:
        if self._unit_of_work_factory is not None:
            return self._unit_of_work_factory()
        from app.persistence.database import default_database
        from app.persistence.unit_of_work import unit_of_work

        if self._database is None:
            self._database = default_database()
        return unit_of_work(self._database)

    @property
    def oidc(self) -> OidcClient:
        if self._oidc is None:
            if self.settings.oidc is None:
                raise RuntimeError("oidc_not_configured")
            from .oidc import OidcClient

            self._oidc = OidcClient(self.settings.oidc)
        return self._oidc

    # Sessions -------------------------------------------------------------

    def _issue(self, work: Any, context: TenantContext, *, auth_method: str, user_agent: str | None) -> IssuedSession:
        token = secrets.token_urlsafe(32)
        session_id = digest(token)
        csrf_secret = secrets.token_hex(32)
        PostgresAuthRepository(work.connection).create_session(
            session_id=session_id,
            user_id=context.user_id,
            workspace_id=context.workspace_id,
            auth_method=auth_method,
            csrf_secret=csrf_secret,
            user_agent_hash=digest(user_agent) if user_agent else None,
            sliding_seconds=self.settings.sliding_ttl_seconds,
            absolute_seconds=self.settings.absolute_ttl_seconds,
        )
        work.audit.append(
            context,
            aggregate_type="auth_session",
            aggregate_id=session_id[:16],
            action="auth.login",
            payload={"auth_method": auth_method},
        )
        csrf = csrf_token_for(csrf_secret=csrf_secret, session_id=session_id)
        return IssuedSession(
            token=token,
            csrf_token=csrf,
            principal=AuthenticatedPrincipal(
                user_id=context.user_id,
                context=context,
                auth_method=f"session:{auth_method}",
                session_id=session_id,
                csrf_token=csrf,
            ),
            max_age_seconds=self.settings.absolute_ttl_seconds,
        )

    def authenticate_session(self, token: str) -> AuthenticatedPrincipal | None:
        if not token or len(token) > 256:
            return None
        session_id = digest(token)
        with self._work() as work:
            record = PostgresAuthRepository(work.connection).active_session(
                session_id, sliding_seconds=self.settings.sliding_ttl_seconds
            )
            if record is None:
                work.rollback()
                return None
            try:
                context = work.identities.load_context(
                    user_id=record.user_id, workspace_id=record.workspace_id
                )
            except TenantAccessDenied:
                # A disabled user or removed membership ends every session.
                work.rollback()
                return None
            work.commit()
        return AuthenticatedPrincipal(
            user_id=context.user_id,
            context=context,
            auth_method=f"session:{record.auth_method}",
            session_id=session_id,
            csrf_token=csrf_token_for(csrf_secret=record.csrf_secret, session_id=session_id),
        )

    def authenticate_bearer(self, token: str) -> AuthenticatedPrincipal | None:
        if self.settings.mode is not AuthMode.OIDC or self.settings.oidc is None:
            return None
        if self.settings.oidc.api_audience is None:
            return None
        claims = self.oidc.validate_access_token(token)
        if claims is None:
            return None
        with self._work() as work:
            user_id = PostgresAuthRepository(work.connection).external_identity_user(
                issuer=self.settings.oidc.issuer, subject=str(claims["sub"])
            )
            if user_id is None:
                work.rollback()
                return None
            try:
                context = work.identities.load_context(
                    user_id=user_id, workspace_id=self.settings.oidc.workspace_id
                )
            except TenantAccessDenied:
                work.rollback()
                return None
            work.rollback()
        return AuthenticatedPrincipal(user_id=user_id, context=context, auth_method="bearer")

    def logout(self, token: str) -> None:
        session_id = digest(token)
        with self._work() as work:
            repository = PostgresAuthRepository(work.connection)
            record = repository.active_session(session_id, sliding_seconds=self.settings.sliding_ttl_seconds)
            if repository.revoke_session(session_id) and record is not None:
                try:
                    context = work.identities.load_context(
                        user_id=record.user_id, workspace_id=record.workspace_id
                    )
                except TenantAccessDenied:
                    context = None
                if context is not None:
                    work.audit.append(
                        context,
                        aggregate_type="auth_session",
                        aggregate_id=session_id[:16],
                        action="auth.logout",
                        payload={},
                    )
            work.commit()

    def list_sessions(self, principal: AuthenticatedPrincipal) -> list[tuple[SessionSummary, bool]]:
        """The caller's active sessions, each with whether it is this one."""
        with self._work() as work:
            sessions = PostgresAuthRepository(work.connection).user_sessions(principal.user_id)
            work.rollback()
        return [(summary, session_id == principal.session_id) for session_id, summary in sessions]

    def revoke_sessions(
        self, principal: AuthenticatedPrincipal, *, handle: str | None, credential: str | None
    ) -> int:
        """Sign out one of the caller's sessions (by handle) or all the others.

        The caller proves its identity again first; the current session is
        never revoked here (that is logout).
        """
        if principal.session_id is None:
            raise ReauthenticationRequired("a browser session is required")
        with self._work() as work:
            repository = PostgresAuthRepository(work.connection)
            if self.settings.mode is AuthMode.LOCAL:
                stored = repository.install_credential()
                if (
                    not credential
                    or len(credential) > 512
                    or stored is None
                    or not hmac.compare_digest(
                        _scrypt(credential, stored.salt, n=stored.n, r=stored.r, p=stored.p),
                        stored.credential_hash,
                    )
                ):
                    self._audit_failure(work, "session_revocation")
                    work.commit()
                    raise ReauthenticationRequired("invalid_credential")
            else:
                age = repository.session_age_seconds(principal.session_id)
                if age is None or age > REAUTHENTICATION_WINDOW_SECONDS:
                    work.rollback()
                    raise ReauthenticationRequired("recent_sign_in_required")
            if handle is not None and principal.session_id.startswith(handle):
                work.rollback()
                return 0
            revoked = repository.revoke_user_sessions_matching(
                principal.user_id, handle=handle, keep=principal.session_id
            )
            work.audit.append(
                principal.context,
                aggregate_type="auth_session",
                aggregate_id=principal.session_id[:16],
                action="auth.sessions.revoked",
                payload={"scope": "one" if handle is not None else "others", "revoked": revoked},
            )
            work.commit()
        return revoked

    # Local mode -----------------------------------------------------------

    def sync_install_credential(self, plaintext: str) -> bool:
        """Make the database verifier match the protected install credential.

        Returns True when the verifier changed. A change revokes every local
        session, because whoever held the old credential must sign in again.
        """
        with self._work() as work:
            repository = PostgresAuthRepository(work.connection)
            current = repository.install_credential()
            if current is not None and hmac.compare_digest(
                _scrypt(plaintext, current.salt, n=current.n, r=current.r, p=current.p),
                current.credential_hash,
            ):
                work.rollback()
                return False
            salt = secrets.token_bytes(16)
            repository.store_install_credential(
                user_id=LOCAL_USER_ID,
                workspace_id=LOCAL_WORKSPACE_ID,
                salt=salt,
                credential_hash=_scrypt(plaintext, salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P),
                n=_SCRYPT_N,
                r=_SCRYPT_R,
                p=_SCRYPT_P,
            )
            revoked = repository.revoke_user_sessions(LOCAL_USER_ID) if current is not None else 0
            context = work.identities.load_context(user_id=LOCAL_USER_ID, workspace_id=LOCAL_WORKSPACE_ID)
            work.audit.append(
                context,
                aggregate_type="install_credential",
                aggregate_id="install",
                action="auth.install_credential.provisioned" if current is None else "auth.install_credential.rotated",
                payload={"revoked_sessions": revoked},
            )
            work.commit()
        return True

    def login_with_install_credential(self, presented: str, *, user_agent: str | None) -> IssuedSession | None:
        if self.settings.mode is not AuthMode.LOCAL or not presented or len(presented) > 512:
            return None
        with self._work() as work:
            stored = PostgresAuthRepository(work.connection).install_credential()
            if stored is None or not hmac.compare_digest(
                _scrypt(presented, stored.salt, n=stored.n, r=stored.r, p=stored.p),
                stored.credential_hash,
            ):
                self._audit_failure(work, "install_credential")
                work.commit()
                return None
            context = work.identities.load_context(user_id=stored.user_id, workspace_id=stored.workspace_id)
            issued = self._issue(work, context, auth_method="local", user_agent=user_agent)
            work.commit()
            return issued

    def issue_login_code(self) -> str:
        """Single-use, 60-second code the launcher exchanges for a session."""
        if self.settings.mode is not AuthMode.LOCAL:
            raise RuntimeError("login codes are available only in local auth mode")
        code = secrets.token_urlsafe(32)
        with self._work() as work:
            PostgresAuthRepository(work.connection).insert_login_code(
                code_hash=digest(code),
                user_id=LOCAL_USER_ID,
                workspace_id=LOCAL_WORKSPACE_ID,
                ttl_seconds=self.settings.login_code_ttl_seconds,
            )
            work.commit()
        return code

    def exchange_login_code(self, code: str, *, user_agent: str | None) -> IssuedSession | None:
        if self.settings.mode is not AuthMode.LOCAL or not code or len(code) > 256:
            return None
        with self._work() as work:
            grant = PostgresAuthRepository(work.connection).consume_login_code(digest(code))
            if grant is None:
                self._audit_failure(work, "login_code")
                work.commit()
                return None
            context = work.identities.load_context(user_id=grant[0], workspace_id=grant[1])
            issued = self._issue(work, context, auth_method="local", user_agent=user_agent)
            work.commit()
            return issued

    def _audit_failure(self, work: Any, method: str) -> None:
        # Failed attempts have no authenticated actor; attribute them to the
        # installation workspace without recording the presented secret.
        try:
            context = work.identities.load_context(user_id=LOCAL_USER_ID, workspace_id=LOCAL_WORKSPACE_ID)
        except TenantAccessDenied:
            return
        work.audit.append(
            context,
            aggregate_type="auth",
            aggregate_id=method,
            action="auth.failed",
            payload={"method": method},
        )

    # OIDC mode ------------------------------------------------------------

    def start_oidc_login(self, *, redirect_after: str) -> tuple[str, str]:
        """Return (authorization_url, browser_binding) for a new login."""
        start = self.oidc.begin(redirect_after=redirect_after)
        with self._work() as work:
            PostgresAuthRepository(work.connection).insert_oidc_state(
                state_hash=digest(start.state),
                browser_binding_hash=digest(start.browser_binding),
                nonce=start.nonce,
                code_verifier=start.code_verifier,
                redirect_after=start.redirect_after,
                ttl_seconds=600,
            )
            work.commit()
        return start.authorization_url, start.browser_binding

    def complete_oidc_login(
        self, *, code: str, state: str, browser_binding: str, user_agent: str | None
    ) -> tuple[IssuedSession, str] | None:
        settings = self.settings.oidc
        if settings is None or not code or not state or not browser_binding:
            return None
        with self._work() as work:
            login = PostgresAuthRepository(work.connection).consume_oidc_state(
                state_hash=digest(state), browser_binding_hash=digest(browser_binding)
            )
            work.commit()
        if login is None:
            return None
        claims = self.oidc.exchange_code(code=code, code_verifier=login.code_verifier, nonce=login.nonce)
        if claims is None:
            return None
        decision = self.oidc.admission(claims)
        if not decision.allowed:
            logger.info("oidc_login_rejected", extra={"reason": decision.reason})
            return None
        subject = str(claims["sub"])
        with self._work() as work:
            repository = PostgresAuthRepository(work.connection)
            user_id = repository.external_identity_user(issuer=settings.issuer, subject=subject)
            if user_id is None:
                user_id = f"user:oidc:{digest(settings.issuer + '|' + subject)[:32]}"
            context = work.identities.provision_member(
                user_id=user_id,
                display_name=decision.display_name,
                email=decision.email,
                workspace_id=settings.workspace_id,
                roles=(settings.default_role,),
            )
            repository.link_external_identity(
                issuer=settings.issuer, subject=subject, user_id=user_id, email=decision.email
            )
            issued = self._issue(work, context, auth_method="oidc", user_agent=user_agent)
            work.commit()
        return issued, login.redirect_after
