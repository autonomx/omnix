from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .core import AssistantRequest, AssistantResult
from .hermes_client import HermesSidecarClient
from .hermes_status import hermes_runtime_config
from .house_plan import infer_house_plan
from .mode_apply import apply_mode_result


@dataclass
class ModeChatRequest:
    content: str
    session_id: str = "default"
    domain: str = "chat"
    dry_run: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModeChatResponse:
    ok: bool
    mode: str
    backend: str
    result: dict[str, Any]
    error: str | None = None


def detect_mode_domain(message: str) -> str:
    text = message.lower()
    if any(token in text for token in ("light", "brightness", "thermostat", "house status")):
        return "house"
    if "podcast" in text:
        return "podcast"
    if any(token in text for token in ("rpg", "quest", "npc", "scene", "bran")):
        return "rpg"
    return "chat"


def local_mode_plan(request: AssistantRequest) -> AssistantResult:
    if request.domain == "house":
        return apply_mode_result(infer_house_plan(request), dry_run=request.dry_run)
    return AssistantResult(success=True, response="Agent mode is ready. No tool plan is needed for this message.", domain=request.domain)


def plan_mode_chat(request: ModeChatRequest) -> ModeChatResponse:
    domain = request.domain if request.domain != "chat" else detect_mode_domain(request.content)
    assistant_request = AssistantRequest(
        message=request.content,
        session_id=request.session_id,
        domain=domain,
        dry_run=request.dry_run,
        metadata=request.metadata,
    )
    config = hermes_runtime_config()
    if config.enabled:
        try:
            result = HermesSidecarClient(base_url=config.base_url, timeout=config.timeout_seconds).plan(assistant_request)
            result = apply_mode_result(result, dry_run=request.dry_run)
            return ModeChatResponse(ok=result.success, mode="agent", backend="hermes", result=asdict(result))
        except Exception as exc:
            result = local_mode_plan(assistant_request)
            return ModeChatResponse(ok=result.success, mode="agent", backend="local_fallback", result=asdict(result), error=str(exc))
    result = local_mode_plan(assistant_request)
    return ModeChatResponse(ok=result.success, mode="agent", backend="local", result=asdict(result))
