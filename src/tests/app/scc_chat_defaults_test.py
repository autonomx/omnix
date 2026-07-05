from app.chat import CreateChatSessionRequest
from app.chat.defaults import resolve_new_session_request
from app.platform.settings_profile_models import SettingsProfile


def _profile() -> SettingsProfile:
    return SettingsProfile.model_validate(
        {
            "global": {
                "providers": {"llm": "central-llm"},
                "models": {"chat": "central-chat-model"},
            }
        }
    )


def test_new_chat_session_inherits_central_provider_and_model() -> None:
    resolved = resolve_new_session_request(CreateChatSessionRequest(title="Fresh chat"), _profile())

    assert resolved.provider_id == "central-llm"
    assert resolved.model_id == "central-chat-model"
    assert resolved.title == "Fresh chat"


def test_explicit_chat_session_values_override_central_defaults() -> None:
    resolved = resolve_new_session_request(
        CreateChatSessionRequest(provider_id="session-llm", model_id="session-model"),
        _profile(),
    )

    assert resolved.provider_id == "session-llm"
    assert resolved.model_id == "session-model"


def test_resolver_does_not_mutate_original_request() -> None:
    request = CreateChatSessionRequest()

    resolve_new_session_request(request, _profile())

    assert request.provider_id is None
    assert request.model_id is None
