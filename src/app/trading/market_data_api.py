from __future__ import annotations

import asyncio
import sys
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.persistence.provider_secret_store import (
    load_trading_provider_secrets,
    save_trading_provider_secrets,
    trading_provider_credential_sources,
)
from app.persistence.runtime import LegacyPersistenceRetired


class CoinMarketCapCredentialStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["coinmarketcap"] = "coinmarketcap"
    configured: bool
    api_key_masked: str = ""
    api_key_source: Literal["environment", "os_protected_store", "missing"]
    api_key_editable: bool
    storage: str


class CoinMarketCapCredentialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str | None = Field(default=None, max_length=500)
    clear_api_key: bool = False


def _mask_key(value: str) -> str:
    clean = value.strip()
    if not clean:
        return ""
    if len(clean) <= 4:
        return "****"
    return f"***{clean[-4:]}"


def _credential_status() -> CoinMarketCapCredentialStatus:
    credentials = load_trading_provider_secrets().get("coinmarketcap") or {}
    sources = trading_provider_credential_sources("coinmarketcap")
    api_key = str(credentials.get("api_key") or "")
    return CoinMarketCapCredentialStatus(
        configured=bool(api_key),
        api_key_masked=_mask_key(api_key),
        api_key_source=sources["api_key"],
        api_key_editable=sys.platform == "win32" and sources["api_key"] != "environment",
        storage="Windows DPAPI user store" if sys.platform == "win32" else "environment only",
    )


def create_trading_market_data_router() -> APIRouter:
    router = APIRouter(prefix="/api/trading/market-data", tags=["trading-market-data"])

    @router.get("/providers/coinmarketcap/credentials", response_model=CoinMarketCapCredentialStatus)
    async def coinmarketcap_credentials() -> CoinMarketCapCredentialStatus:
        return await asyncio.to_thread(_credential_status)

    @router.put("/providers/coinmarketcap/credentials", response_model=CoinMarketCapCredentialStatus)
    async def update_coinmarketcap_credentials(
        request: CoinMarketCapCredentialUpdate,
    ) -> CoinMarketCapCredentialStatus:
        updates: dict[str, str | None] = {}
        if request.api_key is not None:
            updates["api_key"] = request.api_key
        if request.clear_api_key:
            updates["api_key"] = ""
        if not updates:
            return await asyncio.to_thread(_credential_status)
        try:
            await asyncio.to_thread(save_trading_provider_secrets, "coinmarketcap", updates)
            return await asyncio.to_thread(_credential_status)
        except LegacyPersistenceRetired as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
