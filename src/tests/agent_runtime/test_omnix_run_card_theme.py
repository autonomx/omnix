from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_agent_run_card_uses_theme_tokens_instead_of_dark_only_surface() -> None:
    css = (
        _repo_root()
        / "src/apps/web/src/features/chatbot/OmnixRunCard.css"
    ).read_text(encoding="utf-8")

    assert "background: var(--omnix-panel-solid);" in css
    assert "border: 1px solid var(--omnix-border);" in css
    assert "color: var(--omnix-text);" in css
    assert "background: rgba(10, 16, 31, 0.72);" not in css
    assert "background: rgba(4, 8, 18, 0.42);" not in css


def test_light_appearance_explicitly_covers_agent_run_card_nested_text() -> None:
    css = (
        _repo_root()
        / "src/apps/web/src/appearance-overrides.css"
    ).read_text(encoding="utf-8")

    assert ":root[data-omnix-appearance='light'] .assistant-runtime-card {" in css
    assert ":root[data-omnix-appearance='light'] .assistant-runtime-card > p," in css
    assert ".assistant-runtime-progress > div," in css
    assert ".assistant-runtime-test-output {" in css
