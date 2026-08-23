from __future__ import annotations

from pathlib import Path


REPOSITORY = Path("src/app/trading/strategy_repository.py")
MONITOR = Path("src/app/trading/strategy_monitor.py")
API = Path("src/app/trading/strategy_api.py")
GATEWAY = Path("src/app/gateway/trading_routes.py")


def replace_exact(text: str, old: str, new: str, label: str, *, count: int = 1) -> str:
    actual = text.count(old)
    if actual != count:
        raise RuntimeError(f"{label}: expected {count} anchors, found {actual}")
    return text.replace(old, new, count)


def patch_repository() -> None:
    text = REPOSITORY.read_text(encoding="utf-8")
    anchor = """        return [_event(row) for row in rows]\n\n    def entry_events_between(\n"""
    replacement = """        return [_event(row) for row in rows]\n\n    def events_by_types_between(\n        self,\n        strategy_id: str,\n        *,\n        event_types: list[str] | tuple[str, ...],\n        start_time: datetime,\n        end_time: datetime,\n        limit: int = 10_000,\n    ) -> list[StrategyEvent]:\n        if start_time.tzinfo is None or end_time.tzinfo is None:\n            raise ValueError(\"qualification event boundaries must be timezone-aware\")\n        if end_time <= start_time:\n            raise ValueError(\"qualification event end_time must follow start_time\")\n        normalized_types = [str(value).strip() for value in event_types if str(value).strip()]\n        if not normalized_types:\n            return []\n        if limit < 1 or limit > 50_000:\n            raise ValueError(\"qualification event limit must be between 1 and 50000\")\n        with self.uow_factory() as uow:\n            rows = uow.connection.execute(\n                f\"\"\"\n                SELECT {_EVENT_COLUMNS}\n                  FROM omnix_trading_strategy_events\n                 WHERE workspace_id = %s AND strategy_id = %s\n                   AND event_type = ANY(%s)\n                   AND observed_at >= %s AND observed_at < %s\n                 ORDER BY observed_at, created_at, event_id\n                 LIMIT %s\n                \"\"\",\n                (\n                    self.context.workspace_id,\n                    strategy_id,\n                    normalized_types,\n                    start_time,\n                    end_time,\n                    limit,\n                ),\n            ).fetchall()\n        return [_event(row) for row in rows]\n\n    def entry_events_between(\n"""
    text = replace_exact(text, anchor, replacement, "repository qualification query")
    REPOSITORY.write_text(text, encoding="utf-8")


def patch_monitor() -> None:
    text = MONITOR.read_text(encoding="utf-8")
    import_old = """from .strategy_shadow_execution import observe_shadow_execution\nfrom .strategy_shadow_universe import resolve_v2_shadow_archive\nfrom .strategy_v2_management import (\n"""
    import_new = """from .strategy_shadow_execution import observe_shadow_execution\nfrom .strategy_shadow_universe import resolve_v2_shadow_archive\nfrom .strategy_v2_qualification import (\n    V2_PROSPECTIVE_START,\n    V2_QUALIFICATION_EVENT_TYPES,\n    evaluate_v2_prospective_qualification,\n    v2_profile_fingerprint,\n)\nfrom .strategy_v2_management import (\n"""
    text = replace_exact(text, import_old, import_new, "monitor qualification imports")

    helper_old = """def _key(*parts: object) -> str:\n    return hashlib.sha256(\"|\".join(str(part) for part in parts).encode(\"utf-8\")).hexdigest()\n\n\ndef _run_id(prefix: str, observed_at: datetime) -> str:\n"""
    helper_new = """def _key(*parts: object) -> str:\n    return hashlib.sha256(\"|\".join(str(part) for part in parts).encode(\"utf-8\")).hexdigest()\n\n\ndef _v2_qualification_events(\n    repository: TradingStrategyRepository,\n    strategy_id: str,\n    *,\n    now: datetime,\n) -> list[StrategyEvent]:\n    start = datetime(\n        V2_PROSPECTIVE_START.year,\n        V2_PROSPECTIVE_START.month,\n        V2_PROSPECTIVE_START.day,\n        tzinfo=timezone.utc,\n    )\n    end = now.astimezone(timezone.utc) + timedelta(seconds=1)\n    if hasattr(repository, \"events_by_types_between\"):\n        return repository.events_by_types_between(\n            strategy_id,\n            event_types=V2_QUALIFICATION_EVENT_TYPES,\n            start_time=start,\n            end_time=end,\n            limit=20_000,\n        )\n    return [\n        event\n        for event in repository.recent_events(strategy_id, 20_000)\n        if event.event_type in V2_QUALIFICATION_EVENT_TYPES\n        and start <= event.observed_at.astimezone(timezone.utc) < end\n    ]\n\n\ndef _run_id(prefix: str, observed_at: datetime) -> str:\n"""
    text = replace_exact(text, helper_old, helper_new, "monitor qualification helper")

    runtime_old = """        now_utc = datetime.now(timezone.utc)\n        now_et = now_utc.astimezone(_ET)\n        today_et = now_et.date()\n"""
    runtime_new = """        now_utc = datetime.now(timezone.utc)\n        if config.mode == \"auto_paper\" and config.config.strategy_version == \"2.0.0\":\n            qualification_events = await asyncio.to_thread(\n                _v2_qualification_events,\n                strategy_repository,\n                config.strategy_id,\n                now=now_utc,\n            )\n            qualification = await asyncio.to_thread(\n                evaluate_v2_prospective_qualification,\n                config,\n                qualification_events,\n            )\n            if not qualification.auto_paper_authorized:\n                trade_log(\n                    \"auto_trading\",\n                    \"v2_auto_paper_qualification_blocked\",\n                    run_id=self.current_run_id,\n                    strategy_id=config.strategy_id,\n                    profile_fingerprint=qualification.current_profile_fingerprint,\n                    evidence_fingerprint=qualification.evidence_fingerprint,\n                    reason_codes=qualification.reason_codes,\n                    matched_eligible_trade_count=qualification.matched_eligible_trade_count,\n                    execution_match_rate=qualification.execution_match_rate,\n                    expectancy_r=qualification.expectancy_r,\n                    one_sided_90_lcb_r=qualification.one_sided_90_lcb_r,\n                    max_drawdown_r=qualification.max_drawdown_r,\n                    execution_authority=False,\n                )\n                return\n        now_et = now_utc.astimezone(_ET)\n        today_et = now_et.date()\n"""
    text = replace_exact(text, runtime_old, runtime_new, "monitor runtime authorization")

    unavailable_old = """                        \"universe_id\": universe.universe_id,\n                        \"universe_source\": universe_source,\n                        \"signal\": result.signal.model_dump(mode=\"json\"),\n"""
    unavailable_new = """                        \"universe_id\": universe.universe_id,\n                        \"universe_source\": universe_source,\n                        \"profile_fingerprint\": (\n                            v2_profile_fingerprint(config.config)\n                            if config.config.strategy_version == \"2.0.0\"\n                            else None\n                        ),\n                        \"signal\": result.signal.model_dump(mode=\"json\"),\n"""
    text = replace_exact(text, unavailable_old, unavailable_new, "shadow unavailable fingerprint")

    observed_old = """                    \"universe_id\": universe.universe_id,\n                    \"universe_source\": universe_source,\n                    \"signal\": result.signal.model_dump(mode=\"json\"),\n"""
    observed_new = """                    \"universe_id\": universe.universe_id,\n                    \"universe_source\": universe_source,\n                    \"profile_fingerprint\": (\n                        v2_profile_fingerprint(config.config)\n                        if config.config.strategy_version == \"2.0.0\"\n                        else None\n                    ),\n                    \"signal\": result.signal.model_dump(mode=\"json\"),\n"""
    text = replace_exact(text, observed_old, observed_new, "shadow observed fingerprint")
    MONITOR.write_text(text, encoding="utf-8")


def patch_api() -> None:
    text = API.read_text(encoding="utf-8")
    text = replace_exact(
        text,
        "from datetime import date, datetime, timezone\n",
        "from datetime import date, datetime, timedelta, timezone\n",
        "api datetime import",
    )
    import_old = """from .strategy_repository import (\n    StrategyEvent,\n    StrategyProtection,\n    TradingStrategyConfigDocument,\n    TradingStrategyRepository,\n    default_strategy_repository,\n)\nfrom .trade_logging import trade_log\n"""
    import_new = """from .strategy_repository import (\n    StrategyEvent,\n    StrategyProtection,\n    TradingStrategyConfigDocument,\n    TradingStrategyRepository,\n    default_strategy_repository,\n)\nfrom .strategy_v2_qualification import (\n    V2_PROSPECTIVE_START,\n    V2_QUALIFICATION_EVENT_TYPES,\n    V2_QUALIFICATION_VERSION,\n    V2ProspectiveQualification,\n    evaluate_v2_prospective_qualification,\n)\nfrom .trade_logging import trade_log\n"""
    text = replace_exact(text, import_old, import_new, "api qualification imports")

    model_old = """class StrategyProtectionListResponse(BaseModel):\n    protections: list[StrategyProtection]\n\n\nclass StrategyEvaluationRequest(BaseModel):\n"""
    model_new = """class StrategyProtectionListResponse(BaseModel):\n    protections: list[StrategyProtection]\n\n\nclass V2QualificationReviewRequest(BaseModel):\n    model_config = ConfigDict(extra=\"forbid\")\n    review_note: str = Field(min_length=10, max_length=2_000)\n\n\nclass StrategyEvaluationRequest(BaseModel):\n"""
    text = replace_exact(text, model_old, model_new, "api review model")

    helper_old = """def _bar_coverage(bars_by_instrument: dict[str, list[MarketBar]]) -> dict[str, dict[str, object]]:\n"""
    helper_new = """def _v2_qualification_events(\n    repository: TradingStrategyRepository,\n    strategy_id: str,\n    *,\n    now: datetime | None = None,\n) -> list[StrategyEvent]:\n    observed = now or datetime.now(timezone.utc)\n    start = datetime(\n        V2_PROSPECTIVE_START.year,\n        V2_PROSPECTIVE_START.month,\n        V2_PROSPECTIVE_START.day,\n        tzinfo=timezone.utc,\n    )\n    end = observed.astimezone(timezone.utc) + timedelta(seconds=1)\n    if hasattr(repository, \"events_by_types_between\"):\n        return repository.events_by_types_between(\n            strategy_id,\n            event_types=V2_QUALIFICATION_EVENT_TYPES,\n            start_time=start,\n            end_time=end,\n            limit=20_000,\n        )\n    return [\n        event\n        for event in repository.recent_events(strategy_id, 20_000)\n        if event.event_type in V2_QUALIFICATION_EVENT_TYPES\n        and start <= event.observed_at.astimezone(timezone.utc) < end\n    ]\n\n\ndef _require_v2_auto_paper_authorized(\n    document: TradingStrategyConfigDocument,\n    repository: TradingStrategyRepository,\n) -> None:\n    if document.mode != \"auto_paper\" or document.config.strategy_version != \"2.0.0\":\n        return\n    qualification = evaluate_v2_prospective_qualification(\n        document,\n        _v2_qualification_events(repository, document.strategy_id),\n    )\n    if not qualification.auto_paper_authorized:\n        raise ValueError(\"v2_auto_paper_requires_reviewed_prospective_qualification\")\n\n\ndef _bar_coverage(bars_by_instrument: dict[str, list[MarketBar]]) -> dict[str, dict[str, object]]:\n"""
    text = replace_exact(text, helper_old, helper_new, "api qualification helpers")

    create_old = """    @router.post(\"\", response_model=TradingStrategyConfigDocument, status_code=201)\n    async def create_strategy(document: TradingStrategyConfigDocument):\n        try:\n            return await asyncio.to_thread(repository_factory().create_config, document)\n        except ValueError as exc:\n            raise HTTPException(status_code=422, detail=str(exc)) from exc\n"""
    create_new = """    @router.post(\"\", response_model=TradingStrategyConfigDocument, status_code=201)\n    async def create_strategy(document: TradingStrategyConfigDocument):\n        try:\n            repository = repository_factory()\n            _require_v2_auto_paper_authorized(document, repository)\n            return await asyncio.to_thread(repository.create_config, document)\n        except ValueError as exc:\n            raise HTTPException(status_code=422, detail=str(exc)) from exc\n"""
    text = replace_exact(text, create_old, create_new, "api create authorization")

    routes_anchor = """    @router.get(\"/{strategy_id}\", response_model=TradingStrategyConfigDocument)\n    async def get_strategy(strategy_id: str):\n"""
    routes_insert = """    @router.get(\"/{strategy_id}/v2/qualification\", response_model=V2ProspectiveQualification)\n    async def get_v2_qualification(strategy_id: str) -> V2ProspectiveQualification:\n        try:\n            repository = repository_factory()\n            strategy = await asyncio.to_thread(repository.get_config, strategy_id)\n            if strategy.config.strategy_version != \"2.0.0\":\n                raise ValueError(\"v2_qualification_requires_strategy_version_2_0_0\")\n            events = await asyncio.to_thread(_v2_qualification_events, repository, strategy_id)\n            return await asyncio.to_thread(evaluate_v2_prospective_qualification, strategy, events)\n        except ValueError as exc:\n            status = 404 if str(exc) == \"strategy_config_not_found\" else 422\n            raise HTTPException(status_code=status, detail=str(exc)) from exc\n\n    @router.post(\"/{strategy_id}/v2/qualification/review\", response_model=V2ProspectiveQualification)\n    async def review_v2_qualification(\n        strategy_id: str,\n        request: V2QualificationReviewRequest,\n    ) -> V2ProspectiveQualification:\n        try:\n            note = \" \".join(request.review_note.split()).strip()\n            if len(note) < 10:\n                raise ValueError(\"v2_qualification_review_note_too_short\")\n            repository = repository_factory()\n            strategy = await asyncio.to_thread(repository.get_config, strategy_id)\n            if strategy.config.strategy_version != \"2.0.0\":\n                raise ValueError(\"v2_qualification_requires_strategy_version_2_0_0\")\n            events = await asyncio.to_thread(_v2_qualification_events, repository, strategy_id)\n            qualification = await asyncio.to_thread(\n                evaluate_v2_prospective_qualification, strategy, events\n            )\n            if qualification.auto_paper_authorized:\n                return qualification\n            if not qualification.qualified:\n                raise ValueError(\"v2_prospective_qualification_not_met\")\n            observed_at = datetime.now(timezone.utc)\n            raw = \"|\".join((\n                \"v2-promotion-review\",\n                strategy_id,\n                qualification.current_profile_fingerprint,\n                qualification.evidence_fingerprint,\n            ))\n            idem = hashlib.sha256(raw.encode(\"utf-8\")).hexdigest()\n            review_event = StrategyEvent(\n                strategy_id=strategy_id,\n                event_id=idem[:32],\n                instrument_id=f\"strategy:{strategy_id}\",\n                event_type=\"v2_promotion_review\",\n                state=\"qualification_reviewed\",\n                reason_code=\"V2_PROMOTION_REVIEW_APPROVED\",\n                observed_at=observed_at,\n                idempotency_key=idem,\n                payload={\n                    \"qualification_version\": V2_QUALIFICATION_VERSION,\n                    \"profile_fingerprint\": qualification.current_profile_fingerprint,\n                    \"evidence_fingerprint\": qualification.evidence_fingerprint,\n                    \"approved\": True,\n                    \"review_note\": note,\n                    \"execution_authority\": False,\n                },\n            )\n            await asyncio.to_thread(repository.append_event, review_event)\n            return await asyncio.to_thread(\n                evaluate_v2_prospective_qualification,\n                strategy,\n                [*events, review_event],\n            )\n        except ValueError as exc:\n            status = 404 if str(exc) == \"strategy_config_not_found\" else 422\n            raise HTTPException(status_code=status, detail=str(exc)) from exc\n\n    @router.get(\"/{strategy_id}\", response_model=TradingStrategyConfigDocument)\n    async def get_strategy(strategy_id: str):\n"""
    text = replace_exact(text, routes_anchor, routes_insert, "api qualification routes")

    update_old = """    @router.put(\"/{strategy_id}\", response_model=TradingStrategyConfigDocument)\n    async def update_strategy(strategy_id: str, document: TradingStrategyConfigDocument, if_match: int = Header(alias=\"If-Match\", ge=1)):\n        try:\n            return await asyncio.to_thread(\n                repository_factory().update_config,\n                strategy_id,\n                document,\n                expected_revision=if_match,\n            )\n"""
    update_new = """    @router.put(\"/{strategy_id}\", response_model=TradingStrategyConfigDocument)\n    async def update_strategy(strategy_id: str, document: TradingStrategyConfigDocument, if_match: int = Header(alias=\"If-Match\", ge=1)):\n        try:\n            repository = repository_factory()\n            _require_v2_auto_paper_authorized(document, repository)\n            return await asyncio.to_thread(\n                repository.update_config,\n                strategy_id,\n                document,\n                expected_revision=if_match,\n            )\n"""
    text = replace_exact(text, update_old, update_new, "api update authorization")
    API.write_text(text, encoding="utf-8")


def patch_gateway() -> None:
    text = GATEWAY.read_text(encoding="utf-8")
    import_old = """    from app.trading.strategy_universe_archive_monitor import register_trading_strategy_universe_archive_monitor\n\n    gateway.include_router(create_trading_router())\n"""
    import_new = """    from app.trading.strategy_universe_archive_monitor import register_trading_strategy_universe_archive_monitor\n    from app.trading.strategy_v2_qualification_monitor import register_trading_strategy_v2_qualification_monitor\n\n    gateway.include_router(create_trading_router())\n"""
    text = replace_exact(text, import_old, import_new, "gateway qualification import")
    register_old = """    register_trading_strategy_universe_archive_monitor(gateway)\n    register_trading_strategy_research_monitor(gateway)\n"""
    register_new = """    register_trading_strategy_universe_archive_monitor(gateway)\n    register_trading_strategy_v2_qualification_monitor(gateway)\n    register_trading_strategy_research_monitor(gateway)\n"""
    text = replace_exact(text, register_old, register_new, "gateway qualification monitor")
    GATEWAY.write_text(text, encoding="utf-8")


def main() -> int:
    patch_repository()
    patch_monitor()
    patch_api()
    patch_gateway()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
