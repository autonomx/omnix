"""Login, logout and session endpoints under ``/api/auth`` (WP-4.1).

These routes are public in the authentication middleware; each one
authenticates its own input. They live under ``/api`` so the existing
development proxy and production ingress forward them unchanged.
"""
from __future__ import annotations

from collections.abc import Callable
import hmac
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.observability.metrics import record_auth_rejection
from app.security.rate_limit import rate_limited

from .oidc import safe_redirect_path
from .service import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    AuthService,
    IssuedSession,
)
from .settings import AuthMode

OIDC_TX_COOKIE = "omnix_oidc_tx"
_OIDC_TX_PATH = "/api/auth/oidc"


class AuthSessionResponse(BaseModel):
    enforced: bool
    mode: Literal["local", "oidc", "disabled"]
    authenticated: bool
    user_id: str | None = None
    workspace_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    auth_method: str | None = None


class LocalLoginRequest(BaseModel):
    credential: str = Field(min_length=1, max_length=512)


def _set_session_cookies(response: Response, issued: IssuedSession, *, secure: bool) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        issued.token,
        max_age=issued.max_age_seconds,
        httponly=True,
        samesite="strict",
        secure=secure,
        path="/",
    )
    # Readable by the web app, which echoes it in X-Omnix-CSRF.
    response.set_cookie(
        CSRF_COOKIE,
        issued.csrf_token,
        max_age=issued.max_age_seconds,
        httponly=False,
        samesite="strict",
        secure=secure,
        path="/",
    )


def _clear_session_cookies(response: Response, *, secure: bool) -> None:
    for name, http_only in ((SESSION_COOKIE, True), (CSRF_COOKIE, False)):
        response.delete_cookie(name, path="/", secure=secure, httponly=http_only, samesite="strict")


def _user_agent(request: Request) -> str | None:
    value = request.headers.get("user-agent")
    return value[:512] if value else None


def create_auth_router(get_service: Callable[[], AuthService | None]) -> APIRouter:
    router = APIRouter(prefix="/api/auth", tags=["auth"])
    # Sign-in attempts are limited per client address (WP-4.10).
    login_rate_limit = rate_limited("login")

    def service_for(mode: AuthMode | None = None) -> AuthService:
        service = get_service()
        if service is None or not service.settings.enforced:
            raise HTTPException(status_code=404, detail="authentication_not_enforced")
        if mode is not None and service.settings.mode is not mode:
            raise HTTPException(status_code=404, detail="auth_mode_inactive")
        return service

    def revoke_presented(service: AuthService, request: Request) -> None:
        # Rotation: a new login always replaces any session the browser held.
        previous = request.cookies.get(SESSION_COOKIE)
        if previous:
            service.logout(previous)

    @router.get("/session", response_model=AuthSessionResponse)
    def current_session(request: Request) -> AuthSessionResponse:
        service = get_service()
        if service is None or not service.settings.enforced:
            mode = service.settings.mode if service is not None else AuthMode.DISABLED
            return AuthSessionResponse(enforced=False, mode=mode.value, authenticated=False)
        token = request.cookies.get(SESSION_COOKIE)
        principal = service.authenticate_session(token) if token else None
        if principal is None:
            # 200, not 401: the sign-in page reads the mode from this response.
            return AuthSessionResponse(enforced=True, mode=service.settings.mode.value, authenticated=False)
        return AuthSessionResponse(
            enforced=True,
            mode=service.settings.mode.value,
            authenticated=True,
            user_id=principal.user_id,
            workspace_id=principal.context.workspace_id,
            roles=sorted(principal.context.roles),
            auth_method=principal.auth_method,
        )

    @router.post("/local/login", response_model=AuthSessionResponse, dependencies=[Depends(login_rate_limit)])
    def local_login(body: LocalLoginRequest, request: Request, response: Response) -> AuthSessionResponse:
        service = service_for(AuthMode.LOCAL)
        issued = service.login_with_install_credential(body.credential, user_agent=_user_agent(request))
        if issued is None:
            record_auth_rejection("invalid_credential")
            raise HTTPException(status_code=401, detail="invalid_credential")
        revoke_presented(service, request)
        _set_session_cookies(response, issued, secure=service.settings.cookie_secure)
        context = issued.principal.context
        return AuthSessionResponse(
            enforced=True,
            mode="local",
            authenticated=True,
            user_id=context.user_id,
            workspace_id=context.workspace_id,
            roles=sorted(context.roles),
            auth_method=issued.principal.auth_method,
        )

    @router.get("/local/callback", response_class=RedirectResponse, status_code=303, dependencies=[Depends(login_rate_limit)])
    def local_callback(request: Request, code: str = "", next: str = "/") -> RedirectResponse:
        service = service_for(AuthMode.LOCAL)
        issued = service.exchange_login_code(code, user_agent=_user_agent(request))
        if issued is None:
            return RedirectResponse("/login?error=login_link_expired", status_code=303)
        revoke_presented(service, request)
        redirect = RedirectResponse(safe_redirect_path(next), status_code=303)
        _set_session_cookies(redirect, issued, secure=service.settings.cookie_secure)
        return redirect

    @router.post("/logout", status_code=204)
    def logout(request: Request) -> Response:
        service = service_for()
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            principal = service.authenticate_session(token)
            supplied = request.headers.getlist(CSRF_HEADER)
            if principal is not None and (
                len(supplied) != 1
                or not principal.csrf_token
                or not hmac.compare_digest(supplied[0], principal.csrf_token)
            ):
                raise HTTPException(status_code=403, detail="csrf_failed")
            service.logout(token)
        response = Response(status_code=204)
        _clear_session_cookies(response, secure=service.settings.cookie_secure)
        return response

    @router.get("/oidc/login", response_class=RedirectResponse, status_code=302)
    def oidc_login(next: str = "/") -> RedirectResponse:
        service = service_for(AuthMode.OIDC)
        url, binding = service.start_oidc_login(redirect_after=next)
        redirect = RedirectResponse(url, status_code=302)
        # Lax, not Strict: the IdP returns the browser with a cross-site
        # top-level navigation, which must still carry this binding.
        redirect.set_cookie(
            OIDC_TX_COOKIE,
            binding,
            max_age=600,
            httponly=True,
            samesite="lax",
            secure=service.settings.cookie_secure,
            path=_OIDC_TX_PATH,
        )
        return redirect

    @router.get("/oidc/callback", response_class=RedirectResponse, status_code=303, dependencies=[Depends(login_rate_limit)])
    def oidc_callback(request: Request, code: str = "", state: str = "") -> RedirectResponse:
        service = service_for(AuthMode.OIDC)
        binding = request.cookies.get(OIDC_TX_COOKIE) or ""
        result = service.complete_oidc_login(
            code=code, state=state, browser_binding=binding, user_agent=_user_agent(request)
        )
        if result is None:
            failure = RedirectResponse("/login?error=sign_in_failed", status_code=303)
            failure.delete_cookie(OIDC_TX_COOKIE, path=_OIDC_TX_PATH)
            return failure
        issued, redirect_after = result
        revoke_presented(service, request)
        redirect = RedirectResponse(safe_redirect_path(redirect_after), status_code=303)
        redirect.delete_cookie(OIDC_TX_COOKIE, path=_OIDC_TX_PATH)
        _set_session_cookies(redirect, issued, secure=service.settings.cookie_secure)
        return redirect

    return router
