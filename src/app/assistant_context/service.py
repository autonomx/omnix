"""Context assembly for enriched assistant turns."""
from __future__ import annotations

import time
from typing import Callable

from .models import AssistantContextBuildResult, AssistantContextChatRequest
from .vision import DesktopVisionClient
from .web_search import WebSearchClient, should_search_automatically


class AssistantContextService:
    def __init__(
        self,
        *,
        web_search_factory: Callable[[], WebSearchClient] = WebSearchClient,
        desktop_vision_factory: Callable[[], DesktopVisionClient] = DesktopVisionClient,
    ) -> None:
        self.web_search_factory = web_search_factory
        self.desktop_vision_factory = desktop_vision_factory

    def build(self, request: AssistantContextChatRequest) -> AssistantContextBuildResult:
        items = []
        current_image = request.desktop_current_image_data_url or request.desktop_image_data_url
        desktop_requested = bool(
            current_image
            or request.desktop_history_image_data_url
            or request.desktop_combined_image_data_url
        )
        diagnostics: dict[str, object] = {
            "web_search_mode": request.web_search_mode,
            "web_search_requested": request.web_search_requested,
            "desktop_requested": desktop_requested,
            "desktop_capture_mode": request.desktop_capture_mode,
            "desktop_history_frames": len(request.desktop_history_timestamps),
        }

        search_needed = request.web_search_mode == "automatic" and should_search_automatically(request.content)
        search_needed = search_needed or (request.web_search_mode == "manual" and request.web_search_requested)
        if search_needed:
            started = time.perf_counter()
            try:
                web_items = self.web_search_factory().search(request.content, request.web_search_max_results)
                items.extend(web_items)
                diagnostics["web_search_status"] = "completed" if web_items else "empty"
                diagnostics["web_search_results"] = len(web_items)
            except Exception as exc:
                diagnostics["web_search_status"] = "failed"
                diagnostics["web_search_error"] = f"{type(exc).__name__}: {exc}"
            diagnostics["web_search_ms"] = round((time.perf_counter() - started) * 1000)
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
