from __future__ import annotations

from pathlib import Path

from app.config.registry import render_configuration_markdown


def test_configuration_doc_is_generated_from_registry() -> None:
    root = Path(__file__).resolve().parents[3]
    assert (root / "docs" / "CONFIGURATION.md").read_text(encoding="utf-8") == render_configuration_markdown()
