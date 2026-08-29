from __future__ import annotations

import pytest

from app.agent_runtime.chat_bridge import _apply_semantic_route_decision
from app.agent_runtime.profiles import select_agent_profile_id
from app.agent_runtime.router import route_omnix_request
from app.agent_runtime.semantic_classifier import (
    SemanticIntentDecision,
    semantic_profile_id,
)


CODING_AGENT_CASES = (
    # Concrete UI/CSS mutations, including the regression that triggered this work.
    ("ui_selector_center", "in omnix, the plus sign on assistant-context-add-button should be centered"),
    ("ui_selector_dot_center", "center the plus sign inside .assistant-context-add-button"),
    ("ui_selector_make_wider", "make .assistant-context-add-button wider"),
    ("ui_selector_apply_css", "apply this CSS change to .assistant-context-add-button"),
    ("ui_omnix_button", "restyle the send button in the Omnix UI"),
    ("ui_frontend_icon", "move the icon in the frontend header"),
    ("ui_web_modal", "align the modal footer in the web app"),
    ("ui_react_component", "update the React component on the page"),
    ("ui_frontend_sidebar", "move the sidebar in the frontend layout"),
    ("ui_web_dropdown", "restyle the dropdown in the web interface"),
    ("ui_omnix_badge", "remove the badge from the Omnix UI"),
    ("ui_react_chip", "add a chip to the React interface"),
    ("ui_css_textarea", "update the textarea styling in CSS"),
    ("ui_html_layout", "change the HTML layout for the chat page"),
    ("ui_stylesheet", "update the stylesheet for the composer"),
    # Explicit files, repository, codebase, and software targets.
    ("file_router_py", "update src/app/agent_runtime/router.py to handle this case"),
    ("file_chat_bridge_py", "edit src/app/agent_runtime/chat_bridge.py"),
    ("file_component_tsx", "modify src/apps/web/src/components/Composer.tsx"),
    ("file_store_ts", "change app/chat/store.ts"),
    ("repo_fix_tests", "fix the failing tests in the repo"),
    ("repo_update", "update the repository implementation"),
    ("codebase_patch", "patch the codebase to remove the duplicate branch"),
    ("workspace_change", "change the workspace implementation"),
    ("code_fix", "fix the code that handles chat routing"),
    ("css_change", "change the CSS for the chat composer"),
    ("html_change", "update the HTML used by the message form"),
    ("tsx_change", "modify the TSX for the composer"),
    ("jsx_change", "update the JSX for the header"),
    ("middleware_patch", "patch the auth middleware"),
    ("endpoint_change", "change the API endpoint for chat messages"),
    ("callback_remove", "remove the stale callback from the codebase"),
    ("handler_validation", "add validation to the request handler"),
    ("hook_delete", "delete the unused hook from the frontend"),
    ("router_implement", "implement the router change in app/router.py"),
    ("middleware_refactor", "refactor the middleware in src/app/auth.py"),
    ("function_modify", "modify the parser function in src/parser.py"),
    ("module_edit", "edit the routing module in app/router.py"),
    ("pytest_fix", "fix the pytest configuration in the repo"),
    ("vitest_update", "update the vitest setup in the frontend"),
    ("backend_endpoint", "change the backend endpoint implementation"),
    ("frontend_code", "edit the frontend code for the composer"),
    ("selector_add", "add the selector .assistant-context-add-button to the stylesheet"),
    ("classname_update", "update the classname used by the frontend component"),
    # Clear workspace reads/diagnostics should also use coding Agent.
    ("read_repo", "inspect the repository and tell me what changed"),
    ("read_codebase", "review the codebase for duplicate routing logic"),
    ("read_router_file", "read src/app/agent_runtime/router.py and summarize the routing order"),
    ("check_file", "check router.py for the workspace mutation branch"),
    ("find_selector", "find .assistant-context-add-button in the repo"),
    ("locate_callback", "locate the callback that handles chat submission"),
    ("search_code", "search the code for assistant-context-add-button"),
    ("trace_middleware", "trace the auth middleware and tell me where it rejects the request"),
    ("examine_endpoint", "examine the API endpoint that sends chat messages"),
    ("diagnose_pytest", "diagnose the pytest failure in the repository"),
    ("inspect_css", "inspect the CSS for the chat composer"),
    ("review_frontend_component", "review the frontend component for the composer"),
    ("check_omnix_button", "check the button in the Omnix UI and tell me how it is styled"),
    ("read_selector_style", "read .assistant-context-add-button and its related styles"),
    ("find_store_file", "find app/chat/store.py and inspect how metadata is persisted"),
    ("trace_handler", "trace the request handler in the backend"),
    ("inspect_workspace", "inspect the workspace before making any changes"),
    ("review_module", "review the routing module for obvious mistakes"),
    ("diagnose_router", "diagnose the router behavior in src/app/agent_runtime/router.py"),
    ("examine_function", "examine the function in src/parser.py that parses commands"),
)


CODING_CHAT_CASES = (
    # Programming explanation/advice is ordinary Chat when no workspace action is requested.
    ("how_center_css", "How do I center a button with CSS?"),
    ("what_selector", "What does .assistant-context-add-button mean in CSS?"),
    ("explain_router", "Explain what a router.py file usually does."),
    ("why_pytest", "Why would pytest report a fixture not found error?"),
    ("teach_react", "Teach me how React components work."),
    ("describe_grid", "Describe CSS grid in simple terms."),
    ("how_refactor", "How would you refactor middleware safely?"),
    ("what_tests", "What tests would you run for a login endpoint?"),
    ("compare_languages", "Compare Python and TypeScript for backend services."),
    ("summarize_snippet", "Summarize this code snippet for me."),
    ("write_function", "Write a Python function that sorts a list."),
    ("write_css", "Write CSS that centers a plus icon inside a button."),
    ("create_example_component", "Create an example React component for a modal."),
    ("generate_regex", "Generate a regex for a simple identifier."),
    ("show_html", "Show me an HTML example with a form and button."),
    ("sample_typescript", "Give me a TypeScript sample that maps an array."),
    ("example_pytest", "Give me an example pytest fixture."),
    ("code_below", "The code below is just an example; explain why it works."),
    ("pasted_code", "Explain the pasted code without changing any files."),
    ("quoted_command", "I saw `pytest -q` in docs. What does it do?"),
    # Hypothetical/negated coding requests must not execute.
    ("hypothetical_edit", "If I asked you to edit src/app/router.py, what would happen?"),
    ("hypothetical_agent", "How would an agent modify a React component?"),
    ("could_agent", "Could an agent inspect a repository for me?"),
    ("dont_edit", "Don't edit the repository; just explain the likely issue."),
    ("do_not_change_css", "Do not change the CSS; tell me how centering works."),
    ("dont_modify_code", "I don't want you to modify code, just describe the approach."),
    ("no_need_fix", "No need to fix the tests; explain the failure."),
    ("quoted_fix", "Explain the phrase \"fix the failing tests\"."),
    ("why_agent_fixed", "Why did the agent edit that file?"),
    ("teach_implementation", "Teach me how to implement a REST API."),
)


NONCODING_PROFILE_CASES = (
    # Generic words introduced by the UI fix must not force the coding profile.
    ("home_fix_thermostat", "fix the thermostat in the bedroom", "house"),
    ("home_check_light", "check the bedroom light status", "house"),
    ("home_change_light", "change the living room light to a warmer setting", "house"),
    ("personal_email_code", "send an email to Bob about the code review", "personal-assistant"),
    ("personal_tests_email", "summarize my emails about the failing tests", "personal-assistant"),
    ("personal_calendar_class", "schedule my yoga class on my calendar", "personal-assistant"),
    ("personal_meeting_component", "book a meeting about the hardware component", "personal-assistant"),
    ("personal_contact_button", "look up Button Industries in my contacts", "personal-assistant"),
    ("trading_code_company", "research CODE stock and its latest market news", "trading-research"),
    ("trading_ui_company", "analyze UI stock performance today", "trading-research"),
    ("trading_order_bug", "cancel my NVDA order because the broker app has a bug", "trading-research"),
    ("trading_tests", "research NVDA after its latest product tests", "trading-research"),
    ("physical_button", "change the button on my coat", "research"),
    ("shirt_button", "fix the loose button on my shirt", "research"),
    ("electrical_component", "inspect this electrical component conceptually", "research"),
    ("school_class", "help me understand my chemistry class", "research"),
    ("legal_file", "help me file a complaint with the landlord", "research"),
    ("medical_test", "run a medical test is a phrase I want explained", "research"),
    ("music_module", "explain a modular synthesizer module", "research"),
    ("math_function", "analyze this mathematical function conceptually", "research"),
)


@pytest.mark.parametrize("case_id,prompt", CODING_AGENT_CASES, ids=lambda value: str(value))
def test_clear_workspace_requests_route_to_coding_agent(case_id: str, prompt: str) -> None:
    route = route_omnix_request(prompt)
    assert route.lane == "agent", {
        "case": case_id,
        "prompt": prompt,
        "route": route.model_dump(mode="json"),
    }
    assert select_agent_profile_id(prompt) == "coding", {
        "case": case_id,
        "prompt": prompt,
    }


@pytest.mark.parametrize("case_id,prompt", CODING_CHAT_CASES, ids=lambda value: str(value))
def test_programming_conversation_without_workspace_action_stays_chat(
    case_id: str,
    prompt: str,
) -> None:
    route = route_omnix_request(prompt)
    assert route.lane == "chat", {
        "case": case_id,
        "prompt": prompt,
        "route": route.model_dump(mode="json"),
    }


@pytest.mark.parametrize(
    "case_id,prompt,expected_profile",
    NONCODING_PROFILE_CASES,
    ids=lambda value: str(value),
)
def test_generic_software_words_do_not_steal_other_domains(
    case_id: str,
    prompt: str,
    expected_profile: str,
) -> None:
    assert select_agent_profile_id(prompt) == expected_profile, {
        "case": case_id,
        "prompt": prompt,
        "expected_profile": expected_profile,
        "actual_profile": select_agent_profile_id(prompt),
    }


@pytest.mark.parametrize(
    "prompt,reason",
    [
        (
            "in omnix, the plus sign on assistant-context-add-button should be centered",
            "workspace_mutation_request",
        ),
        (
            "inspect src/app/agent_runtime/router.py and tell me why it routes this to Chat",
            "workspace_read_request",
        ),
    ],
)
def test_high_confidence_workspace_routes_cannot_be_downgraded_by_semantic_chat(
    prompt: str,
    reason: str,
) -> None:
    deterministic = route_omnix_request(prompt)
    assert deterministic.reason == reason
    semantic = SemanticIntentDecision(
        lane="chat",
        profile_id="research",
        primary_intent="conversation",
        confidence=0.99,
        reason="adversarial misclassification",
    )
    merged = _apply_semantic_route_decision(
        deterministic,
        semantic,
        content=prompt,
    )
    assert merged.lane == "agent"
    assert merged.reason == reason


@pytest.mark.parametrize(
    "prompt,action",
    [
        ("make the existing chat controls line up better", "workspace_mutate"),
        ("look through the current project and find where chat routing happens", "workspace_read"),
        ("run the relevant checks and tell me why CI is red", "workspace_execute"),
    ],
)
def test_semantic_workspace_actions_can_promote_indirect_coding_requests(
    prompt: str,
    action: str,
) -> None:
    deterministic = route_omnix_request(prompt)
    semantic = SemanticIntentDecision(
        lane="agent",
        profile_id="coding",
        primary_intent="coding_work",
        action_intents=[action],
        confidence=0.95,
        reason="workspace action required",
    )
    merged = _apply_semantic_route_decision(
        deterministic,
        semantic,
        content=prompt,
    )
    assert merged.lane == "agent"
    assert semantic_profile_id(prompt, semantic) == "coding"


def test_semantic_agent_label_without_workspace_action_cannot_promote_chat() -> None:
    prompt = "Tell me what a component is."
    deterministic = route_omnix_request(prompt)
    assert deterministic.lane == "chat"
    semantic = SemanticIntentDecision(
        lane="agent",
        profile_id="coding",
        primary_intent="coding",
        confidence=0.99,
        reason="label only",
    )
    merged = _apply_semantic_route_decision(
        deterministic,
        semantic,
        content=prompt,
    )
    assert merged.lane == "chat"


def test_coding_classification_matrix_is_intentionally_large() -> None:
    assert len(CODING_AGENT_CASES) >= 60
    assert len(CODING_CHAT_CASES) >= 30
    assert len(NONCODING_PROFILE_CASES) >= 20
    assert (
        len(CODING_AGENT_CASES)
        + len(CODING_CHAT_CASES)
        + len(NONCODING_PROFILE_CASES)
    ) >= 110
