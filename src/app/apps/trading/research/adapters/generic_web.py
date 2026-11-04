from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from ..contracts import IssuerIdentity, TradingEvidence, fingerprint
from ..runtime_policy import assert_external_web_search_allowed
from ..source_authority import source_authority_tier
from .base import AdapterExecutionResult
from typing import Any, cast


_RESEARCH_DISABLED = "web_unavailable:research_feature_disabled"


def _research_enabled() -> bool:
    from app.runtime.config import get_runtime_config
    from app.runtime.feature_catalog import enabled_feature_ids

    return "research" in enabled_feature_ids(get_runtime_config())


class GenericWebAdapter:
    """Reads the web through the research feature. Without it (a trading-only install leaves its code out) there is
    no web to read: searches and extractions return no evidence and say why."""

    name = "generic_web"

    def __init__(self, search_service=None, extractor_factory=None) -> None:
        research_enabled = (search_service is None or extractor_factory is None) and _research_enabled()
        if search_service is None and research_enabled:
            from app.platform.research.contracts import (
                ProviderFallbackSearchClient,
                QuickSearchService,
                load_research_runtime_settings,
            )

            settings = load_research_runtime_settings()

            def client_factory(timeout_seconds: float):
                return ProviderFallbackSearchClient(
                    providers=settings.effective_provider_chain,
                    timeout_seconds=timeout_seconds,
                )

            search_service = QuickSearchService(
                client_factory=client_factory,
                research_policy=settings.policy,
                max_extracts=min(2, settings.max_extracts),
            )
        if extractor_factory is None and research_enabled:
            from app.platform.research.contracts import ReadablePageExtractor
            extractor_factory = ReadablePageExtractor
        self.search_service = search_service
        self.extractor_factory = extractor_factory

    def find(self, identity: IssuerIdentity, *, query: str | None = None, limit: int = 8) -> AdapterExecutionResult:
        # Generic/company-IR discovery ultimately consumes the configured web-search
        # provider (for example Brave). Backtests install a context-local hard guard
        # so a future Hermes integration cannot silently spend live search quota.
        assert_external_web_search_allowed()
        if self.search_service is None:
            return AdapterExecutionResult(detail=_RESEARCH_DISABLED, warnings=(_RESEARCH_DISABLED,))
        q = query or f"{identity.symbol} {identity.legal_name or ''} latest news filing financing".strip()
        execution = self.search_service.search(q, limit)
        captured = datetime.now(timezone.utc)
        evidence: list[TradingEvidence] = []
        for item in execution.items:
            locator = item.url or ""
            content = " ".join(str(item.content or "").split()).strip()
            if not content:
                continue
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            tier = source_authority_tier("web", locator)
            fp = fingerprint({"instrument_id": identity.instrument_id, "locator": locator, "content_hash": content_hash})
            evidence.append(TradingEvidence(
                evidence_id=f"web-{hashlib.sha256((locator + content_hash).encode()).hexdigest()[:24]}",
                instrument_id=identity.instrument_id,
                issuer_identity_id=identity.identity_id,
                evidence_type="web_search_result",
                source_type="web",
                source_locator=locator or f"search:{q}",
                source_authority_tier=cast(Any, tier),
                captured_at=captured,
                title=item.title,
                content=content,
                content_hash=content_hash,
                extraction_status="snippet",
                metadata={"provider": item.metadata.get("provider") if item.metadata else None, "query": q},
                immutable_fingerprint=fp,
            ))
        diagnostics = getattr(execution, "diagnostics", {}) or {}
        provider = str(diagnostics.get("provider") or "unknown")
        status = str(diagnostics.get("status") or "unknown")
        results = diagnostics.get("results", len(execution.items))
        attempts = ",".join(str(item) for item in diagnostics.get("provider_attempts", ()))
        failures = ",".join(
            f"{provider_name}:{message}"
            for provider_name, message in (diagnostics.get("provider_failures") or {}).items()
        )
        detail = (
            f"web_results:{len(evidence)} provider:{provider} status:{status} "
            f"items:{results} attempts:{attempts or 'none'} failures:{failures or 'none'}"
        )
        return AdapterExecutionResult(evidence=tuple(evidence), detail=detail)

    def extract(self, identity: IssuerIdentity, *, locator: str) -> AdapterExecutionResult:
        if self.extractor_factory is None:
            return AdapterExecutionResult(detail=_RESEARCH_DISABLED, warnings=(_RESEARCH_DISABLED,))
        page = self.extractor_factory().extract(locator)
        content = " ".join(page.text.split()).strip()
        if not content:
            raise ValueError("web_extraction_empty")
        captured = datetime.now(timezone.utc)
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        tier = source_authority_tier("web", locator)
        fp = fingerprint({"instrument_id": identity.instrument_id, "locator": locator, "content_hash": content_hash})
        return AdapterExecutionResult(evidence=(TradingEvidence(
            evidence_id=f"webx-{hashlib.sha256((locator + content_hash).encode()).hexdigest()[:24]}",
            instrument_id=identity.instrument_id,
            issuer_identity_id=identity.identity_id,
            evidence_type="web_extracted_page",
            source_type="web",
            source_locator=locator,
            source_authority_tier=cast(Any, tier),
            captured_at=captured,
            title=page.title,
            content=content[:250_000],
            content_hash=content_hash,
            extraction_status="completed",
            metadata={"extractor_version": page.extractor_version},
            immutable_fingerprint=fp,
        ),), detail="web_page_extracted")
