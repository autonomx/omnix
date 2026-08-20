"""Context assembly for enriched assistant turns."""
from __future__ import annotations

import time
from typing import Callable

from app.research.evidence import prepare_evidence_context_items
from app.research.extraction import ReadablePageExtractor
from app.research.policy import ResearchPolicy, research_policy_from_env
from app.research.provider_chain import ProviderFallbackSearchClient, normalize_provider_chain
from app.research.quick_search import QuickSearchService

from .models import AssistantContextBuildResult, AssistantContextChatRequest, AssistantContextItem
from .vision import DesktopVisionClient
from .web_search import WebSearchClient


class AssistantContextService:
    def __init__(
        self,
        *,
        web_search_factory: Callable[..., WebSearchClient] = WebSearchClient,
        quick_search_factory: Callable[[], QuickSearchService] | None = None,
        desktop_vision_factory: Callable[[], DesktopVisionClient] = DesktopVisionClient,
    ) -> None:
        self.web_search_factory = web_search_factory
        self.quick_search_factory = quick_search_factory
        self.desktop_vision_factory = desktop_vision_factory

    def _quick_search_for(self, request: AssistantContextChatRequest) -> QuickSearchService:
        if self.quick_search_factory is not None:
            return self.quick_search_factory()
        policy = (
            ResearchPolicy(**request.internal_research_policy)
            if request.internal_research_policy
            else research_policy_from_env()
        )
        provider_chain = normalize_provider_chain(
            request.internal_research_provider,
            request.internal_research_provider_chain,
        )

        def create_client(timeout_seconds: float):
            if len(provider_chain) > 1:
                return ProviderFallbackSearchClient(
                    providers=provider_chain,
                    timeout_seconds=timeout_seconds,
                    client_factory=self.web_search_factory,
                )
            try:
                return self.web_search_factory(
                    provider=provider_chain[0],
                    timeout_seconds=timeout_seconds,
                )
            except TypeError:
                try:
                    return self.web_search_factory(timeout_seconds=timeout_seconds)
                except TypeError:
                    return self.web_search_factory()

        return QuickSearchService(
            client_factory=create_client,
            research_policy=policy,
            extractor_factory=lambda: ReadablePageExtractor(research_policy=policy),
        )

    def build(self, request: AssistantContextChatRequest) -> AssistantContextBuildResult:
        items: list[AssistantContextItem] = []
        current_image = request.desktop_current_image_data_url or request.desktop_image_data_url
        desktop_requested = bool(
            current_image
            or request.desktop_history_image_data_url
            or request.desktop_combined_image_data_url
        )
        diagnostics: dict[str, object] = {
            "web_research_mode": request.web_research_mode,
            "research_provider": request.internal_research_provider,
            "research_provider_chain": request.internal_research_provider_chain,
            "research_compatibility_warnings": request.internal_research_warnings,
            "desktop_requested": desktop_requested,
            "desktop_capture_mode": request.desktop_capture_mode,
            "desktop_history_frames": len(request.desktop_history_timestamps),
            "live_repair_requested": request.live_repair is not None,
        }

        if request.live_repair is not None:
            repair = request.live_repair
            items.append(
                AssistantContextItem(
                    source_id="live_repair",
                    title="Live conversation repair guidance",
                    content=(
                        "Trusted conversational-control guidance for this response: "
                        f"{repair.instruction.strip()} "
                        "Keep the visible user words authoritative, apply the repair briefly, and then continue naturally."
                    ),
                    metadata={
                        "kind": repair.kind,
                        "source_reason": repair.source_reason,
                        "confidence": repair.confidence,
                        "trusted_control_context": True,
                    },
                )
            )
            diagnostics["live_repair_kind"] = repair.kind
            diagnostics["live_repair_source_reason"] = repair.source_reason
            diagnostics["live_repair_confidence"] = repair.confidence

        if request.web_research_mode == "quick":
            execution = self._quick_search_for(request).search(
                request.content,
                request.web_search_max_results,
                identity=request.internal_research_identity or "anonymous",
            )
            prepared = prepare_evidence_context_items(
                [item.model_dump(mode="json") for item in execution.items]
            )
            items.extend(AssistantContextItem.model_validate(item) for item in prepared)
            for key, value in execution.diagnostics.items():
                diagnostics[f"web_search_{key}"] = value
            diagnostics["web_search_warnings"] = execution.warnings
        elif request.web_research_mode == "deep":
            diagnostics["web_search_status"] = "deferred_to_deep_research"
        else:
            diagnostics["web_search_status"] = "skipped"

        if desktop_requested:
            started = time.perf_counter()
            try:
                if not current_image:
                    raise ValueError("desktop temporal context requires a current image")
                observation = self.desktop_vision_factory().describe(
                    current_image,
                    request.desktop_question or request.content,
                    request.vision_model_id or request.model_id,
                    history_image_data_url=request.desktop_history_image_data_url,
                    combined_image_data_url=request.desktop_combined_image_data_url,
                    history_timestamps=request.desktop_history_timestamps,
                    capture_mode=request.desktop_capture_mode,
                )
                items.append(observation)
                diagnostics["desktop_status"] = "completed"
                diagnostics["desktop_model"] = observation.metadata.get("model")
                diagnostics["desktop_fallback_mode"] = observation.metadata.get("fallback_mode")
                diagnostics["desktop_image_count"] = observation.metadata.get("image_count")
                diagnostics["desktop_fallback_errors"] = observation.metadata.get("fallback_errors", [])
            except Exception as exc:
                diagnostics["desktop_status"] = "failed"
                diagnostics["desktop_error"] = f"{type(exc).__name__}: {exc}"
                items.append(_desktop_failure_item(str(diagnostics["desktop_error"])))
            diagnostics["desktop_ms"] = round((time.perf_counter() - started) * 1000)
        else:
            diagnostics["desktop_status"] = "skipped"

        return AssistantContextBuildResult(items=items, diagnostics=diagnostics)


def default_assistant_context_service() -> AssistantContextService:
    return AssistantContextService()


def _desktop_failure_item(error: str) -> AssistantContextItem:
    return AssistantContextItem(
        source_id="desktop_vision",
        title="Desktop sharing status",
        content=(
            "The user shared their desktop for this turn, but Omnix could not inspect the image. "
            f"Vision resolver error: {error}. "
            "Do not claim to see the screen. Tell the user desktop sharing is active but a "
            "vision-capable model or vision provider configuration is needed."
        ),
        metadata={"status": "failed", "error": error},
    )
