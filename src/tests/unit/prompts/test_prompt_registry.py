"""Prompt templates are declared once, versioned, and pinned by a golden file (WP-8.4).

Changing a prompt's text fails ``test_prompts_match_the_reviewed_golden_file``
until the template's version is bumped and the golden file is regenerated:

    OMNIX_UPDATE_PROMPT_GOLDEN=1 python -m pytest src/tests/unit/prompts
"""
import hashlib
import json
import os
import sys
import types
from pathlib import Path

import pytest

from app.prompts import prompt_template
from app.prompts.registry import PROMPT_MODULES, load_templates

GOLDEN = Path(__file__).with_name("prompt_golden.json")


def _fingerprints() -> dict[str, dict[str, str]]:
    return {
        template.id: {
            "version": template.version,
            "sha256": hashlib.sha256(template.text.encode("utf-8")).hexdigest(),
        }
        for template in sorted(load_templates().values(), key=lambda item: item.id)
    }


def test_prompts_match_the_reviewed_golden_file():
    current = _fingerprints()
    if os.environ.get("OMNIX_UPDATE_PROMPT_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    changed = sorted(
        template_id for template_id in golden.keys() & current.keys()
        if golden[template_id]["sha256"] != current[template_id]["sha256"]
    )
    assert not [
        template_id for template_id in changed
        if golden[template_id]["version"] == current[template_id]["version"]
    ], "a prompt's text changed without a version bump"
    assert current == golden, "prompts changed: review them, then regenerate the golden file"


def test_every_prompt_module_declares_templates_with_unique_ids():
    templates = load_templates()
    assert {template.module for template in templates.values()} <= {
        name.split(".")[1] for name in PROMPT_MODULES
    }
    assert all(template.id.startswith(template.module + ".") for template in templates.values())


def test_a_template_formats_like_the_string_it_replaced():
    template = prompt_template("chat.example", "1", "Hello {name!r}, {count:03d} new {{items}}")
    assert template.format(name="Ada", count=7) == f"Hello {'Ada'!r}, {7:03d} new {{items}}"


@pytest.mark.parametrize("template_id", ["Chat.Example", "example", "chat example", "chat."])
def test_prompt_ids_are_dotted_lowercase(template_id):
    with pytest.raises(ValueError, match="dotted lowercase"):
        prompt_template(template_id, "1", "text")


def test_a_duplicate_id_is_refused(monkeypatch):
    first = types.ModuleType("fake_prompts_a")
    second = types.ModuleType("fake_prompts_b")
    first.ONE = prompt_template("chat.same", "1", "first")
    second.TWO = prompt_template("chat.same", "1", "second")
    monkeypatch.setitem(sys.modules, "fake_prompts_a", first)
    monkeypatch.setitem(sys.modules, "fake_prompts_b", second)

    with pytest.raises(ValueError, match="declared twice"):
        load_templates(("fake_prompts_a", "fake_prompts_b"))
