"""Context assembly for enriched assistant turns."""
from __future__ import annotations

import time
from typing import Callable

from app.research.evidence import prepare_evidence_context_items
from app.research.quick_search import QuickSearchService

from .models import AssistantContextBuildResult, AssistantContextChatRequest, AssistantContextItem
from .vision import DesktopVisionClient
from .web_search import WebSearchClient, should_search_automatically


class AssistantContextService:
    def __init__(
        self,
        *,
        web_search_factory: Callable[..., WebSearchClient] = WebSearchClient,
        quick_search_factory: Callable[[], QuickSearchService] | None = None,
        desktop_vision_factory: Callable[[], DesktopVisionClient] = DesktopVisionClient,
    ) -> None:
        self.web_search_factory = web_search_factory
        self.quick_search_factory = quick_search_factory or self._default_quick_search_factory
        self.desktop_vision_factory = desktop_vision_factory

    def _default_quick_search_factory(self) -> QuickSearchService:
        def create_client(timeout_seconds: float) -> WebSearchClient:
            try:
                return self.web_search_factory(timeout_seconds=timeout_seconds)
            except TypeError:
                return self.web_search_factory()

        return QuickSearchService(client_factory=create_client)

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
            "legacy_web_search_mode": request.legacy_web_search_mode,
            "web_search_requested": request.web_search_requested,
            "desktop_requested": desktop_requested,
            "desktop_capture_mode": request.desktop_capture_mode,
            "desktop_history_frames": len(request.desktop_history_timestamps),
        }

        search_needed = request.web_research_mode == "quick"
        if request.legacy_web_search_mode == "automatic":
            search_needed = should_search_automatically(request.content)
        elif request.legacy_web_search_mode == "manual":
            search_needed = request.web_search_requested

        if search_needed:
            execution = self.quick_search_factory().search(
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
            diagnostics["desktop_ms"] = round((time.perf_counter() - started) * 1000)
        else:
            diagnostics["desktop_status"] = "skipped"

        return AssistantContextBuildResult(items=items, diagnostics=diagnostics)


def default_assistant_context_service() -> AssistantContextService:
    return AssistantContextService()
