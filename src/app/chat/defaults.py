"""Central default resolution for newly created chat sessions."""
from __future__ import annotations

from app.platform.settings_profile_models import SettingsProfile

from .models import CreateChatSessionRequest


def resolve_new_session_request(
    request: CreateChatSessionRequest,
    profile: SettingsProfile,
) -> CreateChatSessionRequest:
    """Apply central defaults without overriding explicit session choices."""
    providers = profile.global_settings.providers
    models = profile.global_settings.models
    return request.model_copy(
        update={
            "provider_id": request.provider_id or providers.llm or None,
            "model_id": request.model_id or models.chat or None,
        }
    )
