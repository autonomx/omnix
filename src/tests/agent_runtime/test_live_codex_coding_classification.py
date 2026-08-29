"""Live LLM matrix focused specifically on coding-vs-non-coding classification.

This is intentionally opt-in because every parametrized case uses the real
ChatGPT-authenticated Codex provider. It validates both the model's semantic
interpretation and Omnix's final deterministic+semantic route.

PowerShell:

    $env:OMNIX_RUN_LIVE_CODEX_CODING_CLASSIFICATION_TESTS="1"
    $env:OMNIX_LIVE_CODEX_SEMANTIC_MODEL="gpt-5.6-luna"
    $env:OMNIX_LIVE_CODEX_REASONING_EFFORT="xhigh"
    python -m pytest src/tests/agent_runtime/test_live_codex_coding_classification.py -q --tb=short

Optional:
    OMNIX_LIVE_CODEX_FAST_MODE=1
    OMNIX_LIVE_CODEX_PATH=codex
"""
from __future__ import annotations

from dataclasses import dataclass
import os

import pytest

from app.agent_runtime.chat_bridge import _apply_semantic_route_decision
from app.agent_runtime.router import route_omnix_request
from app.agent_runtime.semantic_classifier import (
    ProviderSemanticIntentClassifier,
    semantic_confidence_threshold,
    semantic_profile_id,
)
from app.providers import ChatGPTCodexProvider, ProviderConfig


_TRUE = {"1", "true", "yes", "on"}
_WORKSPACE_ACTIONS = {"workspace_read", "workspace_execute", "workspace_mutate"}


@dataclass(frozen=True)
class CodingClassificationCase:
    id: str
    prompt: str
    final_lane: str
    semantic_lane: str | None = None
    profile: str | None = None
    required_actions: tuple[str, ...] = ()
    required_action_any_of: tuple[tuple[str, ...], ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    forbid_workspace_actions: bool = False


CASES: tuple[CodingClassificationCase, ...] = (
    # Terse UI/project mutations: these are the failure mode that triggered the suite.
    CodingClassificationCase(
        "ui_exact_regression",
        "in omnix, the plus sign on assistant-context-add-button should be centered",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "ui_selector_dot",
        "the + inside .assistant-context-add-button is off center; fix it",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "ui_send_button_width",
        "the Send message button in the Omnix UI is too narrow, make it wider",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "ui_dropdown_clip",
        "the dropdown in the web UI clips long labels. fix that",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "ui_mobile_sidebar",
        "the frontend sidebar should collapse on mobile; implement that behavior",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "ui_modal_icon",
        "the close icon in the React modal is misaligned. straighten it out",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "ui_css_class_padding",
        ".assistant-context-tool-item needs a little more vertical padding; apply the change",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "ui_existing_composer",
        "the existing chat composer layout feels cramped; adjust it so the input gets more room",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "ui_current_project_theme",
        "in the current project, make the settings cards line up consistently",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "ui_apply_file",
        "apply the spacing fix in src/apps/web/src/features/assistant-workspace/assistant-context-controller.css",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    # Backend/repository mutations.
    CodingClassificationCase(
        "router_fix_file",
        "src/app/agent_runtime/router.py still misclassifies this case; fix it",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "auth_tests_green",
        "the auth tests are failing again. find the issue and get them green",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
        required_action_any_of=(("workspace_read", "workspace_execute"),),
    ),
    CodingClassificationCase(
        "ci_dependency_fix",
        "CI broke after the dependency update. diagnose it, make the fix, and rerun the relevant checks",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate", "workspace_execute"),
    ),
    CodingClassificationCase(
        "callback_leak",
        "we seem to leak callbacks on shutdown. track it down and fix the code",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_read", "workspace_mutate"),
    ),
    CodingClassificationCase(
        "refactor_provider",
        "refactor the provider module without changing its public behavior",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "rename_function_tests",
        "rename the parser helper and update its tests so everything still passes",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "endpoint_validation",
        "add validation to the chat endpoint and cover the edge case with tests",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "middleware_patch",
        "patch the auth middleware so expired sessions fail cleanly",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "dead_code_remove",
        "remove the dead provider-selection code and run the focused tests",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate", "workspace_execute"),
    ),
    CodingClassificationCase(
        "typescript_component",
        "update the TypeScript composer component to preserve the selected folder chip",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "python_parser",
        "fix the Python parser in src/app/agent_runtime/router.py",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "branch_conflict",
        "this branch has a merge conflict in the router; resolve it and make sure tests pass",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
        required_action_any_of=(("workspace_execute", "workspace_read"),),
    ),
    CodingClassificationCase(
        "add_regression_tests",
        "add regression tests for the workspace routing bug we just fixed",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "current_app_accessibility",
        "make the current app's context menu keyboard accessible and test it",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    # Read-only repository work must still use the coding Agent.
    CodingClassificationCase(
        "read_repo",
        "inspect the repository and tell me what changed around Agent routing",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_read",),
        forbidden_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "find_selector",
        "find assistant-context-add-button in the repo and tell me where its styles come from",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_read",),
        forbidden_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "review_diff",
        "review the current diff and point out routing risks, but don't edit anything",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_read",),
        forbidden_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "inspect_cause",
        "inspect the code and tell me why the Local folder selection isn't reaching Pi; no edits yet",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_read",),
        forbidden_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "trace_handler",
        "trace the chat request handler through the backend and show me where workspace_root is consumed",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_read",),
        forbidden_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "locate_warning",
        "look through the current project and locate the source of this warning without changing files",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_read",),
        forbidden_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "run_pytest_only",
        "run pytest for the agent_runtime tests and report the failures; don't edit anything",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_execute",),
        forbidden_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "inspect_branch_run_tests",
        "inspect this branch and run the relevant tests, but leave the files untouched",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_read", "workspace_execute"),
        forbidden_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "search_dead_code",
        "look through the repo for dead code around provider selection; report only",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_read",),
        forbidden_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "diagnose_router_readonly",
        "diagnose why router.py sends this request to Chat, but don't patch it yet",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_read",),
        forbidden_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "french_mutation",
        "dans le repo, le bouton d'ajout est mal aligné; corrige le composant sans changer le reste",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_mutate",),
    ),
    CodingClassificationCase(
        "spanish_readonly",
        "revisa el repositorio y dime por qué falla el enrutamiento del chat, pero no edites nada",
        "agent",
        "agent",
        "coding",
        required_actions=("workspace_read",),
        forbidden_actions=("workspace_mutate",),
    ),
    # Programming content that should stay ordinary Chat.
    CodingClassificationCase(
        "chat_write_function",
        "Write a Python function that sorts a list of dictionaries by date.",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_css_example",
        "Show me CSS that centers a plus icon inside a round button.",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_react_example",
        "Create an example React component for a confirmation modal.",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_selector_meaning",
        "What does .assistant-context-add-button mean as a CSS selector?",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_pytest_explain",
        "Explain what pytest -q does.",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_debug_advice",
        "How would you debug a slow API endpoint?",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_test_advice",
        "What tests would you write for a login endpoint?",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_git_teach",
        "Teach me how Git branches work.",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_snippet_summary",
        "Summarize this code snippet; don't access any repository.",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_pasted_fix",
        "Fix the pasted code snippet below in your answer only; don't edit any files.",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_command_quote",
        "I saw `git reset --hard` in documentation. Explain what it means; don't run it.",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_hypothetical_repo",
        "If I asked you to edit the repository, what would an Agent do?",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_no_edit",
        "Don't edit the CSS. Just explain why flexbox centering sometimes looks off.",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "research_compare_frameworks",
        "Compare React and Vue for a small dashboard.",
        "agent",
        "agent",
        "research",
        required_actions=("research_read",),
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_framework_concepts",
        "In general, what are the conceptual differences between React and Vue? No need for current release information.",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_generate_sql",
        "Generate a SQL query that groups orders by month.",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_regex",
        "Write a regex for a lowercase slug.",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_translate_snippet",
        "Convert this tiny JavaScript snippet to Python in your response; no files need changing.",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "chat_architecture_advice",
        "How should I structure callbacks in a Python service?",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    # Adversarial non-software meanings of words added by the UI routing fix.
    CodingClassificationCase(
        "noncode_thermostat_fix",
        "fix the thermostat in the bedroom",
        "agent",
        "agent",
        "house",
        required_action_any_of=(("home_read", "home_mutate"),),
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "noncode_email_code_review",
        "send an email to Bob about the code review",
        "agent",
        "agent",
        "personal-assistant",
        required_actions=("email_send",),
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "noncode_email_tests",
        "summarize my emails about the failing tests",
        "agent",
        "agent",
        "personal-assistant",
        required_actions=("email_read",),
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "noncode_calendar_class",
        "schedule my yoga class on my calendar for tomorrow at 6",
        "agent",
        "agent",
        "personal-assistant",
        required_actions=("calendar_create",),
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "noncode_meeting_component",
        "book a calendar meeting called Hardware Component Review for Friday",
        "agent",
        "agent",
        "personal-assistant",
        required_actions=("calendar_create",),
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "noncode_stock_code",
        "research CODE stock and summarize today's market news",
        "agent",
        "agent",
        "trading-research",
        required_actions=("market_read",),
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "noncode_coat_button",
        "I need to replace the button on my coat. What kind should I buy?",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "noncode_shirt_button_fix",
        "fixing a loose shirt button by hand: walk me through it",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "noncode_school_class",
        "What does 'class' mean in a school schedule?",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "noncode_electrical_component",
        "Explain what this electrical component does conceptually; no software involved.",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "noncode_medical_test",
        "What does a fasting blood test measure?",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "noncode_bug_insect",
        "There's a bug on my kitchen wall. What kind of insect might it be?",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "noncode_file_format",
        "What file format is best for scanning a passport?",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "noncode_engine_component",
        "Describe the role of a suspension component in a car.",
        "chat",
        "chat",
        forbid_workspace_actions=True,
    ),
    CodingClassificationCase(
        "noncode_email_css_subject",
        "check my email for messages with CSS in the subject line",
        "agent",
        "agent",
        "personal-assistant",
        required_actions=("email_read",),
        forbid_workspace_actions=True,
    ),
)


def _enabled() -> bool:
    return (
        str(
            os.environ.get(
                "OMNIX_RUN_LIVE_CODEX_CODING_CLASSIFICATION_TESTS",
                "",
            )
        )
        .strip()
        .casefold()
        in _TRUE
    )


def _bool_env(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().casefold()
    return raw in _TRUE


@pytest.fixture(scope="session")
def live_codex_coding_classifier() -> ProviderSemanticIntentClassifier:
    if not _enabled():
        pytest.skip(
            "live Codex coding classification is opt-in; set "
            "OMNIX_RUN_LIVE_CODEX_CODING_CLASSIFICATION_TESTS=1"
        )

    codex_path = str(
        os.environ.get("OMNIX_LIVE_CODEX_PATH", "codex") or "codex"
    ).strip()
    model = str(
        os.environ.get("OMNIX_LIVE_CODEX_SEMANTIC_MODEL", "gpt-5.6-sol")
        or "gpt-5.6-sol"
    ).strip()
    reasoning_effort = str(
        os.environ.get("OMNIX_LIVE_CODEX_REASONING_EFFORT", "medium") or "medium"
    ).strip()
    fast_mode = _bool_env("OMNIX_LIVE_CODEX_FAST_MODE", True)

    status = ChatGPTCodexProvider.auth_status(codex_path)
    if not (
        status.get("installed")
        and status.get("authenticated")
        and status.get("auth_mode") == "chatgpt"
    ):
        pytest.fail(
            "live coding classification was explicitly enabled, but Codex is "
            f"not ChatGPT-authenticated: {status}"
        )

    provider = ChatGPTCodexProvider(
        ProviderConfig(
            provider_type="chatgpt_codex",
            model=model,
            timeout=90.0,
            extra_params={
                "codex_path": codex_path,
                "reasoning_effort": reasoning_effort,
                "fast_mode": fast_mode,
                "transport": "app_server",
            },
        )
    )
    if not provider.test_connection():
        provider.close()
        pytest.fail(
            "Codex is authenticated but the app-server transport could not be initialized"
        )

    classifier = ProviderSemanticIntentClassifier(
        provider,
        model=model,
        timeout_seconds=60.0,
    )
    try:
        yield classifier
    finally:
        provider.close()


@pytest.mark.live_codex
@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_live_codex_coding_classification(
    live_codex_coding_classifier: ProviderSemanticIntentClassifier,
    case: CodingClassificationCase,
) -> None:
    decision = live_codex_coding_classifier.classify(case.prompt)
    payload = decision.model_dump(mode="json")

    assert decision.confidence >= semantic_confidence_threshold(), {
        "case": case.id,
        "decision": payload,
    }
    if case.semantic_lane is not None:
        assert decision.lane == case.semantic_lane, {
            "case": case.id,
            "expected_semantic_lane": case.semantic_lane,
            "decision": payload,
        }

    actions = set(decision.action_intents)
    assert set(case.required_actions) <= actions, {
        "case": case.id,
        "missing_actions": sorted(set(case.required_actions) - actions),
        "decision": payload,
    }
    for group in case.required_action_any_of:
        assert actions & set(group), {
            "case": case.id,
            "expected_any_action": group,
            "actual_actions": sorted(actions),
            "decision": payload,
        }
    assert not (set(case.forbidden_actions) & actions), {
        "case": case.id,
        "forbidden_actions": sorted(set(case.forbidden_actions) & actions),
        "decision": payload,
    }
    if case.forbid_workspace_actions:
        assert not (actions & _WORKSPACE_ACTIONS), {
            "case": case.id,
            "unexpected_workspace_actions": sorted(actions & _WORKSPACE_ACTIONS),
            "decision": payload,
        }

    resolved_profile = semantic_profile_id(case.prompt, decision)
    if case.profile is not None:
        assert resolved_profile == case.profile, {
            "case": case.id,
            "expected_profile": case.profile,
            "resolved_profile": resolved_profile,
            "decision": payload,
        }

    deterministic = route_omnix_request(case.prompt)
    merged = _apply_semantic_route_decision(
        deterministic,
        decision,
        content=case.prompt,
    )
    assert merged.lane == case.final_lane, {
        "case": case.id,
        "expected_final_lane": case.final_lane,
        "deterministic": deterministic.model_dump(mode="json"),
        "semantic": payload,
        "merged": merged.model_dump(mode="json"),
    }


@pytest.mark.live_codex
def test_live_coding_classification_matrix_is_intentionally_large() -> None:
    assert len(CASES) >= 65
    assert sum(case.profile == "coding" and case.final_lane == "agent" for case in CASES) >= 35
    assert sum(case.final_lane == "chat" for case in CASES) >= 25
    assert sum(case.forbid_workspace_actions for case in CASES) >= 25
