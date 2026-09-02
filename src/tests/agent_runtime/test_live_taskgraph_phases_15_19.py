"""Opt-in live LLM matrix for Agent Runtime Phases 15-19.

This suite is intentionally different from the broad live Agent conversation
matrix. GPT-5.6 Luna interprets each real multi-turn conversation, then the test
asserts the deterministic Phase 15-19 contracts produced by Omnix:

- evidence coverage identity and temporal identity;
- multi-profile TaskGraph selection and per-node authority;
- cross-profile data dependencies and authority-free synthesis;
- Agent <-> TaskGraph supersession, graph steering, replay, and cancellation;
- coding acceptance parity inside a graph;
- reference-context propagation as data rather than authority;
- authority-preserving optimizer plans.

No home, market, web, email, calendar, workspace, or TaskGraph runtime tool is
executed by this suite. The live model supplies only SemanticTask meaning.

PowerShell:

    $env:OMNIX_RUN_LIVE_TASKGRAPH_PHASE_TESTS="1"
    python -m pytest src/tests/agent_runtime/test_live_taskgraph_phases_15_19.py -q --tb=short

Run one scenario:

    $env:OMNIX_LIVE_TASKGRAPH_SCENARIO="depth_06_executor_supersession"
    python -m pytest src/tests/agent_runtime/test_live_taskgraph_phases_15_19.py -q --tb=short

Optional:

    $env:OMNIX_LIVE_CODEX_PATH="codex"
    $env:OMNIX_LIVE_TASKGRAPH_FAST_MODE="0"

The live model contract is fixed here to GPT-5.6 Luna + high reasoning effort.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from types import SimpleNamespace
from typing import Literal

import pytest

from app.agent_runtime import chat_bridge
from app.agent_runtime.active_objective import (
    ActiveObjective,
    advance_active_objective,
)
from app.agent_runtime.chat_bridge import route_typed_chat_turn
from app.agent_runtime.contracts import ModelRef, WorkspaceSpec
from app.agent_runtime.evidence import evidence_coverage_key
from app.agent_runtime.semantic_task import SemanticTask
from app.agent_runtime.semantic_task_parser import ProviderSemanticTaskParser
from app.agent_runtime.task_graph import (
    TaskGraph,
    TaskGraphRunSnapshot,
    TaskNodeRunState,
    compile_task_graph,
    task_node_fingerprint,
)
from app.agent_runtime.task_graph_optimizer import optimize_task_graph
from app.agent_runtime.task_graph_revision import merge_task_graph_continuation
from app.agent_runtime.turn_plan import (
    TurnPlan,
    compile_turn_plan,
    derive_effective_objective,
)
from app.providers import ChatGPTCodexProvider, ProviderConfig


_TRUE = {"1", "true", "yes", "on"}
_MODEL = "gpt-5.6-luna"
_REASONING_EFFORT = "high"
_GRAPH_ACTIONS = {
    "start_task_graph",
    "steer_task_graph",
    "replace_task_graph_with_task_graph",
    "replace_agent_with_task_graph",
}
_AGENT_START_ACTIONS = {
    "start_agent",
    "replace_task_graph_with_agent",
    "replace_agent_with_agent",
}
_MUTATING_ACTIONS = {
    "workspace_mutate",
    "workspace_execute",
    "ops_execute",
    "home_mutate",
    "email_send",
    "email_draft",
    "calendar_create",
}


@dataclass(frozen=True)
class GraphExpectation:
    required_profiles: tuple[str, ...] = ()
    forbidden_profiles: tuple[str, ...] = ()
    required_edges: tuple[tuple[str, str], ...] = ()
    required_capabilities: tuple[tuple[str, str], ...] = ()
    forbidden_capabilities: tuple[tuple[str, str], ...] = ()
    require_synthesis: bool = False
    require_coding_acceptance: bool = False
    require_sensitive_approval: tuple[str, ...] = ()
    reference_contains: tuple[str, ...] = ()
    optimizer_batch_min_requirements: int = 0
    expected_anomaly: str | None = None


@dataclass(frozen=True)
class LiveTurn:
    user: str
    run_actions: tuple[str, ...]
    plan_profiles: tuple[str | None, ...] = ()
    required_actions: tuple[str, ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    evidence_minimums: tuple[tuple[str, int], ...] = ()
    coverage_contains: tuple[str, ...] = ()
    freshness_minimums: tuple[tuple[str, str, int], ...] = ()
    graph: GraphExpectation | None = None
    attach_workspace: bool = False
    assistant: str = "Understood."


@dataclass(frozen=True)
class LiveScenario:
    id: str
    phases: tuple[int, ...]
    turns: tuple[LiveTurn, ...]
    notes: str = ""


def T(
    user: str,
    *run_actions: str,
    **kwargs,
) -> LiveTurn:
    return LiveTurn(
        user=user,
        run_actions=tuple(run_actions),
        **kwargs,
    )


SCENARIOS: tuple[LiveScenario, ...] = (
    LiveScenario(
        id="phase15_historical_current_identity",
        phases=(15,),
        turns=(
            T(
                "Compare NVDA's current market quote with its market quote as of "
                "2026-08-03T20:00:00Z. Treat current and historical as two "
                "separate observations for the same security.",
                "chat",
                "start_agent",
                plan_profiles=("trading-research", None),
                evidence_minimums=(("market_quote", 2),),
                coverage_contains=("nvda",),
                freshness_minimums=(
                    ("market_quote", "current", 1),
                    ("market_quote", "as_of_date", 1),
                ),
                graph=GraphExpectation(
                    required_profiles=("trading-research",),
                ),
            ),
        ),
        notes="Current and point-in-time requirements must not collapse.",
    ),
    LiveScenario(
        id="phase16_interleaved_profile_fail_closed",
        phases=(16,),
        turns=(
            T(
                "In the attached Omnix repo, first inspect the current React "
                "dependency, then research the latest stable React release, then "
                "modify the repo to upgrade React, and finally email me the result.",
                "start_task_graph",
                plan_profiles=(None,),
                attach_workspace=True,
                graph=GraphExpectation(
                    expected_anomaly=(
                        "interleaved_profile_dependency_requires_split"
                    ),
                ),
            ),
        ),
        notes="Coding -> research -> coding cannot be collapsed into one coding node.",
    ),
    LiveScenario(
        id="depth_01_evidence_coverage",
        phases=(15, 19),
        turns=(
            T(
                "Research the latest stable React and Vue releases separately, "
                "using primary sources where possible, and compare their versions.",
                "chat",
                "start_agent",
                plan_profiles=("research", None),
                evidence_minimums=(("software_release", 2),),
                coverage_contains=("react", "vue"),
                graph=GraphExpectation(
                    required_profiles=("research",),
                    optimizer_batch_min_requirements=2,
                ),
            ),
        ),
        notes="Same source class must retain two independently satisfiable obligations.",
    ),
    LiveScenario(
        id="depth_02_single_step_quote_email_cancel",
        phases=(16, 17, 18),
        turns=(
            T(
                "Get AAPL's current market price, then email that exact price to me. "
                "Do not send the email before you have the quote.",
                "start_task_graph",
                plan_profiles=(None,),
                required_actions=("market_read", "email_send"),
                evidence_minimums=(("market_quote", 1),),
                coverage_contains=("aapl",),
                graph=GraphExpectation(
                    required_profiles=("trading-research", "personal-assistant"),
                    required_edges=(("trading-research", "personal-assistant"),),
                    require_synthesis=True,
                    require_sensitive_approval=("personal-assistant",),
                ),
                assistant="The quote and email task is in progress.",
            ),
            T(
                "Actually, do not send any email or take any action. Just explain "
                "the AAPL price you already obtained above in chat; do not re-check it.",
                "cancel_task_graph_then_chat",
                plan_profiles=(None,),
                forbidden_actions=("email_send", "market_read"),
            ),
        ),
    ),
    LiveScenario(
        id="depth_03_agent_promotes_to_graph_then_narrows",
        phases=(16, 18),
        turns=(
            T(
                "In the attached Omnix repo, fix the failing TaskGraph approval "
                "test and run the focused tests.",
                "start_agent",
                plan_profiles=("coding",),
                required_actions=("workspace_mutate",),
                attach_workspace=True,
                assistant="The coding task is active.",
            ),
            T(
                "Continue that same coding task, and when the tests are done email "
                "me the final test result.",
                "replace_agent_with_task_graph",
                plan_profiles=("coding", "personal-assistant", None),
                required_actions=("email_send",),
                graph=GraphExpectation(
                    required_profiles=("coding", "personal-assistant"),
                    required_edges=(("coding", "personal-assistant"),),
                    require_synthesis=True,
                    require_coding_acceptance=True,
                    require_sensitive_approval=("coding", "personal-assistant"),
                ),
                assistant="The coding and email work is now one coordinated task.",
            ),
            T(
                "Actually, don't send any email. Just summarize the coding work in "
                "chat; do not edit files or run anything else.",
                "cancel_task_graph_then_chat",
                forbidden_actions=("workspace_mutate", "workspace_execute", "email_send"),
            ),
        ),
    ),
    LiveScenario(
        id="depth_04_graph_continue_replay_cancel",
        phases=(16, 17, 18),
        turns=(
            T(
                "Check the current Vancouver weather and my calendar availability, "
                "then create a tentative 2 PM Saturday walk only if it is dry and I am free.",
                "start_task_graph",
                plan_profiles=(None,),
                required_actions=("calendar_create",),
                evidence_minimums=(("weather_state", 1), ("calendar_state", 1)),
                graph=GraphExpectation(
                    required_profiles=("research", "personal-assistant"),
                    required_edges=(("research", "personal-assistant"),),
                    required_capabilities=(("research", "weather.current"),),
                    require_synthesis=True,
                ),
                assistant="The weather/calendar task is active.",
            ),
            T(
                "Also check Seattle's current weather before deciding; keep the same "
                "calendar action and final answer.",
                "steer_task_graph",
                plan_profiles=("research", None),
                evidence_minimums=(("weather_state", 1),),
                coverage_contains=("seattle",),
                graph=GraphExpectation(
                    required_profiles=("research",),
                    require_synthesis=True,
                ),
                assistant="Seattle weather is now part of the task.",
            ),
            T(
                "Try that exact request again.",
                "steer_task_graph",
                assistant="The graph is being replayed.",
            ),
            T(
                "Actually, do not create or change any calendar event. Just explain "
                "the weather and availability already gathered; do not re-check anything.",
                "cancel_task_graph_then_chat",
                forbidden_actions=("calendar_create", "research_read"),
            ),
        ),
    ),
    LiveScenario(
        id="depth_05_multi_profile_continuation_synthesis",
        phases=(16, 17, 18, 19),
        turns=(
            T(
                "Check GME's current market price and the current Vancouver weather, "
                "then email me one combined summary after both observations are available.",
                "start_task_graph",
                plan_profiles=(None,),
                required_actions=("email_send",),
                evidence_minimums=(("market_quote", 1), ("weather_state", 1)),
                graph=GraphExpectation(
                    required_profiles=(
                        "trading-research",
                        "research",
                        "personal-assistant",
                    ),
                    required_capabilities=(
                        ("trading-research", "trading.market_quote"),
                        ("research", "weather.current"),
                    ),
                    forbidden_capabilities=(
                        ("trading-research", "weather.current"),
                    ),
                    require_synthesis=True,
                ),
                assistant="The market/weather graph is active.",
            ),
            T(
                "Also include AMC's current market price in the same final summary.",
                "steer_task_graph",
                plan_profiles=("trading-research", None),
                evidence_minimums=(("market_quote", 1),),
                coverage_contains=("amc",),
                graph=GraphExpectation(
                    required_profiles=("trading-research",),
                    require_synthesis=True,
                ),
                assistant="AMC is included.",
            ),
            T(
                "Also include Seattle's current weather.",
                "steer_task_graph",
                plan_profiles=("research", None),
                evidence_minimums=(("weather_state", 1),),
                coverage_contains=("seattle",),
                graph=GraphExpectation(
                    required_profiles=("research",),
                    require_synthesis=True,
                ),
                assistant="Seattle weather is included.",
            ),
            T(
                "Give me a chat-only explanation using only the observations already "
                "shown in this conversation. Do not invoke any market, weather, or "
                "research tool.",
                "chat",
                forbidden_actions=("market_read", "research_read"),
                assistant="Here is the comparison from the collected observations.",
            ),
            T(
                "Try that exact request again.",
                "steer_task_graph",
                assistant="The durable graph is replaying the original objective.",
            ),
        ),
    ),
    LiveScenario(
        id="depth_06_executor_supersession",
        phases=(16, 18),
        turns=(
            T(
                "Get MSFT's current price, then email that exact price to me.",
                "start_task_graph",
                plan_profiles=(None,),
                required_actions=("market_read", "email_send"),
                graph=GraphExpectation(
                    required_profiles=("trading-research", "personal-assistant"),
                    require_synthesis=True,
                ),
                assistant="The price/email graph is active.",
            ),
            T(
                "New task: in the attached Omnix repo, fix the failing TaskGraph "
                "recovery test and run the focused tests.",
                "replace_task_graph_with_agent",
                plan_profiles=("coding",),
                required_actions=("workspace_mutate",),
                attach_workspace=True,
                assistant="The old graph was superseded by the coding task.",
            ),
            T(
                "Also email me the final focused-test result when that coding task is done.",
                "replace_agent_with_task_graph",
                plan_profiles=("coding", "personal-assistant", None),
                required_actions=("email_send",),
                graph=GraphExpectation(
                    required_profiles=("coding", "personal-assistant"),
                    require_coding_acceptance=True,
                    require_synthesis=True,
                ),
                assistant="The coding task now includes email delivery.",
            ),
            T(
                "New task: check Vancouver weather and my calendar, then schedule a "
                "walk if I am free and the weather is dry.",
                "replace_task_graph_with_task_graph",
                plan_profiles=(None,),
                required_actions=("calendar_create",),
                graph=GraphExpectation(
                    required_profiles=("research", "personal-assistant"),
                    require_synthesis=True,
                ),
                assistant="The coding/email graph was superseded by the new graph.",
            ),
            T(
                "Actually, don't schedule anything. Just explain what you already "
                "found; do not re-check weather or calendar.",
                "cancel_task_graph_then_chat",
                forbidden_actions=("calendar_create", "research_read"),
                assistant="The graph was cancelled and the existing findings were explained.",
            ),
            T(
                "Email that explanation to me now.",
                "start_agent",
                plan_profiles=("personal-assistant",),
                required_actions=("email_send",),
                assistant="A new email task was started.",
            ),
        ),
    ),
    LiveScenario(
        id="depth_07_reference_context_and_cross_profile_data",
        phases=(16, 17, 18),
        turns=(
            T(
                "For this investigation, the affected service is the API on port "
                "5432 and the repository is Omnix. Do not do anything yet.",
                "chat",
                assistant="I will use port 5432 and Omnix as conversation context.",
            ),
            T(
                "In the attached repo, inspect where port 5432 is configured. Read "
                "only; do not edit or run tests yet.",
                "start_agent",
                plan_profiles=("coding",),
                required_actions=("workspace_read",),
                forbidden_actions=("workspace_mutate", "workspace_execute"),
                attach_workspace=True,
                assistant="The repository configuration has been inspected.",
            ),
            T(
                "Continue this investigation: also research the current PostgreSQL "
                "documentation for that connection behavior and compare it with the "
                "repo configuration.",
                "replace_agent_with_task_graph",
                plan_profiles=(None,),
                graph=GraphExpectation(
                    required_profiles=("coding", "research"),
                    required_edges=(("coding", "research"),),
                    require_synthesis=True,
                    reference_contains=("5432", "Omnix"),
                ),
                assistant="Repository and PostgreSQL documentation are now coordinated.",
            ),
            T(
                "Now run the focused configuration test, but do not edit files.",
                "steer_task_graph",
                plan_profiles=("coding", None),
                required_actions=("workspace_execute",),
                forbidden_actions=("workspace_mutate",),
                graph=GraphExpectation(
                    required_profiles=("coding",),
                    require_synthesis=True,
                    reference_contains=("5432",),
                ),
                assistant="The focused configuration test is included.",
            ),
            T(
                "If that test proves the mismatch, fix the configuration and add "
                "a regression test.",
                "steer_task_graph",
                plan_profiles=("coding", None),
                required_actions=("workspace_mutate",),
                graph=GraphExpectation(
                    required_profiles=("coding",),
                    require_coding_acceptance=True,
                    require_synthesis=True,
                    reference_contains=("5432",),
                ),
                assistant="The conditional coding correction is part of the graph.",
            ),
            T(
                "Also include the current PostgreSQL release-note context before the final answer.",
                "steer_task_graph",
                plan_profiles=("research", None),
                evidence_minimums=(("software_release", 1),),
                graph=GraphExpectation(
                    required_profiles=("research",),
                    require_synthesis=True,
                    reference_contains=("5432",),
                ),
                assistant="Current release context is included.",
            ),
            T(
                "Summarize the existing graph findings only. No more tools or lookups.",
                "chat",
                forbidden_actions=("workspace_read", "workspace_mutate", "workspace_execute", "research_read"),
            ),
        ),
    ),
    LiveScenario(
        id="depth_08_evidence_identity_stress",
        phases=(15, 19),
        turns=(
            T(
                "Research the latest stable React, Vue, and Svelte releases separately "
                "using primary sources where possible.",
                "chat",
                "start_agent",
                plan_profiles=("research", None),
                evidence_minimums=(("software_release", 3),),
                coverage_contains=("react", "vue", "svelte"),
                graph=GraphExpectation(
                    required_profiles=("research",),
                    optimizer_batch_min_requirements=3,
                ),
                assistant="Three release facts were collected separately.",
            ),
            T(
                "Now add the latest stable Node.js and Deno releases as separate facts.",
                "chat",
                "start_agent",
                "steer_agent",
                plan_profiles=("research", None),
                evidence_minimums=(("software_release", 2),),
                coverage_contains=("node", "deno"),
                graph=GraphExpectation(
                    required_profiles=("research",),
                    optimizer_batch_min_requirements=2,
                ),
                assistant="Node.js and Deno are separate release facts.",
            ),
            T(
                "Research the latest SEC filing for GME and AMC separately.",
                "start_agent",
                "replace_agent_with_agent",
                plan_profiles=("trading-research",),
                evidence_minimums=(("company_filing", 2),),
                coverage_contains=("gme", "amc"),
                assistant="GME and AMC filings were treated separately.",
            ),
            T(
                "Also add the latest SEC filing for NVDA and AMD, separately.",
                "chat",
                "steer_agent",
                plan_profiles=("trading-research", None),
                evidence_minimums=(("company_filing", 2),),
                coverage_contains=("nvda", "amd"),
                assistant="NVDA and AMD filings were added separately.",
            ),
            T(
                "Compare only those filing facts already collected. Do not re-query anything.",
                "chat",
                "steer_agent",
                forbidden_actions=("market_read", "research_read"),
                assistant="Here is the comparison using only collected facts.",
            ),
            T(
                "New research task: check current GitHub public service status and "
                "current npm public service status separately.",
                "chat",
                "start_agent",
                "replace_agent_with_agent",
                plan_profiles=("research", None),
                evidence_minimums=(("general_current_web", 2),),
                coverage_contains=("github", "npm"),
                assistant="The two service-status facts are separate.",
            ),
            T(
                "Check current Vercel public service status as a separate fact.",
                "chat",
                "start_agent",
                "replace_agent_with_agent",
                plan_profiles=("research", None),
                evidence_minimums=(("general_current_web", 1),),
                coverage_contains=("vercel",),
                assistant="Vercel status was added.",
            ),
            T(
                "Summarize every fact already collected without rechecking any source.",
                "chat",
                "steer_agent",
                forbidden_actions=("research_read", "market_read"),
            ),
        ),
    ),
    LiveScenario(
        id="depth_09_mixed_lifecycle_and_retry",
        phases=(16, 17, 18),
        turns=(
            T(
                "In the attached Omnix repo, inspect the TaskGraph approval code "
                "and explain the likely bug. Read only.",
                "start_agent",
                plan_profiles=("coding",),
                required_actions=("workspace_read",),
                forbidden_actions=("workspace_mutate",),
                attach_workspace=True,
                assistant="The approval code has been inspected.",
            ),
            T(
                "Explain the tradeoff you see before changing anything. Do not run tools.",
                "chat",
                "steer_agent",
                forbidden_actions=("workspace_read", "workspace_mutate", "workspace_execute"),
                assistant="Here is the tradeoff.",
            ),
            T(
                "Run the focused approval test, still without editing files.",
                "steer_agent",
                plan_profiles=("coding",),
                required_actions=("workspace_execute",),
                forbidden_actions=("workspace_mutate",),
                assistant="The focused test was run.",
            ),
            T(
                "Fix the proven bug and add a regression test.",
                "steer_agent",
                plan_profiles=("coding",),
                required_actions=("workspace_mutate",),
                assistant="The bug and regression test are part of the objective.",
            ),
            T(
                "Also email me the focused test result when the coding work is complete.",
                "replace_agent_with_task_graph",
                plan_profiles=("coding", "personal-assistant", None),
                required_actions=("email_send",),
                graph=GraphExpectation(
                    required_profiles=("coding", "personal-assistant"),
                    require_coding_acceptance=True,
                    require_synthesis=True,
                ),
                assistant="The coding work and email delivery are coordinated.",
            ),
            T(
                "Also verify current GitHub public service status before the final summary.",
                "steer_task_graph",
                plan_profiles=("research", None),
                evidence_minimums=(("general_current_web", 1),),
                graph=GraphExpectation(
                    required_profiles=("research",),
                    require_synthesis=True,
                ),
                assistant="Current GitHub status is included.",
            ),
            T(
                "Try that exact request again.",
                "steer_task_graph",
                assistant="The graph is replaying.",
            ),
            T(
                "Actually, do not send the email. Just summarize everything in chat "
                "and do not run any more tools.",
                "cancel_task_graph_then_chat",
                forbidden_actions=("email_send", "workspace_execute", "research_read"),
                assistant="The graph was cancelled and summarized.",
            ),
            T(
                "Turn off the office lamp.",
                "start_agent",
                plan_profiles=("house",),
                required_actions=("home_mutate",),
            ),
        ),
    ),
    LiveScenario(
        id="depth_10_full_phase_lifecycle",
        phases=(15, 16, 17, 18, 19),
        turns=(
            T(
                "Check current Vancouver weather and my calendar, then create a "
                "tentative outdoor meeting tomorrow at 3 PM only if I am free and "
                "the weather is dry.",
                "start_task_graph",
                plan_profiles=(None,),
                required_actions=("calendar_create",),
                graph=GraphExpectation(
                    required_profiles=("research", "personal-assistant"),
                    required_edges=(("research", "personal-assistant"),),
                    require_synthesis=True,
                ),
                assistant="The weather/calendar graph is active.",
            ),
            T(
                "Also include AAPL's current price in the final summary, but do not "
                "change the calendar condition.",
                "steer_task_graph",
                plan_profiles=("trading-research", None),
                evidence_minimums=(("market_quote", 1),),
                coverage_contains=("aapl",),
                graph=GraphExpectation(
                    required_profiles=("trading-research",),
                    require_synthesis=True,
                ),
                assistant="AAPL is included.",
            ),
            T(
                "Also inspect the attached Omnix repo for the TaskGraph API contract "
                "drift guard; read only.",
                "steer_task_graph",
                plan_profiles=("coding", None),
                required_actions=("workspace_read",),
                forbidden_actions=("workspace_mutate",),
                attach_workspace=True,
                graph=GraphExpectation(
                    required_profiles=("coding",),
                    require_synthesis=True,
                ),
                assistant="The repo read is part of the graph.",
            ),
            T(
                "Also email me the final combined result when all of that is complete.",
                "steer_task_graph",
                plan_profiles=("personal-assistant", None),
                required_actions=("email_send",),
                graph=GraphExpectation(
                    required_profiles=("personal-assistant",),
                    require_synthesis=True,
                ),
                assistant="Email delivery is included.",
            ),
            T(
                "Summarize the current graph objective in chat only; do not run more tools.",
                "chat",
                forbidden_actions=("workspace_read", "market_read", "research_read", "email_send"),
                assistant="Here is the current objective summary.",
            ),
            T(
                "Try that exact graph request again.",
                "steer_task_graph",
                assistant="The graph is replaying.",
            ),
            T(
                "New task: in the attached repo, fix the failing TaskGraph API drift "
                "test and run the focused checks.",
                "replace_task_graph_with_agent",
                plan_profiles=("coding",),
                required_actions=("workspace_mutate",),
                assistant="The graph was replaced by the coding objective.",
            ),
            T(
                "One correction: keep the generated contract canonical and do not "
                "weaken the drift guard.",
                "steer_agent",
                plan_profiles=("coding",),
                assistant="The coding objective was revised without weakening the guard.",
            ),
            T(
                "Also email me the final test result after the coding checks pass.",
                "replace_agent_with_task_graph",
                plan_profiles=("coding", "personal-assistant", None),
                required_actions=("email_send",),
                graph=GraphExpectation(
                    required_profiles=("coding", "personal-assistant"),
                    require_coding_acceptance=True,
                    require_synthesis=True,
                ),
                assistant="The coding result and email delivery are coordinated.",
            ),
            T(
                "Actually, do not send anything. Just summarize the completed coding "
                "work here and do not run another tool.",
                "cancel_task_graph_then_chat",
                forbidden_actions=("email_send", "workspace_execute", "workspace_mutate"),
            ),
        ),
        notes="Full executor lifecycle: graph -> Agent -> graph -> cancelled Chat.",
    ),
)


def _enabled() -> bool:
    return (
        str(os.environ.get("OMNIX_RUN_LIVE_TASKGRAPH_PHASE_TESTS", ""))
        .strip()
        .casefold()
        in _TRUE
    )


def _bool_env(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().casefold()
    return raw in _TRUE


@pytest.fixture(scope="session")
def live_taskgraph_parser() -> ProviderSemanticTaskParser:
    if not _enabled():
        pytest.skip(
            "live TaskGraph Phase 15-19 tests are opt-in; set "
            "OMNIX_RUN_LIVE_TASKGRAPH_PHASE_TESTS=1"
        )

    codex_path = str(
        os.environ.get("OMNIX_LIVE_CODEX_PATH", "codex") or "codex"
    ).strip()
    status = ChatGPTCodexProvider.auth_status(codex_path)
    if not (
        status.get("installed")
        and status.get("authenticated")
        and status.get("auth_mode") == "chatgpt"
    ):
        pytest.fail(
            "live TaskGraph tests were explicitly enabled, but Codex is not "
            f"ChatGPT-authenticated: {status}"
        )

    provider = ChatGPTCodexProvider(
        ProviderConfig(
            provider_type="chatgpt_codex",
            model=_MODEL,
            timeout=150.0,
            extra_params={
                "codex_path": codex_path,
                "reasoning_effort": _REASONING_EFFORT,
                "fast_mode": _bool_env(
                    "OMNIX_LIVE_TASKGRAPH_FAST_MODE",
                    False,
                ),
                "transport": "app_server",
            },
        )
    )
    assert provider.config.model == _MODEL
    assert provider.reasoning_effort == _REASONING_EFFORT
    if not provider.test_connection():
        provider.close()
        pytest.fail("Codex app-server transport could not be initialized")

    old_cache = os.environ.get("OMNIX_AGENT_SEMANTIC_TASK_CACHE")
    os.environ["OMNIX_AGENT_SEMANTIC_TASK_CACHE"] = "0"
    parser = ProviderSemanticTaskParser(
        provider,
        model=_MODEL,
        timeout_seconds=120.0,
    )
    try:
        yield parser
    finally:
        provider.close()
        if old_cache is None:
            os.environ.pop("OMNIX_AGENT_SEMANTIC_TASK_CACHE", None)
        else:
            os.environ["OMNIX_AGENT_SEMANTIC_TASK_CACHE"] = old_cache


def _reference_context(messages: list[SimpleNamespace]) -> str:
    rows: list[str] = []
    for message in messages:
        role = str(getattr(message, "role", "") or "").strip().title()
        content = str(getattr(message, "content", "") or "").strip()
        if role and content:
            rows.append(f"{role}: {content}")
    return "\n".join(rows)


def _routing_environment(
    workspace,
    *,
    selected: bool,
    attached_this_turn: bool,
) -> dict:
    return {
        "active_workspace": workspace.name if selected else None,
        "workspace_source": (
            "turn_attachment"
            if attached_this_turn
            else ("configured_default" if selected else "none")
        ),
        "workspace_attached_this_turn": attached_this_turn,
        "attachment_kinds": ["local_folder"] if selected else [],
        "attachment_count": 1 if selected else 0,
        "agent_mode_selected": False,
    }


def _coverage_strings(plan: TurnPlan) -> list[str]:
    rows: list[str] = []
    for requirement in plan.compilation.evidence_decision.policy.requirements:
        rows.append(
            evidence_coverage_key(
                requirement.coverage,
                subject=requirement.subject,
            ).casefold()
        )
    return rows


def _assert_turn_semantics(
    scenario: LiveScenario,
    index: int,
    turn: LiveTurn,
    plan: TurnPlan,
) -> None:
    payload = {
        "scenario": scenario.id,
        "turn": index,
        "user": turn.user,
        "semantic_task": plan.semantic_task.model_dump(mode="json"),
        "turn_plan": plan.model_dump(mode="json"),
    }
    assert plan.semantic_task.ambiguity != "clarification_required", payload
    assert plan.run_action in turn.run_actions, {
        **payload,
        "expected_run_actions": turn.run_actions,
        "actual_run_action": plan.run_action,
    }
    if turn.plan_profiles:
        assert plan.profile_id in turn.plan_profiles, {
            **payload,
            "expected_profiles": turn.plan_profiles,
            "actual_profile": plan.profile_id,
        }

    actions = set(plan.compilation.action_intents)
    assert set(turn.required_actions) <= actions, {
        **payload,
        "missing_actions": sorted(set(turn.required_actions) - actions),
        "actual_actions": sorted(actions),
    }
    forbidden = set(turn.forbidden_actions).intersection(actions)
    assert not forbidden, {
        **payload,
        "forbidden_actions": sorted(forbidden),
        "actual_actions": sorted(actions),
    }

    requirements = plan.compilation.evidence_decision.policy.requirements
    for source_class, minimum in turn.evidence_minimums:
        actual = sum(
            requirement.source_class == source_class
            for requirement in requirements
        )
        assert actual >= minimum, {
            **payload,
            "source_class": source_class,
            "expected_minimum": minimum,
            "actual": actual,
            "requirements": [
                item.model_dump(mode="json")
                for item in requirements
            ],
        }

    coverage = _coverage_strings(plan)
    for token in turn.coverage_contains:
        needle = token.casefold()
        assert any(needle in row for row in coverage), {
            **payload,
            "missing_coverage_token": token,
            "coverage": coverage,
        }

    for source_class, freshness, minimum in turn.freshness_minimums:
        actual = sum(
            requirement.source_class == source_class
            and requirement.freshness == freshness
            for requirement in requirements
        )
        assert actual >= minimum, {
            **payload,
            "source_class": source_class,
            "freshness": freshness,
            "expected_minimum": minimum,
            "actual": actual,
        }


def _graph_profiles(graph: TaskGraph) -> set[str]:
    return {
        str(node.profile_id)
        for node in graph.nodes
        if node.profile_id is not None
    }


def _assert_graph(
    scenario: LiveScenario,
    index: int,
    expectation: GraphExpectation,
    graph: TaskGraph,
) -> None:
    payload = {
        "scenario": scenario.id,
        "turn": index,
        "graph": graph.model_dump(mode="json"),
    }
    profiles = _graph_profiles(graph)
    assert set(expectation.required_profiles) <= profiles, {
        **payload,
        "missing_profiles": sorted(
            set(expectation.required_profiles) - profiles
        ),
    }
    assert not set(expectation.forbidden_profiles).intersection(profiles), payload

    node_map = {node.id: node for node in graph.nodes}
    for source_profile, target_profile in expectation.required_edges:
        assert any(
            node_map[edge.source].profile_id == source_profile
            and node_map[edge.target].profile_id == target_profile
            for edge in graph.edges
        ), {
            **payload,
            "missing_profile_edge": [source_profile, target_profile],
        }

    for profile, capability in expectation.required_capabilities:
        matching = [
            node
            for node in graph.nodes
            if node.profile_id == profile
        ]
        assert matching, {**payload, "missing_profile": profile}
        assert any(
            capability in node.required_external_capabilities
            or capability in node.required_local_capabilities
            for node in matching
        ), {
            **payload,
            "profile": profile,
            "missing_capability": capability,
        }

    for profile, capability in expectation.forbidden_capabilities:
        matching = [
            node
            for node in graph.nodes
            if node.profile_id == profile
        ]
        assert all(
            capability not in node.required_external_capabilities
            and capability not in node.required_local_capabilities
            for node in matching
        ), {
            **payload,
            "profile": profile,
            "forbidden_capability": capability,
        }

    if expectation.require_synthesis:
        result_id = str(graph.output_contract.get("result_node") or "")
        result_node = node_map.get(result_id)
        assert result_node is not None, payload
        assert result_node.kind == "synthesis", payload
        assert result_node.profile_id is None, payload
        assert result_node.required_local_capabilities == [], payload
        assert result_node.required_external_capabilities == [], payload
        assert result_node.evidence_policy.requirement == "none", payload

    if expectation.require_coding_acceptance:
        coding_mutations = [
            node
            for node in graph.nodes
            if node.profile_id == "coding"
            and "workspace_mutate" in node.semantic_action_intents
        ]
        assert coding_mutations, {
            **payload,
            "missing_coding_mutation_node": True,
        }
        assert any(
            node.acceptance_plan is not None
            and node.acceptance_plan.require_diff is True
            and "diff" in node.acceptance_plan.required_artifacts
            and "successful_test_command" in node.acceptance_plan.checks
            for node in coding_mutations
        ), payload

    for profile in expectation.require_sensitive_approval:
        matching = [
            node
            for node in graph.nodes
            if node.profile_id == profile
        ]
        assert matching, {**payload, "missing_approval_profile": profile}
        assert all(
            node.approval_policy == "ask_sensitive"
            for node in matching
        ), payload

    for token in expectation.reference_contains:
        assert token.casefold() in graph.reference_context.casefold(), {
            **payload,
            "missing_reference_context": token,
            "reference_context": graph.reference_context,
        }

    # SemanticTask compilation currently emits only profile nodes plus
    # authority-free fan-in/synthesis nodes. Runtime-only primitives must not
    # appear accidentally as a consequence of LLM wording.
    assert {
        node.kind for node in graph.nodes
    } <= {"evidence_read", "agent", "join", "synthesis"}, payload

    before = graph.model_dump(mode="json")
    optimization = optimize_task_graph(graph)
    after = graph.model_dump(mode="json")
    assert before == after, {
        **payload,
        "optimizer_mutated_authority_graph": True,
    }

    mutation_nodes = {
        node.id
        for node in graph.nodes
        if set(node.semantic_action_intents).intersection(_MUTATING_ACTIONS)
    }
    assert not mutation_nodes.intersection(optimization.cache_keys), payload
    assert not mutation_nodes.intersection(optimization.speculative_read_nodes), payload

    if expectation.optimizer_batch_min_requirements:
        assert any(
            len(batch.requirement_ids)
            >= expectation.optimizer_batch_min_requirements
            for batch in optimization.evidence_batches
        ), {
            **payload,
            "expected_batch_requirement_count": (
                expectation.optimizer_batch_min_requirements
            ),
            "evidence_batches": [
                item.model_dump(mode="json")
                for item in optimization.evidence_batches
            ],
        }


def _compile_graph_for_turn(
    *,
    turn: LiveTurn,
    plan: TurnPlan,
    active_objective: ActiveObjective | None,
    current_graph: TaskGraph | None,
    reference_context: str,
    workspace_spec: WorkspaceSpec | None,
    parser: ProviderSemanticTaskParser,
    routing_environment: dict,
) -> tuple[TaskGraph | None, str | None]:
    if plan.run_action == "steer_task_graph" and plan.disposition == "replay_objective":
        assert current_graph is not None
        replay = current_graph.model_copy(
            update={
                "revision": current_graph.revision + 1,
                "reference_context": (
                    reference_context
                    or current_graph.reference_context
                )[:12000],
            }
        )
        return replay, None

    graph_request = turn.user
    graph_task = plan.semantic_task
    if (
        plan.run_action == "replace_agent_with_task_graph"
        and active_objective is not None
    ):
        graph_request = derive_effective_objective(
            active_objective.effective_objective_text(),
            plan,
        )
        graph_task = parser.parse_contextual(
            graph_request,
            reference_context=reference_context,
            previous_objective="",
            current_environment=routing_environment,
        )

    compilation = compile_task_graph(
        graph_request,
        graph_task,
        model=ModelRef(
            provider_id="chatgpt_codex",
            model_id=_MODEL,
            reasoning_effort=_REASONING_EFFORT,
        ),
        workspace=workspace_spec,
        reference_context=reference_context,
    )
    if not compilation.ok or compilation.graph is None:
        code = (
            compilation.anomalies[0].code
            if compilation.anomalies
            else "task_graph_compilation_failed"
        )
        return None, code

    graph = compilation.graph
    if plan.run_action == "steer_task_graph" and current_graph is not None:
        if plan.relation == "continue":
            graph = merge_task_graph_continuation(
                current_graph,
                graph,
                context_dependent=(
                    plan.semantic_task.request_completeness
                    == "context_dependent"
                ),
            )
        else:
            graph = graph.model_copy(
                update={
                    "graph_id": current_graph.graph_id,
                    "revision": current_graph.revision + 1,
                }
            )
    return graph, None


def _next_objective(
    *,
    scenario: LiveScenario,
    index: int,
    plan: TurnPlan,
    active: ActiveObjective | None,
    graph_succeeded: bool,
    workspace_name: str | None,
) -> ActiveObjective | None:
    if plan.run_action == "cancel_task_graph_then_chat":
        return None
    if plan.run_action in _GRAPH_ACTIONS:
        if not graph_succeeded:
            return active
        run_id = (
            active.run_id
            if plan.run_action == "steer_task_graph"
            and active is not None
            else f"live:{scenario.id}:graph:{index}"
        )
        return advance_active_objective(
            active,
            request=plan.latest_request,
            profile="task-graph",
            relation=plan.relation,
            disposition=plan.disposition,
            turn_id=f"{scenario.id}:turn:{index}",
            run_id=run_id,
            status="active",
            workspace_name=workspace_name,
        )
    if plan.run_action in _AGENT_START_ACTIONS:
        return advance_active_objective(
            active,
            request=plan.latest_request,
            profile=str(plan.profile_id or "unknown"),
            relation=(
                plan.relation
                if plan.run_action == "steer_agent"
                else "none"
            ),
            disposition=(
                plan.disposition
                if plan.run_action == "steer_agent"
                else "new_objective"
            ),
            turn_id=f"{scenario.id}:turn:{index}",
            run_id=f"live:{scenario.id}:agent:{index}",
            status="active",
            workspace_name=workspace_name,
        )
    if plan.run_action == "steer_agent":
        assert active is not None
        return advance_active_objective(
            active,
            request=plan.latest_request,
            profile=str(plan.profile_id or active.profile or "unknown"),
            relation=plan.relation,
            disposition=plan.disposition,
            turn_id=f"{scenario.id}:turn:{index}",
            run_id=active.run_id,
            status="active",
            workspace_name=workspace_name,
        )
    return active


@pytest.mark.live_codex
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.id)
def test_live_luna_taskgraph_phases_15_19(
    scenario: LiveScenario,
    live_taskgraph_parser: ProviderSemanticTaskParser,
    tmp_path,
) -> None:
    selected = str(
        os.environ.get("OMNIX_LIVE_TASKGRAPH_SCENARIO", "")
        or ""
    ).strip()
    if selected and selected != scenario.id:
        pytest.skip(f"filtered to {selected}")

    workspace = tmp_path / "omnix-live-taskgraph"
    workspace.mkdir(exist_ok=True)
    workspace_spec = WorkspaceSpec(
        root=str(workspace),
        repository=str(workspace),
        base_ref="HEAD",
    )

    messages: list[SimpleNamespace] = []
    active_objective: ActiveObjective | None = None
    current_graph: TaskGraph | None = None
    workspace_selected = False

    for index, turn in enumerate(scenario.turns, start=1):
        workspace_selected = workspace_selected or turn.attach_workspace
        reference_context = _reference_context(messages)
        environment = _routing_environment(
            workspace,
            selected=workspace_selected,
            attached_this_turn=turn.attach_workspace,
        )

        task = live_taskgraph_parser.parse_contextual(
            turn.user,
            reference_context=reference_context,
            previous_objective=(
                active_objective.reference_text()
                if active_objective is not None
                else ""
            ),
            current_environment=environment,
        )
        plan = compile_turn_plan(
            turn.user,
            task,
            active_objective=active_objective,
            routing_environment=environment,
        )
        _assert_turn_semantics(scenario, index, turn, plan)

        graph: TaskGraph | None = None
        graph_error: str | None = None
        should_compile_graph = (
            turn.graph is not None
            or plan.run_action in _GRAPH_ACTIONS
        )
        if should_compile_graph:
            graph, graph_error = _compile_graph_for_turn(
                turn=turn,
                plan=plan,
                active_objective=active_objective,
                current_graph=current_graph,
                reference_context=reference_context,
                workspace_spec=(
                    workspace_spec if workspace_selected else None
                ),
                parser=live_taskgraph_parser,
                routing_environment=environment,
            )

            if turn.graph is not None and turn.graph.expected_anomaly is not None:
                assert graph is None, {
                    "scenario": scenario.id,
                    "turn": index,
                    "expected_anomaly": turn.graph.expected_anomaly,
                    "graph": (
                        graph.model_dump(mode="json")
                        if graph is not None
                        else None
                    ),
                }
                assert graph_error == turn.graph.expected_anomaly
            else:
                assert graph is not None, {
                    "scenario": scenario.id,
                    "turn": index,
                    "graph_error": graph_error,
                    "semantic_task": plan.semantic_task.model_dump(
                        mode="json"
                    ),
                    "turn_plan": plan.model_dump(mode="json"),
                }
                if turn.graph is not None:
                    _assert_graph(
                        scenario,
                        index,
                        turn.graph,
                        graph,
                    )

        graph_succeeded = graph is not None or not should_compile_graph
        active_objective = _next_objective(
            scenario=scenario,
            index=index,
            plan=plan,
            active=active_objective,
            graph_succeeded=graph_succeeded,
            workspace_name=(
                workspace.name if workspace_selected else None
            ),
        )

        if plan.run_action in _GRAPH_ACTIONS and graph is not None:
            current_graph = graph
        elif plan.run_action in {
            "replace_task_graph_with_agent",
            "cancel_task_graph_then_chat",
        }:
            current_graph = None

        messages.append(
            SimpleNamespace(
                role="user",
                content=turn.user,
            )
        )
        messages.append(
            SimpleNamespace(
                role="assistant",
                content=turn.assistant,
            )
        )


def test_live_taskgraph_matrix_covers_every_conversation_depth_1_to_10() -> None:
    assert {len(scenario.turns) for scenario in SCENARIOS} == set(range(1, 11))


def test_live_taskgraph_matrix_covers_all_new_architecture_phases() -> None:
    assert {
        phase
        for scenario in SCENARIOS
        for phase in scenario.phases
    } == {15, 16, 17, 18, 19}
    assert any(
        turn.graph is not None
        and turn.graph.require_coding_acceptance
        for scenario in SCENARIOS
        for turn in scenario.turns
    )
    assert any(
        turn.graph is not None
        and turn.graph.optimizer_batch_min_requirements >= 2
        for scenario in SCENARIOS
        for turn in scenario.turns
    )
    assert any(
        "cancel_task_graph_then_chat" in turn.run_actions
        for scenario in SCENARIOS
        for turn in scenario.turns
    )
    assert any(
        "replace_agent_with_task_graph" in turn.run_actions
        for scenario in SCENARIOS
        for turn in scenario.turns
    )


class _FirstTaskThenLiveParser:
    """Reuse the already-paid latest-turn parse, then delegate reparses to Luna."""

    def __init__(
        self,
        task: SemanticTask,
        live_parser: ProviderSemanticTaskParser,
    ) -> None:
        self.task = task
        self.live_parser = live_parser
        self.calls = 0

    def parse_contextual(self, content: str, **kwargs) -> SemanticTask:
        self.calls += 1
        if self.calls == 1:
            return self.task
        return self.live_parser.parse_contextual(content, **kwargs)


class _RecordingAgentService:
    def __init__(self) -> None:
        self.runs: dict[str, SimpleNamespace] = {}
        self.starts = []
        self.commands = []
        self.reference_contexts: list[tuple[str, str]] = []

    def get(self, run_id):
        return self.runs.get(run_id)

    def start_with_context(self, spec, *, reference_context="", **_kwargs):
        self.starts.append(spec)
        self.reference_contexts.append(
            (spec.run_id, str(reference_context or ""))
        )
        snapshot = SimpleNamespace(
            run_id=spec.run_id,
            status="running",
            revision=1,
            last_error=None,
            superseded_by_run_id=None,
            spec=spec,
        )
        self.runs[spec.run_id] = snapshot
        return snapshot

    def start(self, spec):
        return self.start_with_context(spec)

    def command_with_context(
        self,
        command,
        *,
        reference_context="",
        **_kwargs,
    ):
        self.commands.append(command)
        self.reference_contexts.append(
            (command.run_id, str(reference_context or ""))
        )
        snapshot = self.runs[command.run_id]
        if command.command_type == "cancel":
            snapshot.status = "cancelled"
        else:
            snapshot.revision += 1
        return snapshot

    def command(self, command):
        return self.command_with_context(command)

    def approvals(self, _run_id, *, state=None):
        return []


class _RecordingTaskGraphRuntime:
    def __init__(self) -> None:
        self.runs: dict[str, TaskGraphRunSnapshot] = {}
        self.starts: list[TaskGraph] = []
        self.revisions: list[dict[str, object]] = []
        self.cancellations: list[tuple[str, str]] = []

    @staticmethod
    def _states(graph: TaskGraph) -> list[TaskNodeRunState]:
        return [
            TaskNodeRunState(
                node_id=node.id,
                status="pending",
                fingerprint=task_node_fingerprint(node),
            )
            for node in graph.nodes
        ]

    def start(self, graph: TaskGraph) -> TaskGraphRunSnapshot:
        run_id = f"recording-graph-{len(self.starts) + 1}"
        self.starts.append(graph)
        snapshot = TaskGraphRunSnapshot(
            run_id=run_id,
            graph=graph,
            status="running",
            revision=graph.revision,
            node_states=self._states(graph),
        )
        self.runs[run_id] = snapshot
        return snapshot

    def get_status(self, run_id: str) -> TaskGraphRunSnapshot | None:
        return self.runs.get(run_id)

    def revise(
        self,
        run_id: str,
        revised_graph: TaskGraph,
        *,
        user_instruction: str,
        reuse_completed: bool = True,
    ) -> TaskGraphRunSnapshot:
        previous = self.runs[run_id]
        graph = revised_graph.model_copy(
            update={
                "graph_id": previous.graph.graph_id,
                "revision": previous.graph.revision + 1,
            }
        )
        self.revisions.append(
            {
                "run_id": run_id,
                "user_instruction": user_instruction,
                "reuse_completed": reuse_completed,
                "graph": graph,
            }
        )
        snapshot = TaskGraphRunSnapshot(
            run_id=run_id,
            graph=graph,
            status="running",
            revision=graph.revision,
            node_states=self._states(graph),
        )
        self.runs[run_id] = snapshot
        return snapshot

    def cancel(
        self,
        run_id: str,
        *,
        reason: str = "user_cancelled",
    ) -> TaskGraphRunSnapshot:
        previous = self.runs[run_id]
        self.cancellations.append((run_id, reason))
        snapshot = previous.model_copy(update={"status": "cancelled"})
        self.runs[run_id] = snapshot
        return snapshot


def _run_live_bridge_turn(
    *,
    session,
    parser: ProviderSemanticTaskParser,
    user: str,
    workspace_root: str | None = None,
):
    reference_context = _reference_context(session.messages)
    active = None
    for message in reversed(session.messages):
        raw = (getattr(message, "metadata", {}) or {}).get(
            "active_objective"
        )
        if isinstance(raw, dict):
            try:
                candidate = ActiveObjective.model_validate(raw)
            except Exception:
                continue
            if candidate.status not in {
                "completed",
                "abandoned",
                "cancelled",
            }:
                active = candidate
            break

    environment = {
        "active_workspace": (
            os.path.basename(workspace_root)
            if workspace_root
            else None
        ),
        "workspace_source": (
            "turn_attachment" if workspace_root else "none"
        ),
        "workspace_attached_this_turn": bool(workspace_root),
        "attachment_kinds": (
            ["local_folder"] if workspace_root else []
        ),
        "attachment_count": 1 if workspace_root else 0,
        "agent_mode_selected": False,
    }
    task = parser.parse_contextual(
        user,
        reference_context=reference_context,
        previous_objective=(
            active.reference_text() if active is not None else ""
        ),
        current_environment=environment,
    )
    metadata = {}
    if workspace_root:
        metadata["workspace_root"] = workspace_root
    user_message = SimpleNamespace(
        id=f"bridge:user:{len(session.messages)}",
        role="user",
        content=user,
        metadata=metadata,
    )
    session.messages.append(user_message)
    result = route_typed_chat_turn(
        session,
        user_message,
        provider_id="chatgpt_codex",
        model_id=_MODEL,
        semantic_classifier=_FirstTaskThenLiveParser(task, parser),
        routing_context_factory=lambda: SimpleNamespace(
            reference_context=reference_context
        ),
    )
    assistant_metadata = (
        dict(result.metadata) if result is not None else {}
    )
    session.messages.append(
        SimpleNamespace(
            id=f"bridge:assistant:{len(session.messages)}",
            role="assistant",
            content=(
                result.content if result is not None else "Understood."
            ),
            metadata=assistant_metadata,
        )
    )
    return task, user_message, result


@pytest.mark.live_codex
def test_live_bridge_replaces_graph_with_agent_then_agent_with_graph(
    live_taskgraph_parser: ProviderSemanticTaskParser,
    monkeypatch,
    tmp_path,
) -> None:
    workspace = tmp_path / "omnix-bridge"
    workspace.mkdir()
    agent_service = _RecordingAgentService()
    graph_runtime = _RecordingTaskGraphRuntime()
    monkeypatch.setattr(
        chat_bridge,
        "default_agent_run_service",
        lambda: agent_service,
    )
    monkeypatch.setattr(
        chat_bridge,
        "default_task_graph_runtime",
        lambda: graph_runtime,
    )
    monkeypatch.setattr(
        chat_bridge,
        "_enforce_chat_evidence",
        lambda *_a, **_k: None,
    )
    monkeypatch.setenv("OMNIX_AGENT_REASONING_EFFORT", _REASONING_EFFORT)

    session = SimpleNamespace(
        id="live-taskgraph-bridge-supersession",
        provider_id="chatgpt_codex",
        model_id=_MODEL,
        messages=[],
    )

    _task1, _message1, result1 = _run_live_bridge_turn(
        session=session,
        parser=live_taskgraph_parser,
        user="Get MSFT's current market price, then email that exact price to me.",
    )
    assert result1 is not None
    assert result1.metadata.get("task_graph_mode") is True
    assert len(graph_runtime.starts) == 1
    first_graph_run = str(
        result1.metadata["task_graph_run"]["run_id"]
    )

    _task2, _message2, result2 = _run_live_bridge_turn(
        session=session,
        parser=live_taskgraph_parser,
        user=(
            "New task: in the attached Omnix repo, fix the failing "
            "TaskGraph recovery test and run the focused tests."
        ),
        workspace_root=str(workspace),
    )
    assert result2 is not None
    assert result2.metadata.get("task_graph_mode") is not True
    assert len(agent_service.starts) == 1
    assert graph_runtime.cancellations[-1][0] == first_graph_run
    first_agent_run = str(result2.metadata["agent_run"]["run_id"])

    _task3, _message3, result3 = _run_live_bridge_turn(
        session=session,
        parser=live_taskgraph_parser,
        user=(
            "Continue that coding task, and also email me the final "
            "focused-test result when it is done."
        ),
        workspace_root=str(workspace),
    )
    assert result3 is not None
    assert result3.metadata.get("task_graph_mode") is True
    assert len(graph_runtime.starts) == 2
    assert any(
        command.run_id == first_agent_run
        and command.command_type == "cancel"
        for command in agent_service.commands
    )
    profiles = _graph_profiles(graph_runtime.starts[-1])
    assert {"coding", "personal-assistant"} <= profiles


@pytest.mark.live_codex
def test_live_bridge_cancelled_graph_is_not_resurrected(
    live_taskgraph_parser: ProviderSemanticTaskParser,
    monkeypatch,
) -> None:
    agent_service = _RecordingAgentService()
    graph_runtime = _RecordingTaskGraphRuntime()
    monkeypatch.setattr(
        chat_bridge,
        "default_agent_run_service",
        lambda: agent_service,
    )
    monkeypatch.setattr(
        chat_bridge,
        "default_task_graph_runtime",
        lambda: graph_runtime,
    )
    monkeypatch.setattr(
        chat_bridge,
        "_enforce_chat_evidence",
        lambda *_a, **_k: None,
    )

    session = SimpleNamespace(
        id="live-taskgraph-bridge-cancel",
        provider_id="chatgpt_codex",
        model_id=_MODEL,
        messages=[],
    )

    _task1, _message1, result1 = _run_live_bridge_turn(
        session=session,
        parser=live_taskgraph_parser,
        user="Get AAPL's current price, then email that exact price to me.",
    )
    assert result1 is not None
    graph_run_id = str(
        result1.metadata["task_graph_run"]["run_id"]
    )

    _task2, cancel_message, result2 = _run_live_bridge_turn(
        session=session,
        parser=live_taskgraph_parser,
        user=(
            "Actually, do not send any email or take any action. Just "
            "explain the AAPL price already obtained above; do not re-check it."
        ),
    )
    assert result2 is None
    assert graph_runtime.cancellations[-1][0] == graph_run_id
    assert (
        cancel_message.metadata["active_objective"]["status"]
        == "cancelled"
    )

    _task3, _message3, result3 = _run_live_bridge_turn(
        session=session,
        parser=live_taskgraph_parser,
        user="Email that explanation to me now.",
    )
    assert result3 is not None
    assert result3.metadata.get("task_graph_mode") is not True
    assert len(graph_runtime.starts) == 1
    assert graph_runtime.revisions == []
    assert len(agent_service.starts) == 1
    assert (
        result3.metadata["agent_run"]["run_id"]
        != graph_run_id
    )


@pytest.mark.live_codex
def test_live_bridge_opaque_retry_replays_existing_graph(
    live_taskgraph_parser: ProviderSemanticTaskParser,
    monkeypatch,
) -> None:
    agent_service = _RecordingAgentService()
    graph_runtime = _RecordingTaskGraphRuntime()
    monkeypatch.setattr(
        chat_bridge,
        "default_agent_run_service",
        lambda: agent_service,
    )
    monkeypatch.setattr(
        chat_bridge,
        "default_task_graph_runtime",
        lambda: graph_runtime,
    )
    monkeypatch.setattr(
        chat_bridge,
        "_enforce_chat_evidence",
        lambda *_a, **_k: None,
    )

    session = SimpleNamespace(
        id="live-taskgraph-bridge-replay",
        provider_id="chatgpt_codex",
        model_id=_MODEL,
        messages=[],
    )

    _task1, _message1, result1 = _run_live_bridge_turn(
        session=session,
        parser=live_taskgraph_parser,
        user=(
            "Get GME's current price and Vancouver weather, then email me one "
            "combined summary after both observations are available."
        ),
    )
    assert result1 is not None
    assert result1.metadata.get("task_graph_mode") is True
    run_id = str(result1.metadata["task_graph_run"]["run_id"])

    _task2, _message2, result2 = _run_live_bridge_turn(
        session=session,
        parser=live_taskgraph_parser,
        user="Try that exact request again.",
    )
    assert result2 is not None
    assert result2.metadata.get("task_graph_mode") is True
    assert len(graph_runtime.starts) == 1
    assert len(graph_runtime.revisions) == 1
    revision = graph_runtime.revisions[0]
    assert revision["run_id"] == run_id
    assert revision["reuse_completed"] is False
