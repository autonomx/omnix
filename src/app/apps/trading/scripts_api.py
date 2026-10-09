"""Omnix Scripts over HTTP (TVP-11.1, 11.2): check a script, run it on a chart's bars, and the names for autocomplete.

Scripts are stored as trading documents (``/api/trading/scripts``, record type ``script``). A run reads the chart's
bars on the server and runs the script in a worker process (``scripts_service.py``): a script never reaches orders,
files or the network.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.security.tenant_context import current_tenant

from .scripts.builtins import _NAMED_CONSTANTS, COLORS, FUNCTIONS
from .scripts.runtime import SERIES_NAMES
from .scripts_service import ScriptRunService, ScriptServiceError, bars_for_script, check_script, default_script_service
from .service import TradingMarketDataService, default_market_data_service

logger = logging.getLogger(__name__)

# A script's source, as the editor and the documents keep it.
MAX_SOURCE_LENGTH = 200_000

# Names the editor completes besides the functions, constants and series.
KEYWORDS = (
    "if", "else", "for", "to", "by", "in", "while", "switch", "var", "varip", "true", "false", "na", "and", "or", "not",
    "break", "continue", "import", "export", "method", "type", "int", "float", "bool", "string", "color", "series", "simple", "const",
)
VARIABLES = (
    "bar_index", "last_bar_index", "barstate.isfirst", "barstate.islast", "barstate.isconfirmed", "barstate.isnew", "barstate.isrealtime",
    "barstate.ishistory", "syminfo.ticker", "syminfo.tickerid", "syminfo.mintick", "syminfo.timezone", "timeframe.period",
    "timeframe.multiplier", "timeframe.isintraday", "timeframe.isdaily", "timeframe.isweekly", "timeframe.ismonthly", "timenow",
)


class ScriptCheckRequest(BaseModel):
    source: str = Field(max_length=MAX_SOURCE_LENGTH)


class ScriptDiagnostic(BaseModel):
    kind: str
    message: str
    line: int
    column: int


class ScriptCheckResponse(BaseModel):
    diagnostics: list[ScriptDiagnostic]
    declaration: dict[str, Any] | None = None
    inputs: list[dict[str, Any]] = Field(default_factory=list)


class ScriptRunRequest(BaseModel):
    source: str = Field(max_length=MAX_SOURCE_LENGTH)
    instrument_id: str = Field(min_length=3, max_length=200)
    binding_id: str | None = Field(default=None, max_length=240)
    interval: str = Field(min_length=1, max_length=16)
    inputs: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=1_000, ge=10, le=5_000)
    # Time per top-level statement, for the editor's profiler (TVP-11.2).
    profile: bool = False


class ScriptRunResponse(BaseModel):
    # The start of each bar the script ran on (ISO), one per value in each plot.
    times: list[str]
    result: dict[str, Any] | None = None
    # The script's problem (with its line) or the service's (busy, stopped); the result is null then.
    error: ScriptDiagnostic | None = None


class ScriptReferenceResponse(BaseModel):
    functions: list[str]
    constants: list[str]
    variables: list[str]
    keywords: list[str]


def create_trading_scripts_router(
    service_factory: Callable[[], ScriptRunService] = default_script_service,
    market_service_factory: Callable[[], TradingMarketDataService] = default_market_data_service,
) -> APIRouter:
    router = APIRouter(prefix="/api/trading/scripts", tags=["trading-scripts"])

    @router.post("/check", response_model=ScriptCheckResponse)
    async def check(request: ScriptCheckRequest) -> ScriptCheckResponse:
        """Compile a script: its problems with their line and column, its declaration and inputs."""
        return ScriptCheckResponse.model_validate(await asyncio.to_thread(check_script, request.source))

    @router.post("/run", response_model=ScriptRunResponse)
    async def run(request: ScriptRunRequest) -> ScriptRunResponse:
        """Run a script on the latest ``limit`` bars of a chart (as the chart reads them, clock-aligned)."""
        try:
            response = await asyncio.to_thread(
                market_service_factory().bars, request.instrument_id, request.interval, request.limit, request.binding_id, alignment="clock",
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.warning("script_bars_failed", exc_info=True)
            raise HTTPException(status_code=502, detail={"code": "market_data_failed", "message": "The market data provider request failed."}) from exc
        bars = list(response.bars)
        times = [bar.start_time.isoformat() for bar in bars]
        user_id = str(getattr(current_tenant(), "user_id", "") or "")
        try:
            result = await asyncio.to_thread(
                service_factory().run, request.source, bars_for_script(bars), inputs=request.inputs,
                symbol=request.instrument_id, timeframe=request.interval, user_id=user_id, profile=request.profile,
            )
        except ScriptServiceError as error:
            return ScriptRunResponse(times=times, error=ScriptDiagnostic(**error.payload()))
        return ScriptRunResponse(times=times, result=result)

    @router.get("/reference", response_model=ScriptReferenceResponse)
    def reference() -> ScriptReferenceResponse:
        """The names the editor completes: functions, named constants, built-in series and variables, keywords."""
        return ScriptReferenceResponse(
            functions=sorted(FUNCTIONS),
            constants=sorted({*_NAMED_CONSTANTS, *(f"color.{name}" for name in COLORS)}),
            variables=sorted({*SERIES_NAMES, *VARIABLES}),
            keywords=list(KEYWORDS),
        )

    return router
