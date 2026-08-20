from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

from .contracts import IssuerIdentity, fingerprint

_SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"


def _symbol_exchange(instrument_id: str) -> tuple[str, str | None]:
    parts = [part for part in instrument_id.split(":") if part]
    if not parts:
        raise ValueError("invalid_instrument_id")
    symbol = parts[-1].upper()
    exchange = parts[-2].upper() if len(parts) >= 3 else None
    return symbol, exchange


class SecIssuerIdentityResolver:
    def __init__(self, runtime=None) -> None:
        if runtime is None:
            from app.trading.providers.http_runtime import ProviderHttpRuntime
            runtime = ProviderHttpRuntime("sec_issuer_identity", max_concurrency=1)
        self.runtime = runtime
        self._mapping: dict[str, dict[str, Any]] | None = None

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "User-Agent": os.environ.get(
                "OMNIX_SEC_USER_AGENT",
                "OmnixTradingResearch/1.0 local-research contact=local@localhost",
            ),
            "Accept-Encoding": "gzip, deflate",
            "Host": "www.sec.gov",
        }

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._mapping is not None:
            return self._mapping
        response = self.runtime.get(_SEC_TICKERS, headers=self._headers(), timeout=20)
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("sec_company_tickers_malformed")
        mapping: dict[str, dict[str, Any]] = {}
        for row in payload.values():
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "").upper().strip()
            if ticker:
                mapping[ticker] = row
        self._mapping = mapping
        return mapping

    def resolve(self, instrument_id: str) -> IssuerIdentity:
        symbol, exchange = _symbol_exchange(instrument_id)
        row = self._load().get(symbol)
        captured = datetime.now(timezone.utc)
        cik = None if row is None else str(row.get("cik_str") or "").zfill(10)
        legal_name = None if row is None else str(row.get("title") or "").strip() or None
        confidence = "1" if row is not None else "0"
        payload = {
            "instrument_id": instrument_id,
            "symbol": symbol,
            "exchange": exchange,
            "legal_name": legal_name,
            "cik": cik,
            "source": "sec_company_tickers",
            "captured_at": captured.isoformat(),
            "confidence": confidence,
        }
        fp = fingerprint(payload)
        return IssuerIdentity(
            identity_id=f"issuer-{hashlib.sha256((instrument_id + '|' + str(cik)).encode()).hexdigest()[:24]}",
            instrument_id=instrument_id,
            symbol=symbol,
            exchange=exchange,
            legal_name=legal_name,
            cik=cik,
            source="sec_company_tickers",
            source_available_at=captured,
            captured_at=captured,
            confidence=confidence,
            immutable_fingerprint=fp,
        )
