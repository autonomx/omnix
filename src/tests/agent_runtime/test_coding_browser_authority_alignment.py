from __future__ import annotations

import pytest

from app.agent_runtime.coding_external_authority import (
    coding_external_capabilities_for_task,
    task_requires_browser_authority,
)
from app.agent_runtime.coding_quality import compile_task_engineering_contract
from app.agent_runtime.evidence import classify_evidence, compile_task_authority
from app.agent_runtime.profiles import get_agent_profile


# Representative coverage for every UI/web vocabulary family that the coding
# quality compiler can turn into mandatory governed-browser validation. Include
# declarative requirements because SemanticTask can classify them as mutations
# even when the raw user wording contains no imperative action verb.
_UI_MUTATION_TASKS = (
    "remove the text from chat header",
    "update the footer text",
    "remove the tools option from the sidebar",
    "change the toolbar minimize button to an arrow",
    "update the frontend button",
    "update the web page",
    "change the CSS form",
    "update the UI dialog",
    "update the UX dropdown",
    "fix the React modal button",
    "update the TypeScript component",
    "update the TSX component",
    "update the JSX component",
    "change the theme menu",
    "fix light mode tabs",
    "fix dark mode layout",
    "the chat header should show only one character name",
    (
        "characters in character drop down in header should not be showing 2 of the same name "
        "separated by -; it should show only one name"
    ),
)


@pytest.mark.parametrize("task", _UI_MUTATION_TASKS)
def test_required_ui_browser_validation_always_has_matching_authority(task: str) -> None:
    _requirements, _constraints, validation_plan = compile_task_engineering_contract(
        task,
        [],
        profile="coding",
        mutating=True,
    )

    required_browser = [
        item
        for item in validation_plan
        if item.kind == "browser" and item.required
    ]

    assert required_browser, f"quality contract did not require browser validation for {task!r}"
    assert task_requires_browser_authority(task), (
        "quality requires governed browser proof but the authority compiler would "
        f"launch Pi without browser authority for {task!r}"
    )

    issued = set(coding_external_capabilities_for_task(task))
    assert "browser.open" in issued
    assert "browser.assert_text_not_contains" in issued


def test_header_removal_is_issued_browser_authority_through_task_compiler() -> None:
    task = "remove the text from chat header"
    profile = get_agent_profile("coding")
    decision = classify_evidence(task, profile_id="coding")

    compiled = compile_task_authority(profile, task, decision)
    issued = set(compiled.required_external)

    assert "browser.open" in issued
    assert "browser.assert_text_not_contains" in issued
    assert "browser.snapshot" in issued


def test_declarative_dropdown_requirement_is_issued_browser_authority_through_task_compiler() -> None:
    task = (
        "characters in character drop down in header should not be showing 2 of the same name "
        "separated by -; it should show only one name"
    )
    profile = get_agent_profile("coding")
    decision = classify_evidence(task, profile_id="coding")

    compiled = compile_task_authority(profile, task, decision)
    issued = set(compiled.required_external)

    assert "browser.open" in issued
    assert "browser.snapshot" in issued
    assert "browser.assert_text_not_contains" in issued


def test_declarative_ui_requirement_does_not_need_an_imperative_action_verb() -> None:
    task = "the character dropdown should show only one display name"

    assert task_requires_browser_authority(task)
    assert "browser.open" in set(coding_external_capabilities_for_task(task))


def test_explicit_browser_prohibition_still_fails_closed() -> None:
    task = "update the chat header; do not use the browser"

    assert not task_requires_browser_authority(task)
    assert not {
        capability
        for capability in coding_external_capabilities_for_task(task)
        if capability.startswith("browser.")
    }
