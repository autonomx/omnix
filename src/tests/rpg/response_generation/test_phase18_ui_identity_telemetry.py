from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_WEB_ROOT = _REPO_ROOT / "src" / "apps" / "web"


def test_turn_ui_store_never_deduplicates_by_speaker_and_text() -> None:
    source = (
        _WEB_ROOT
        / "src"
        / "features"
        / "rpg"
        / "rpgTurnUiStore.ts"
    ).read_text(encoding="utf-8")

    assert "`${message.speaker}\\0${message.text}`" not in source
    assert "`${entry.speaker}\\0${entry.text}`" not in source
    assert "interactionId" in source
    assert "storyMessageIdentity" in source
    assert "id: `${interactionId}:message:${index}`" in source


def test_story_scene_uses_identity_keys_and_records_visible_commit() -> None:
    source = (
        _WEB_ROOT
        / "src"
        / "features"
        / "rpg"
        / "RpgStoryScene.tsx"
    ).read_text(encoding="utf-8")

    assert "key={storyMessageIdentity(message, index)}" in source
    assert "message.speaker}:${message.text" not in source
    assert "markRpgTurnReactCommitted" in source
    assert "markRpgTurnVisible" in source
    assert "rpg-turn-diagnostics" in source


def test_client_records_request_headers_body_parse_store_commit_and_visible() -> None:
    source = (
        _WEB_ROOT
        / "src"
        / "features"
        / "rpg"
        / "rpgTurnDiagnostics.ts"
    ).read_text(encoding="utf-8")

    for field in (
        "requestStartedMs",
        "headersReceivedMs",
        "bodyReadMs",
        "jsonParsedMs",
        "storeUpdatedMs",
        "reactCommittedMs",
        "visibleMs",
        "requestToVisibleMs",
    ):
        assert field in source
    assert "X-Omnix-Rpg-Attribution-Pct" in source
    assert "Server-Timing" in source


def test_rpg_turn_ui_fetch_interceptor_is_installed_at_web_startup() -> None:
    source = (_WEB_ROOT / "src" / "main.tsx").read_text(encoding="utf-8")

    assert "installRpgTurnUiFetchInterceptor();" in source
