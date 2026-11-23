"""A picture the person shows the call through their front camera (companion roadmap 4.2).

Owner decision 2026-11-15: only a picture's description is kept, never the image. A live voice turn carries at most
one ``camera_image`` (``SendChatMessageRequest.camera_image``, which is never serialised into the job or the
message). Before the reply, the configured vision model describes it for the person's words, with the same remote
consent the desktop companion needs; the description joins the turn as untrusted observed context (source
``camera``), and the user message records ``camera_snapshot: {description, described_at}``. The image itself is
dropped once the vision call returns.

The stream says a fixed "Let me look." before the vision call, so the call is never silent while it waits. A
failure or a timeout is said in a fixed line, and the reply goes on without the picture: a turn is never blocked by
the camera.
"""
from __future__ import annotations

from app.conversation.contracts import is_live_voice_message
import concurrent.futures
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from app.config.env import environment
from app.prompts import prompt_template

logger = logging.getLogger(__name__)

CAMERA_SOURCE_ID = "camera"
CAMERA_FILLER = "Let me look."
CAMERA_UNSEEN_LINE = "Sorry, I couldn't see it."
# A 1024 px JPEG from the web is about 100-400 KB; its data URL a third larger.
CAMERA_IMAGE_MAX_CHARS = 3_000_000
DESCRIBE_TIMEOUT_SECONDS = 8.0
_DESCRIPTION_CHARS = 1500

CAMERA_QUESTION_TEMPLATE = prompt_template(
    "chat.live_call_camera.question", "1",
    (
        "This is a photo from the front camera of a person on a voice call. They are showing it to the assistant "
        "they are talking to, and said: \"{words}\"\n"
        "Describe what is visible that helps answer them, in a few plain sentences. Say what you are unsure of. "
        "Do not identify people by name, and do not read out private details such as card or account numbers."
    ),
)

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="live-call-camera")


CameraReason = Literal["ready", "vision_not_configured", "remote_vision_not_allowed", "vision_unavailable"]


@dataclass(frozen=True)
class CameraVision:
    """Whether a call may offer the camera: vision configured, and local or remote with consent."""

    available: bool
    remote: bool
    reason: CameraReason


@dataclass(frozen=True)
class CameraLook:
    """What came of one picture: the context item for the turn, what was said before the reply, and the snapshot
    the user message keeps (None when nothing was seen)."""

    context_item: dict[str, Any]
    spoken: str
    snapshot: dict[str, str] | None
    outcome: str


def _assistant_settings() -> dict[str, Any]:
    try:
        from app.settings.access import load_settings

        settings = load_settings()
    except Exception:  # noqa: BLE001 - no settings: nothing is allowed that needs consent
        logger.warning("live call camera: settings could not be read", exc_info=True)
        return {}
    profile = settings.get("settings_control_center") if isinstance(settings, dict) else None
    assistant = profile.get("assistant") if isinstance(profile, dict) else None
    return assistant if isinstance(assistant, dict) else {}


def _vision_model(assistant: dict[str, Any]) -> str:
    return str(
        assistant.get("desktopCompanionVisionModelId") or assistant.get("desktop_companion_vision_model_id") or ""
    ).strip()


def _remote_allowed(assistant: dict[str, Any]) -> bool:
    value = assistant.get("desktopCompanionRemoteVisionAllowed", assistant.get("desktop_companion_remote_vision_allowed"))
    return value is True


def _default_client() -> Any:
    from app.providers.desktop_vision import default_desktop_vision_client

    return default_desktop_vision_client()


def camera_vision(
    *,
    client_factory: Callable[[], Any] | None = None,
    assistant_settings: Callable[[], dict[str, Any]] | None = None,
) -> CameraVision:
    """Whether the call may offer Show, and why not. Nothing is sent to a model here."""
    client_factory = client_factory or _default_client
    assistant_settings = assistant_settings or _assistant_settings
    from app.providers.desktop_vision import (
        ProviderVisionClient,
        is_provider_vision_model_ref,
        is_remote_vision_endpoint,
    )

    assistant = assistant_settings()
    try:
        client = client_factory()
    except Exception:  # noqa: BLE001 - not offered, not broken
        logger.warning("live call camera: vision client could not be built", exc_info=True)
        return CameraVision(False, False, "vision_unavailable")
    configured = (
        # Codex or the Claude CLI, or the chat's own local model: no vision model needs setting.
        isinstance(client, ProviderVisionClient)
        or getattr(client, "follows_chat", False) is True
        or bool(_vision_model(assistant))
        or any(environment().get(name, "").strip() for name in ("OMNIX_VISION_BASE_URL", "OMNIX_VISION_MODEL",
                                                             "OMNIX_VISION_PROVIDER"))
    )
    if not configured:
        return CameraVision(False, False, "vision_not_configured")
    # The picture goes where ``describe`` sends it: a Codex or Claude model id goes through that provider's CLI even
    # from a local client (review 2026-11-22: a local endpoint with such a model id sent it without consent).
    remote = (is_remote_vision_endpoint(str(getattr(client, "base_url", "") or ""))
              or is_provider_vision_model_ref(_vision_model(assistant)))
    if remote and not _remote_allowed(assistant):
        return CameraVision(False, True, "remote_vision_not_allowed")
    return CameraVision(True, remote, "ready")


def record_camera_snapshot(chat_store: Any, session_id: str, user_message: Any, snapshot: dict[str, str]) -> None:
    """Keep the picture's description on the person's message; a store that cannot is skipped, never fatal."""
    message_id = str(getattr(user_message, "id", "") or "")
    update = getattr(chat_store, "update_user_message_metadata", None) or getattr(
        chat_store, "update_message_metadata", None
    )
    if not (session_id and message_id and callable(update)):
        return
    try:
        update(session_id=session_id, message_id=message_id, metadata={"camera_snapshot": snapshot})
    except Exception:  # noqa: BLE001 - the reply still has the description
        logger.warning("live call camera: the snapshot description could not be saved", exc_info=True)


class CameraTurn:
    """The events a camera turn streams before its reply, and the options its reply then takes.

    Iterate it for the filler (and the failure line); afterwards ``options`` holds the context item and the spoken
    prefix for ``stream_chat_turn``. A user turn that is not a live voice turn gets nothing: the camera belongs to
    the call.
    """

    def __init__(
        self, chat_store: Any, session_id: str, user_message: Any, image_data_url: str, **look_options: Any,
    ) -> None:
        self._chat_store = chat_store
        self._session_id = session_id
        self._user_message = user_message
        self._image: str | None = image_data_url
        self._look_options = look_options
        self.options: dict[str, Any] = {}
        self.look: CameraLook | None = None

    def __iter__(self) -> Iterator[dict[str, Any]]:
        image, self._image = self._image, None
        live_voice = getattr(self._chat_store, "live_voice_chat_port", None)
        if not image or live_voice is None or not is_live_voice_message(self._user_message):
            return
        yield {"type": "text_chunk", "text": CAMERA_FILLER}
        look = look_at_camera_image(image, str(getattr(self._user_message, "content", "") or ""),
                                    **self._look_options)
        del image  # the picture is not kept past the vision call
        self.look = look
        if look.snapshot is None:
            yield {"type": "text_chunk", "text": CAMERA_UNSEEN_LINE}
        else:
            record_camera_snapshot(self._chat_store, self._session_id, self._user_message, look.snapshot)
        self.options = {"context_items": [look.context_item], "spoken_prefix": look.spoken}


def _unseen(reason: str) -> CameraLook:
    item = {
        "source_id": CAMERA_SOURCE_ID,
        "title": "The person's camera",
        "content": (
            "The person just showed you something through their camera, but it could not be seen "
            f"({reason}). You already told them you couldn't see it. Nothing about the picture is known."
        ),
    }
    return CameraLook(item, f"{CAMERA_FILLER} {CAMERA_UNSEEN_LINE}", None, reason)


def look_at_camera_image(
    image_data_url: str,
    words: str,
    *,
    client_factory: Callable[[], Any] | None = None,
    assistant_settings: Callable[[], dict[str, Any]] | None = None,
    timeout_seconds: float = DESCRIBE_TIMEOUT_SECONDS,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> CameraLook:
    """Describe one camera picture for the person's words, within the timeout; never raises."""
    client_factory = client_factory or _default_client
    assistant_settings = assistant_settings or _assistant_settings
    status = camera_vision(client_factory=client_factory, assistant_settings=assistant_settings)
    if not status.available:
        return _unseen(status.reason)
    assistant = assistant_settings()
    question = CAMERA_QUESTION_TEMPLATE.format(words=" ".join(str(words or "").split())[:400])
    try:
        client = client_factory()
        future = _executor.submit(client.describe, image_data_url, question, _vision_model(assistant) or None)
        item = future.result(timeout=timeout_seconds)
    except concurrent.futures.TimeoutError:
        logger.warning("live call camera: vision took longer than %.1f s", timeout_seconds)
        return _unseen("it took too long")
    except Exception:  # noqa: BLE001 - the reply says it could not see it
        logger.warning("live call camera: vision failed", exc_info=True)
        return _unseen("the picture could not be read")
    description = " ".join(str(getattr(item, "content", "") or "").split())[:_DESCRIPTION_CHARS]
    if not description:
        return _unseen("nothing came back")
    context_item = {
        "source_id": CAMERA_SOURCE_ID,
        "title": "What the person's camera shows (a vision model's description, not the image)",
        "content": description,
    }
    snapshot = {"description": description, "described_at": now().isoformat()}
    return CameraLook(context_item, CAMERA_FILLER, snapshot, "seen")


__all__ = [
    "CAMERA_FILLER", "CAMERA_IMAGE_MAX_CHARS", "CAMERA_QUESTION_TEMPLATE", "CAMERA_SOURCE_ID", "CAMERA_UNSEEN_LINE",
    "CameraLook", "CameraVision", "DESCRIBE_TIMEOUT_SECONDS", "CameraTurn", "camera_vision", "look_at_camera_image",
    "record_camera_snapshot",
]
