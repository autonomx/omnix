"""
Phase 18.1 — Frontend tooling integration tests.

Tests for renderer function availability and output correctness.
"""

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_presentation_renderer_defines_escape_html_and_inspector_renderers():
    src = _read("src/static/rpg/rpgPresentationRenderer.js")
    assert "function escapeHtml" in src
    assert "export function renderMemoryInspector" in src
    assert "export function renderVisualInspector" in src
    assert "export function renderSessionPackagePanel" in src


def test_dialogue_renderer_wires_loading_and_error_states():
    src = _read("src/static/rpg/rpgDialogueRenderer.js")
    assert "rpg-inspector-loading" in src
    assert "renderInspectorError" in src
    assert 'data-action="queue-normalize"' in src or '"queue-normalize"' in src


def test_inspector_styles_define_bounded_entry_lists_and_error_state():
    src = _read("src/static/rpg/rpgInspectorStyles.css")
    assert ".rpg-inspector-entry-list" in src
    assert "max-height: 320px" in src
    assert ".rpg-inspector-error" in src