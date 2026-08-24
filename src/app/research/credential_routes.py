"""Credential-safe routes for API-backed web research providers."""
from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.persistence import provider_secret_store as secret_store
from app.persistence.runtime import LegacyPersistenceRetired

_RESEARCH_CREDENTIAL_PROVIDERS = ("brave", "tavily")
_GET_ROUTE_NAME = "assistant_research_credentials_status_endpoint"
_UPDATE_ROUTE_NAME = "assistant_research_credentials_update_endpoint"


class ResearchCredentialUpdate(BaseModel):
    provider: Literal["brave", "tavily"]
    api_key: str = Field(default="", max_length=4096)


def _provider_status(provider: str) -> dict[str, object]:
    api_key = secret_store.load_research_provider_secrets().get(provider, "")
    source = secret_store.research_provider_credential_source(provider)
    return {
        "provider": provider,
        "configured": bool(api_key),
        "source": source,
        "editable": secret_store.research_provider_credential_editable(provider),
        "key_suffix": api_key[-4:] if api_key else None,
    }


def research_credentials_status() -> dict[str, object]:
    return {
        "providers": [_provider_status(provider) for provider in _RESEARCH_CREDENTIAL_PROVIDERS],
        "legacy_environment_key": any(
            secret_store.research_provider_credential_source(provider) == "legacy_environment"
            for provider in _RESEARCH_CREDENTIAL_PROVIDERS
        ),
    }


def register_research_credential_routes(app: FastAPI) -> None:
    route_names = {getattr(route, "name", "") for route in app.routes}

    if _GET_ROUTE_NAME not in route_names:

        @app.get(
            "/api/assistant/research/credentials",
            include_in_schema=False,
            name=_GET_ROUTE_NAME,
        )
        async def assistant_research_credentials_status_endpoint() -> dict[str, object]:
            return research_credentials_status()

    if _UPDATE_ROUTE_NAME not in route_names:

        @app.post(
            "/api/assistant/research/credentials",
            include_in_schema=False,
            name=_UPDATE_ROUTE_NAME,
        )
        async def assistant_research_credentials_update_endpoint(
            request: ResearchCredentialUpdate,
        ) -> dict[str, object]:
            source = secret_store.research_provider_credential_source(request.provider)
            if source in {"environment", "legacy_environment"}:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "research_credential_environment_owned",
                        "provider": request.provider,
                        "source": source,
                    },
                )
            try:
                secret_store.save_research_provider_secret(request.provider, request.api_key)
            except LegacyPersistenceRetired as exc:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "research_credential_store_unavailable",
                        "provider": request.provider,
                        "message": str(exc),
                    },
                ) from exc
            return research_credentials_status()