"""Comprehensive opt-in live LLM conversation matrix for Agent routing.

The suite uses the real ChatGPT-authenticated Codex provider with GPT-5.6 Luna
at high reasoning effort.  It exercises single-turn and 2-10 turn conversations,
including clarification, implementation, repeated refinement, read-only
diagnosis, authority narrowing, and request-continuity behavior.

It deliberately does not execute home, web, trading, or workspace tools.  The
live model performs SemanticTask v2 classification; a recording Agent service
captures the RunSpec or steering command that Omnix would hand to execution.

PowerShell:

    $env:OMNIX_RUN_LIVE_AGENT_CONVERSATION_TESTS="1"
    python -m pytest src/tests/agent_runtime/test_live_agent_conversation_matrix.py -q --tb=short

Optional filters:

    $env:OMNIX_LIVE_AGENT_CONVERSATION_DOMAIN="coding"
    $env:OMNIX_LIVE_AGENT_CONVERSATION_SCENARIO="coding_05"
    $env:OMNIX_LIVE_CODEX_PATH="codex"
    $env:OMNIX_LIVE_AGENT_FAST_MODE="0"

The model and reasoning effort are intentionally fixed by this contract:
GPT-5.6 Luna + high.  Change them only by changing this test explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from types import SimpleNamespace
from typing import Literal

import pytest

from app.agent_runtime import chat_bridge
from app.agent_runtime.active_objective import ActiveObjective
from app.agent_runtime.chat_bridge import route_typed_chat_turn
from app.agent_runtime.evidence import compile_task_authority
from app.agent_runtime.profiles import get_agent_profile
from app.agent_runtime.semantic_task import SemanticTask
from app.agent_runtime.semantic_task_parser import ProviderSemanticTaskParser
from app.agent_runtime.turn_plan import TurnPlan, compile_turn_plan
from app.providers import ChatGPTCodexProvider, ProviderConfig


_TRUE = {"1", "true", "yes", "on"}
_MODEL = "gpt-5.6-luna"
_REASONING_EFFORT = "high"
_HANDOFF = Literal["none", "latest", "previous"]


@dataclass(frozen=True)
class ConversationTurn:
    user: str
    lane: Literal["chat", "agent"]
    profile: str | None = None
    required_actions: tuple[str, ...] = ()
    action_any_of: tuple[tuple[str, ...], ...] = ()
    forbidden_actions: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    evidence_any_of: tuple[str, ...] = ()
    forbidden_evidence: tuple[str, ...] = ()
    relations: tuple[str, ...] = ()
    handoff: _HANDOFF = "none"
    assistant: str = "Understood."
    attach_workspace: bool = False
    expected_request: str | None = None


@dataclass(frozen=True)
class ConversationScenario:
    id: str
    domain: Literal["coding", "smarthome", "web", "trading"]
    turns: tuple[ConversationTurn, ...]
    notes: str = ""


def C(user: str, assistant: str = "Understood.", **kwargs) -> ConversationTurn:
    return ConversationTurn(user=user, lane="chat", assistant=assistant, **kwargs)


def A(
    user: str,
    profile: str,
    *actions: str,
    assistant: str = "Agent accepted the request.",
    handoff: _HANDOFF = "latest",
    **kwargs,
) -> ConversationTurn:
    return ConversationTurn(
        user=user,
        lane="agent",
        profile=profile,
        required_actions=tuple(actions),
        handoff=handoff,
        assistant=assistant,
        **kwargs,
    )


def Q(
    user: str,
    profile: str,
    *actions: str,
    assistant: str = "Here is the current answer.",
    **kwargs,
) -> ConversationTurn:
    """Bounded current-data Chat: semantic read + governed evidence, no Agent run."""
    return ConversationTurn(
        user=user,
        lane="chat",
        profile=profile,
        required_actions=tuple(actions),
        handoff="none",
        assistant=assistant,
        **kwargs,
    )


SCENARIOS: tuple[ConversationScenario, ...] = (
    # ------------------------------------------------------------------
    # Coding.  These intentionally cover every conversation length 1..10.
    # ------------------------------------------------------------------
    ConversationScenario(
        "coding_01_single_ui_fix",
        "coding",
        (
            A(
                "In the attached Omnix workspace, fix the clipped text in the system-mode profile dropdown and run the focused web tests.",
                "coding",
                "workspace_mutate",
                action_any_of=(("workspace_execute", "workspace_read"),),
                attach_workspace=True,
            ),
        ),
    ),
    ConversationScenario(
        "coding_02_discuss_then_implement",
        "coding",
        (
            C(
                "Conceptually, what makes a settings panel easier to scan without making it feel sparse?",
                "A useful approach is stronger grouping, consistent spacing, and restrained hierarchy.",
                forbidden_actions=("workspace_read", "workspace_mutate", "workspace_execute"),
            ),
            A(
                "Good. Apply that idea to the settings panel in the attached Omnix workspace, keep dark mode unchanged, and add a regression test.",
                "coding",
                "workspace_mutate",
                attach_workspace=True,
            ),
        ),
    ),
    ConversationScenario(
        "coding_03_read_only_then_fix",
        "coding",
        (
            A(
                "Inspect the attached repo and diagnose why the selected Local folder chip disappears after sending a message. Do not edit anything yet.",
                "coding",
                "workspace_read",
                forbidden_actions=("workspace_mutate",),
                attach_workspace=True,
                assistant="The likely issue is state replacement in the composer lifecycle.",
            ),
            A(
                "Before changing it, explain the tradeoff between keeping that state locally versus lifting it higher.",
                "coding",
                relations=("continue", "revise"),
                assistant="Local state is simpler; lifted state survives component lifecycle changes more reliably.",
                forbidden_actions=("workspace_mutate",),
            ),
            A(
                "Implement the safer fix now and run the focused tests.",
                "coding",
                "workspace_mutate",
                relations=("revise", "continue"),
            ),
        ),
    ),
    ConversationScenario(
        "coding_04_playwright_web_test_then_fix",
        "coding",
        (
            C(
                "For a React app, what should a good Playwright smoke test verify on a login page?",
                "It should verify rendering, form interaction, submission, navigation, and key accessibility behavior.",
                forbidden_actions=("workspace_read", "workspace_mutate", "workspace_execute"),
            ),
            A(
                "In the attached workspace, run the existing Playwright login smoke test and report the failure without editing files.",
                "coding",
                "workspace_execute",
                forbidden_actions=("workspace_mutate",),
                attach_workspace=True,
                assistant="The smoke test fails because the submit button becomes detached during the transition.",
            ),
            A(
                "Fix that implementation issue, but do not broaden the test timeout.",
                "coding",
                "workspace_mutate",
                relations=("revise", "continue"),
                assistant="The implementation has been corrected without changing the timeout.",
            ),
            A(
                "Now rerun the focused Playwright test and the component test for the login form.",
                "coding",
                "workspace_execute",
                forbidden_actions=("workspace_mutate",),
                relations=("continue", "revise"),
            ),
        ),
    ),
    ConversationScenario(
        "coding_05_multiple_refinements",
        "coding",
        (
            A(
                "In the attached workspace, make the chat composer remember the selected Local folder after a message is sent.",
                "coding",
                "workspace_mutate",
                attach_workspace=True,
                assistant="The selected folder is now preserved across sends.",
            ),
            A(
                "Also keep it when switching between system and character mode.",
                "coding",
                "workspace_mutate",
                relations=("continue",),
                assistant="Mode switching now preserves it too.",
            ),
            A(
                "Actually, clear it when the user explicitly starts a brand-new chat, but not when they only switch modes.",
                "coding",
                "workspace_mutate",
                relations=("revise", "continue"),
                assistant="New-chat reset now clears it while mode switching does not.",
            ),
            A(
                "Add regression coverage for all three behaviors.",
                "coding",
                "workspace_mutate",
                relations=("continue",),
                assistant="Regression coverage was added.",
            ),
            A(
                "One correction: the new-chat reset must happen after the session is created, not before. Fix that and rerun the focused tests.",
                "coding",
                "workspace_mutate",
                action_any_of=(("workspace_execute", "workspace_read"),),
                relations=("revise", "continue"),
            ),
        ),
        notes="Explicit five-turn case with several coding requests and corrections.",
    ),
    ConversationScenario(
        "coding_06_narrow_then_expand_authority",
        "coding",
        (
            C(
                "What kinds of mistakes usually cause semantic routing regressions?",
                "Common causes include overloaded keywords, stale context, and authority being inferred from text heuristics.",
                forbidden_actions=("workspace_read", "workspace_mutate"),
            ),
            A(
                "Inspect the attached agent router for those risks. Read only; no changes and no tests yet.",
                "coding",
                "workspace_read",
                forbidden_actions=("workspace_mutate", "workspace_execute"),
                attach_workspace=True,
                assistant="I found a risky fallback around ambiguous UI language.",
            ),
            A(
                "Run the existing router classification tests, still without editing anything.",
                "coding",
                "workspace_execute",
                forbidden_actions=("workspace_mutate",),
                relations=("continue", "revise"),
                assistant="The focused classification test exposes the fallback.",
            ),
            A(
                "Implement the smallest fix for that fallback.",
                "coding",
                "workspace_mutate",
                relations=("revise", "continue"),
                assistant="The fallback has been corrected.",
            ),
            A(
                "Add cases for light mode, bedroom light, and a quoted command so the meanings cannot collide.",
                "coding",
                "workspace_mutate",
                relations=("continue",),
                assistant="Those regression cases were added.",
            ),
            A(
                "Run the complete agent-runtime routing subset and report any remaining failures without making unrelated changes.",
                "coding",
                "workspace_execute",
                forbidden_actions=("workspace_mutate",),
                relations=("continue", "revise"),
            ),
        ),
    ),
    ConversationScenario(
        "coding_07_light_mode_context_not_home",
        "coding",
        (
            C(
                "Why can the phrase light mode be dangerous in a router that also controls smart lights?",
                "Because the same token can refer to a UI theme or a physical device.",
                forbidden_actions=("home_read", "home_mutate", "workspace_mutate"),
            ),
            C(
                "Suppose the app is called Omnix and I mention Aurora. What context matters most?",
                "UI, theme, stylesheet, page, component, and project context should dominate the word light.",
                forbidden_actions=("home_read", "home_mutate"),
            ),
            A(
                "Inspect the attached workspace and see whether Aurora light mode still has unreadable assistant-run text. Do not change it yet.",
                "coding",
                "workspace_read",
                forbidden_actions=("home_read", "home_mutate", "workspace_mutate"),
                attach_workspace=True,
                assistant="The run card still uses a dark-oriented muted text value in one state.",
            ),
            A(
                "Fix it while preserving dark mode.",
                "coding",
                "workspace_mutate",
                forbidden_actions=("home_read", "home_mutate"),
                relations=("revise", "continue"),
                assistant="The light-mode contrast is corrected while dark mode remains unchanged.",
            ),
            A(
                "Apply the same readability rule to the related run detail rows.",
                "coding",
                "workspace_mutate",
                relations=("continue",),
                assistant="The related detail rows now follow the same rule.",
            ),
            A(
                "Add a light-mode regression test that would have caught both problems.",
                "coding",
                "workspace_mutate",
                relations=("continue",),
                assistant="A regression test now covers both surfaces.",
            ),
            A(
                "Rerun the focused web tests and typecheck; do not edit anything else.",
                "coding",
                "workspace_execute",
                forbidden_actions=("workspace_mutate",),
                relations=("continue", "revise", "resume"),
            ),
        ),
    ),
    ConversationScenario(
        "coding_08_ci_diagnose_correct_validate",
        "coding",
        (
            C(
                "What is the safest order for investigating a CI failure before changing code?",
                "Inspect the exact failed job, reproduce the focused failure, then change only the proven cause.",
                forbidden_actions=("workspace_read", "workspace_mutate", "workspace_execute"),
            ),
            A(
                "Check the current CI state for the attached repo and diagnose the Agent Runtime failure. Do not edit yet.",
                "coding",
                "workspace_read",
                action_any_of=(("workspace_execute", "workspace_read"),),
                required_evidence=("repo_ci_state",),
                forbidden_actions=("workspace_mutate",),
                attach_workspace=True,
                assistant="The failure points to a stale routing assertion.",
            ),
            A(
                "Reproduce that exact failure locally without changing files.",
                "coding",
                "workspace_execute",
                forbidden_actions=("workspace_mutate",),
                relations=("continue", "revise"),
                assistant="The focused local test reproduces it.",
            ),
            A(
                "Fix the stale assertion and any production bug it exposes, but do not touch unrelated routing behavior.",
                "coding",
                "workspace_mutate",
                relations=("revise", "continue"),
                assistant="The assertion and underlying narrow bug are fixed.",
            ),
            A(
                "Run the focused test again.",
                "coding",
                "workspace_execute",
                forbidden_actions=("workspace_mutate",),
                relations=("continue", "resume"),
                assistant="The focused test now passes.",
            ),
            A(
                "Now run the surrounding semantic-task and handoff tests too.",
                "coding",
                "workspace_execute",
                forbidden_actions=("workspace_mutate",),
                relations=("continue",),
                assistant="The surrounding tests pass.",
            ),
            A(
                "Review the resulting diff for accidental authority widening. Do not edit during this pass.",
                "coding",
                "workspace_read",
                forbidden_actions=("workspace_mutate",),
                relations=("continue", "revise"),
                assistant="The diff stays inside the intended authority boundary.",
            ),
            A(
                "If the diff is clean, run the agent-runtime typecheck and final focused suite once more.",
                "coding",
                "workspace_execute",
                forbidden_actions=("workspace_mutate",),
                relations=("continue",),
            ),
        ),
    ),
    ConversationScenario(
        "coding_09_long_clarify_and_resume",
        "coding",
        (
            C(
                "I want the chat header to feel less crowded, but I am not asking for code changes yet. What options would you consider?",
                "I would first reduce competing controls, tighten hierarchy, and preserve the highest-frequency actions.",
                forbidden_actions=("workspace_read", "workspace_mutate"),
            ),
            C(
                "The mode selector and voice selector both need to stay visible.",
                "Then the best gains are likely spacing, grouping, and reducing secondary chrome.",
                forbidden_actions=("workspace_mutate",),
            ),
            C(
                "The New Chat button also has to remain one click away.",
                "That still leaves room to simplify labels and consolidate lower-priority controls.",
                forbidden_actions=("workspace_mutate",),
            ),
            A(
                "Implement that direction in the attached Omnix workspace: keep those three controls visible and reduce the header crowding without changing behavior.",
                "coding",
                "workspace_mutate",
                attach_workspace=True,
                assistant="The header layout is simplified while all three controls stay visible.",
            ),
            A(
                "The spacing around the voice selector is still too wide. Tighten just that area.",
                "coding",
                "workspace_mutate",
                relations=("revise", "continue"),
                assistant="The voice-selector spacing is tighter.",
            ),
            A(
                "Do not shrink the New Chat hit target though.",
                "coding",
                relations=("continue", "revise"),
                assistant="The hit target remains unchanged.",
            ),
            A(
                "Add responsive coverage for the narrow desktop width.",
                "coding",
                "workspace_mutate",
                relations=("continue",),
                assistant="Responsive coverage was added.",
            ),
            A(
                "Run the relevant tests and typecheck without further edits.",
                "coding",
                "workspace_execute",
                forbidden_actions=("workspace_mutate",),
                relations=("continue", "revise"),
                assistant="The relevant checks pass.",
            ),
            A(
                "Try that exact implementation request again.",
                "coding",
                "workspace_mutate",
                handoff="previous",
                expected_request=(
                    "Implement that direction in the attached Omnix workspace: keep those "
                    "three controls visible and reduce the header crowding without changing behavior."
                ),
                relations=("resume",),
            ),
        ),
    ),
    ConversationScenario(
        "coding_10_feature_build_refine_correct",
        "coding",
        (
            C(
                "For a tabbed trading chart UI, what state should belong to each tab versus globally?",
                "Per-tab state should hold symbol, interval, drawings, and view state; global state should hold account and shared preferences.",
                forbidden_actions=("workspace_read", "workspace_mutate"),
            ),
            C(
                "I also want switching tabs to feel instant.",
                "Keep tab state in memory and avoid refetching data that is still fresh.",
                forbidden_actions=("workspace_mutate",),
            ),
            A(
                "Implement per-tab chart session state in the attached workspace with symbol, interval, and drawing state isolated per tab.",
                "coding",
                "workspace_mutate",
                attach_workspace=True,
                assistant="Each chart tab now owns its own session state.",
            ),
            A(
                "Add a plus button for a new chart tab and keep the current tab selected after a symbol change.",
                "coding",
                "workspace_mutate",
                relations=("continue",),
                assistant="New tabs and selection persistence are implemented.",
            ),
            A(
                "Make tabs closable, but never allow closing the last remaining chart.",
                "coding",
                "workspace_mutate",
                relations=("continue",),
                assistant="Tabs are closable while one chart is always retained.",
            ),
            A(
                "Correction: when closing the active tab, select the tab immediately to its left when possible.",
                "coding",
                "workspace_mutate",
                relations=("revise", "continue"),
                assistant="Active-tab close now prefers the left neighbor.",
            ),
            A(
                "Add unit tests for creation, switching, closing, and per-tab symbol isolation.",
                "coding",
                "workspace_mutate",
                relations=("continue",),
                assistant="Unit coverage was added.",
            ),
            A(
                "Run those tests and typecheck.",
                "coding",
                "workspace_execute",
                forbidden_actions=("workspace_mutate",),
                relations=("continue", "revise"),
                assistant="The tests and typecheck pass.",
            ),
            A(
                "One more correction: drawings must survive interval changes inside the same tab.",
                "coding",
                "workspace_mutate",
                relations=("revise", "continue"),
                assistant="Drawings now survive interval changes in the same tab.",
            ),
            A(
                "Update the regression coverage for that rule and rerun the focused suite.",
                "coding",
                "workspace_mutate",
                action_any_of=(("workspace_execute", "workspace_read"),),
                relations=("continue",),
            ),
        ),
    ),

    # ------------------------------------------------------------------
    # Smart-home conversations.
    # ------------------------------------------------------------------
    ConversationScenario(
        "home_01_single_read",
        "smarthome",
        (
            A(
                "Please inspect the bedroom lamp and tell me whether it is on; do not change anything.",
                "house",
                "home_read",
                forbidden_actions=("home_mutate",),
                required_evidence=("home_state",),
            ),
        ),
    ),
    ConversationScenario(
        "home_02_concept_then_action",
        "smarthome",
        (
            C(
                "What is the difference between checking a smart plug state and toggling it?",
                "Checking is read-only; toggling changes physical state.",
                forbidden_actions=("home_read", "home_mutate"),
            ),
            A(
                "Now check the office plug. If it is on, turn it off and verify the final state.",
                "house",
                "home_mutate",
                required_evidence=("home_state",),
            ),
        ),
    ),
    ConversationScenario(
        "home_03_clarify_room_then_check",
        "smarthome",
        (
            C(
                "I have two lamps with similar names. How should I phrase a request so you do not touch the wrong one?",
                "Use the room plus the device name and say whether you want a read or a change.",
                forbidden_actions=("home_read", "home_mutate"),
            ),
            C(
                "The one I mean is the bedside lamp in the guest room.",
                "That identifies the target clearly.",
                forbidden_actions=("home_mutate",),
            ),
            A(
                "Check that guest-room bedside lamp and report its state only.",
                "house",
                "home_read",
                forbidden_actions=("home_mutate",),
                required_evidence=("home_state",),
            ),
        ),
    ),
    ConversationScenario(
        "home_04_read_then_change_target",
        "smarthome",
        (
            A(
                "Check whether the downstairs hallway light is on. Do not change it.",
                "house",
                "home_read",
                forbidden_actions=("home_mutate",),
                required_evidence=("home_state",),
                assistant="The downstairs hallway light is on.",
            ),
            A(
                "Would turning it off affect any automation you know about from this conversation?",
                "house",
                assistant="There is no automation information in the conversation to rely on.",
                forbidden_actions=("home_mutate",),
                relations=("continue",),
            ),
            A(
                "Turn that hallway light off and verify it.",
                "house",
                "home_mutate",
                relations=("revise", "continue"),
                assistant="The hallway light is now off.",
            ),
            A(
                "Correction: I meant the upstairs hallway light. Check its state first; do not change it yet.",
                "house",
                "home_read",
                forbidden_actions=("home_mutate",),
                relations=("revise",),
                required_evidence=("home_state",),
            ),
        ),
    ),
    ConversationScenario(
        "home_05_energy_then_action",
        "smarthome",
        (
            A(
                "Check today's available energy telemetry and identify which smart plug is drawing the most power.",
                "house",
                "home_read",
                required_evidence=("home_energy",),
                assistant="The office heater plug is the largest reported load.",
            ),
            A(
                "Do not turn anything off yet. What would be the risk of cutting power to a heater plug abruptly?",
                "house",
                forbidden_actions=("home_mutate",),
                relations=("revise",),
                assistant="It may interrupt the device's normal shutdown behavior depending on the heater.",
            ),
            A(
                "Check the current state of that office heater plug only.",
                "house",
                "home_read",
                forbidden_actions=("home_mutate",),
                required_evidence=("home_state",),
                relations=("none", "revise", "continue"),
                assistant="The office heater plug is currently on.",
            ),
            A(
                "Turn it off now and verify the state.",
                "house",
                "home_mutate",
                required_evidence=("home_state",),
                relations=("revise", "continue"),
                assistant="The plug is now off.",
            ),
            A(
                "Recheck the energy telemetry and tell me whether the reported load dropped; do not change anything else.",
                "house",
                "home_read",
                forbidden_actions=("home_mutate",),
                required_evidence=("home_energy",),
                relations=("revise", "continue"),
            ),
        ),
    ),
    ConversationScenario(
        "home_06_multi_device_evening",
        "smarthome",
        (
            C(
                "I want a calmer evening setup. I am only planning right now, not asking you to control anything.",
                "A calmer setup could reduce unnecessary lights and leave only the rooms in use lit.",
                forbidden_actions=("home_read", "home_mutate"),
            ),
            A(
                "Check the living-room and hallway lights and tell me which are currently on. No changes yet.",
                "house",
                "home_read",
                forbidden_actions=("home_mutate",),
                required_evidence=("home_state",),
                assistant="Both are currently on.",
            ),
            A(
                "Turn off the hallway light but leave the living-room light unchanged.",
                "house",
                "home_mutate",
                relations=("revise", "continue"),
                assistant="The hallway light is off; the living-room light was left unchanged.",
            ),
            A(
                "Dim the living-room lighting if that device supports it; otherwise leave it alone.",
                "house",
                "home_mutate",
                relations=("continue", "revise"),
                assistant="The request was applied only if supported.",
            ),
            A(
                "Check both states again and do not make any further changes.",
                "house",
                "home_read",
                forbidden_actions=("home_mutate",),
                required_evidence=("home_state",),
                relations=("revise", "continue", "resume"),
                assistant="The final states have been checked.",
            ),
            A(
                "Also check whether any downstairs smart plug is still on, read only.",
                "house",
                "home_read",
                forbidden_actions=("home_mutate",),
                required_evidence=("home_state",),
                relations=("continue",),
            ),
        ),
    ),
    ConversationScenario(
        "home_07_narrow_prohibition_then_change",
        "smarthome",
        (
            C(
                "When I say do not change anything, that should override any earlier idea to toggle a device, right?",
                "Yes. The latest explicit prohibition should remove mutation authority.",
                forbidden_actions=("home_read", "home_mutate"),
            ),
            A(
                "Check the porch light and garage plug. Do not change either device.",
                "house",
                "home_read",
                forbidden_actions=("home_mutate",),
                required_evidence=("home_state",),
                assistant="The porch light is on and the garage plug is off.",
            ),
            A(
                "Keep the garage plug exactly as it is.",
                "house",
                forbidden_actions=("home_mutate",),
                relations=("continue", "revise"),
                assistant="The garage plug is constrained to remain unchanged.",
            ),
            A(
                "Turn off only the porch light and verify it. Do not touch the garage plug.",
                "house",
                "home_mutate",
                relations=("revise", "continue"),
                assistant="Only the porch light was changed.",
            ),
            A(
                "Check the garage plug again without changing it.",
                "house",
                "home_read",
                forbidden_actions=("home_mutate",),
                required_evidence=("home_state",),
                relations=("revise", "continue"),
                assistant="The garage plug state has been rechecked.",
            ),
            A(
                "Now check the porch light one last time, read only.",
                "house",
                "home_read",
                forbidden_actions=("home_mutate",),
                required_evidence=("home_state",),
                relations=("revise", "continue"),
                assistant="The porch light state has been rechecked.",
            ),
            C(
                "Explain why the final read did not need mutation authority.",
                "Because reading verified state and changing physical state are separate authorities.",
                forbidden_actions=("home_mutate",),
            ),
        ),
    ),
    ConversationScenario(
        "home_08_long_scene_refinement",
        "smarthome",
        (
            C(
                "Help me plan a movie-night lighting setup, but do not control the house yet.",
                "A simple plan is dimmer living-room lighting and unnecessary adjacent lights off.",
                forbidden_actions=("home_read", "home_mutate"),
            ),
            C(
                "Keep the kitchen usable though.",
                "Then leave a kitchen light on while reducing the living-room brightness.",
                forbidden_actions=("home_mutate",),
            ),
            A(
                "Check the current living-room, kitchen, and hallway light states. Read only.",
                "house",
                "home_read",
                forbidden_actions=("home_mutate",),
                required_evidence=("home_state",),
                assistant="The current states have been checked.",
            ),
            A(
                "Set the living room for movie night and turn off the hallway light, but leave the kitchen unchanged.",
                "house",
                "home_mutate",
                relations=("revise", "continue"),
                assistant="The living room and hallway were adjusted while the kitchen was left unchanged.",
            ),
            A(
                "Actually keep one small hallway light on if there is a separate hallway lamp; otherwise do not reverse the change.",
                "house",
                "home_mutate",
                relations=("revise", "continue"),
                assistant="The conditional refinement was applied.",
            ),
            A(
                "Verify the living-room and hallway states now.",
                "house",
                "home_read",
                required_evidence=("home_state",),
                forbidden_actions=("home_mutate",),
                relations=("none", "revise", "continue"),
                assistant="The final lighting states have been verified.",
            ),
            A(
                "Check the living-room energy use if telemetry is available, read only.",
                "house",
                "home_read",
                forbidden_actions=("home_mutate",),
                relations=("none", "continue", "revise"),
                assistant="Available energy telemetry has been checked.",
            ),
            A(
                "Also summarize which devices you changed versus only inspected, without making any further changes.",
                "house",
                forbidden_actions=("home_mutate",),
                relations=("continue",),
                assistant="The scene changes required mutation authority; final state and energy checks were read-only.",
            ),
        ),
    ),

    # ------------------------------------------------------------------
    # Public-web / research conversations.  Bounded lookups may remain Chat
    # while open-ended investigation should become the research Agent.
    # ------------------------------------------------------------------
    ConversationScenario(
        "web_01_single_bounded_release",
        "web",
        (
            Q(
                "Check whether Python 3.14 is the current stable Python release and answer with the version only.",
                "research",
                "research_read",
                required_evidence=("software_release",),
            ),
        ),
    ),
    ConversationScenario(
        "web_02_timeless_then_current",
        "web",
        (
            C(
                "Explain the difference between a stable release and a release candidate from general knowledge.",
                "A stable release is intended for production use; a release candidate is a final pre-release validation stage.",
                forbidden_actions=("research_read",),
            ),
            Q(
                "Now check the current Python release status and tell me which stable version is latest.",
                "research",
                "research_read",
                required_evidence=("software_release",),
            ),
        ),
    ),
    ConversationScenario(
        "web_03_open_research_then_narrow",
        "web",
        (
            C(
                "What makes release notes useful when evaluating an upgrade?",
                "They show behavior changes, compatibility risks, migrations, and deprecations.",
                forbidden_actions=("research_read",),
            ),
            A(
                "Research the latest stable Playwright release across the official release notes, migration guidance, and browser/test-runner documentation, then synthesize the changes most likely to affect our browser tests.",
                "research",
                "research_read",
                required_evidence=("software_release",),
                assistant="The latest release contains several test-runner and browser compatibility changes.",
            ),
            Q(
                "From that research, check just the exact latest version number once more and give me the number only.",
                "research",
                "research_read",
                required_evidence=("software_release",),
                relations=("revise", "continue"),
            ),
        ),
    ),
    ConversationScenario(
        "web_04_compare_primary_sources",
        "web",
        (
            C(
                "When researching a software change, why prefer primary documentation over random summaries?",
                "Primary documentation is authoritative about the product's own behavior and release details.",
                forbidden_actions=("research_read",),
            ),
            A(
                "Research the latest stable React and Vue releases using primary sources where possible.",
                "research",
                "research_read",
                required_evidence=("software_release",),
                assistant="I compared current primary release information for both frameworks.",
            ),
            A(
                "Continue the primary-source research across both React and Vue release notes and migration guidance, but compare only the changes that would matter to a small dashboard application.",
                "research",
                "research_read",
                relations=("continue", "revise"),
                assistant="The comparison is narrowed to dashboard-relevant changes.",
            ),
            A(
                "Re-check those primary sources as needed, add source attribution, and separate confirmed release facts from your interpretation.",
                "research",
                "research_read",
                relations=("continue",),
            ),
        ),
    ),
    ConversationScenario(
        "web_05_current_fact_refinement",
        "web",
        (
            Q(
                "Check the current official release date for GTA 6 and tell me the date only.",
                "research",
                "research_read",
                evidence_any_of=("general_current_web", "software_release"),
                assistant="The current official date has been checked.",
            ),
            C(
                "Do not search again yet. What kinds of announcements could make that date change?",
                "Publisher delay announcements, platform changes, or revised release guidance could change it.",
                forbidden_actions=("research_read",),
            ),
            A(
                "Now research whether there have been any new official GTA 6 release-date changes in the last 30 days.",
                "research",
                "research_read",
                evidence_any_of=("general_current_web", "breaking_news"),
                assistant="Recent official updates have been checked.",
            ),
            A(
                "Ignore rumor sites and focus on Rockstar or Take-Two statements plus reputable reporting.",
                "research",
                "research_read",
                relations=("continue", "revise"),
                assistant="The source set is restricted accordingly.",
            ),
            A(
                "Give me a short conclusion and list exactly which claims are official versus reported.",
                "research",
                relations=("continue",),
            ),
        ),
    ),
    ConversationScenario(
        "web_06_outage_investigation",
        "web",
        (
            C(
                "What information would you want before deciding whether a service problem is local or a public outage?",
                "Local logs, provider status, recent incidents, and whether other users report the same failure are useful.",
                forbidden_actions=("research_read",),
            ),
            Q(
                "Check whether GitHub is reporting a public outage right now.",
                "research",
                "research_read",
                evidence_any_of=("general_current_web", "breaking_news"),
                assistant="Current public status information has been checked.",
            ),
            A(
                "Research the incident more broadly and summarize what services are affected and when it started.",
                "research",
                "research_read",
                evidence_any_of=("general_current_web", "breaking_news"),
                assistant="The incident scope and timeline have been researched.",
            ),
            A(
                "Prioritize GitHub's own status information over social posts.",
                "research",
                "research_read",
                relations=("continue", "revise"),
                assistant="Primary status information is prioritized.",
            ),
            Q(
                "Check for any recovery update since the first report.",
                "research",
                "research_read",
                relations=("continue",),
                evidence_any_of=("general_current_web", "breaking_news"),
                assistant="Recovery updates have been checked.",
            ),
            A(
                "Summarize the latest confirmed state and what remains uncertain.",
                "research",
                relations=("continue",),
            ),
        ),
    ),
    ConversationScenario(
        "web_07_browser_testing_research",
        "web",
        (
            C(
                "From general knowledge, what is the difference between a Playwright locator and a raw CSS selector?",
                "Locators add retry and actionability semantics around element targeting.",
                forbidden_actions=("research_read",),
            ),
            A(
                "Research the current Playwright guidance for resilient locators and assertions.",
                "research",
                "research_read",
                evidence_any_of=("software_release", "general_current_web"),
                assistant="Current Playwright guidance has been researched.",
            ),
            A(
                "Focus on recommendations that reduce flaky web tests.",
                "research",
                "research_read",
                relations=("continue", "revise"),
                assistant="The findings are narrowed to flake reduction.",
            ),
            A(
                "Compare role-based locators with test-id locators and explain when each is preferred.",
                "research",
                relations=("continue",),
                assistant="The locator strategies have been compared.",
            ),
            Q(
                "Check whether any of those recommendations changed in the latest stable release docs.",
                "research",
                "research_read",
                evidence_any_of=("software_release", "general_current_web"),
                relations=("continue",),
                assistant="The latest stable release guidance has been checked.",
            ),
            A(
                "Give me a migration checklist for an existing flaky login test suite.",
                "research",
                relations=("continue",),
                assistant="A migration checklist has been prepared.",
            ),
            Q(
                "Add citations for every recommendation that depends on current Playwright behavior.",
                "research",
                "research_read",
                evidence_any_of=("software_release", "general_current_web"),
                relations=("continue",),
            ),
        ),
    ),
    ConversationScenario(
        "web_08_long_multi_source_research",
        "web",
        (
            C(
                "I am evaluating whether to adopt a new JavaScript runtime. What categories should I compare?",
                "Compatibility, performance, ecosystem, tooling, deployment, and maintenance maturity are key.",
                forbidden_actions=("research_read",),
            ),
            A(
                "Research the current stable releases of Node, Deno, and Bun.",
                "research",
                "research_read",
                required_evidence=("software_release",),
                assistant="Current stable release information has been collected.",
            ),
            A(
                "Compare ecosystem compatibility and package-management behavior.",
                "research",
                "research_read",
                relations=("continue",),
                assistant="Ecosystem and package-management differences are compared.",
            ),
            A(
                "Now focus on test-runner and TypeScript support.",
                "research",
                "research_read",
                relations=("continue", "revise"),
                assistant="The comparison is focused on tests and TypeScript.",
            ),
            A(
                "Separate documented facts from benchmark claims.",
                "research",
                relations=("continue", "revise"),
                assistant="Documented facts and benchmark claims are separated.",
            ),
            A(
                "For benchmark claims, prefer recent independent sources and call out methodology limits.",
                "research",
                relations=("continue",),
                assistant="Benchmark methodology limits are included.",
            ),
            A(
                "Check whether any major compatibility issue changed in the last month.",
                "research",
                "research_read",
                evidence_any_of=("general_current_web", "breaking_news", "software_release"),
                relations=("continue",),
                assistant="Recent compatibility developments have been checked.",
            ),
            A(
                "Finish with a recommendation for a conservative production team, with sources.",
                "research",
                "research_read",
                relations=("continue",),
            ),
        ),
    ),

    # ------------------------------------------------------------------
    # Trading / market-research conversations.  Execution is intentionally
    # absent: the trading-research profile is read-only.
    # ------------------------------------------------------------------
    ConversationScenario(
        "trading_01_single_quote",
        "trading",
        (
            Q(
                "What is NVDA trading at right now? Give me the current quote only.",
                "trading-research",
                "market_read",
                required_evidence=("market_quote",),
            ),
        ),
    ),
    ConversationScenario(
        "trading_02_concept_then_quote",
        "trading",
        (
            C(
                "Explain what relative volume means without looking anything up.",
                "Relative volume compares current volume with a normal baseline for the same security.",
                forbidden_actions=("market_read",),
            ),
            Q(
                "Now check GME's current quote and tell me the price and spread if available.",
                "trading-research",
                "market_read",
                required_evidence=("market_quote",),
            ),
        ),
    ),
    ConversationScenario(
        "trading_03_catalyst_research",
        "trading",
        (
            C(
                "From general knowledge, what distinguishes a real stock catalyst from social-media noise?",
                "A real catalyst is tied to verifiable company, regulatory, industry, or macro information.",
                forbidden_actions=("market_read",),
            ),
            A(
                "Research whether GME has a real catalyst today and separate company facts from market speculation.",
                "trading-research",
                "market_read",
                required_evidence=("market_news",),
                assistant="Today's GME catalyst picture has been researched.",
            ),
            Q(
                "Check the current quote too and relate the move to the confirmed catalyst without predicting certainty.",
                "trading-research",
                "market_read",
                required_evidence=("market_quote",),
                relations=("continue",),
            ),
        ),
    ),
    ConversationScenario(
        "trading_04_compare_two_tickers",
        "trading",
        (
            Q(
                "Check the current NVDA quote.",
                "trading-research",
                "market_read",
                required_evidence=("market_quote",),
                assistant="The current NVDA quote has been checked.",
            ),
            Q(
                "Check AMD's current quote too.",
                "trading-research",
                "market_read",
                required_evidence=("market_quote",),
                assistant="The current AMD quote has been checked.",
            ),
            A(
                "Research today's confirmed catalysts for both NVDA and AMD.",
                "trading-research",
                "market_read",
                required_evidence=("market_news",),
                assistant="Today's confirmed catalysts for both companies have been researched.",
            ),
            A(
                "Compare which catalyst is more material and explain the evidence behind the ranking.",
                "trading-research",
                "market_read",
                relations=("continue",),
            ),
        ),
    ),
    ConversationScenario(
        "trading_05_multiple_refinements",
        "trading",
        (
            A(
                "Research today's top story affecting NVDA and summarize the confirmed catalyst.",
                "trading-research",
                "market_read",
                required_evidence=("market_news",),
                assistant="The leading confirmed NVDA catalyst has been summarized.",
            ),
            Q(
                "Also check the current quote and whether the market is reacting in the same direction.",
                "trading-research",
                "market_read",
                required_evidence=("market_quote",),
                relations=("continue",),
                assistant="The quote and direction have been checked.",
            ),
            A(
                "Actually, compare that with AMD instead of analyzing NVDA alone.",
                "trading-research",
                "market_read",
                relations=("revise",),
                assistant="The analysis now compares NVDA with AMD.",
            ),
            A(
                "Include any company filing from this week that materially changes the comparison.",
                "trading-research",
                "market_read",
                required_evidence=("company_filing",),
                relations=("continue",),
                assistant="Material recent filings are included.",
            ),
            A(
                "End with a risk-focused summary, not a buy or sell recommendation.",
                "trading-research",
                relations=("continue",),
            ),
        ),
    ),
    ConversationScenario(
        "trading_06_filing_quote_sequence",
        "trading",
        (
            C(
                "Explain why an 8-K can matter to a short-term trader without looking up any company.",
                "An 8-K can disclose material events that rapidly change market expectations.",
                forbidden_actions=("market_read",),
            ),
            A(
                "Research GME filings from the last seven days and identify anything material.",
                "trading-research",
                "market_read",
                required_evidence=("company_filing",),
                assistant="Recent GME filings have been reviewed.",
            ),
            Q(
                "Now check the current GME quote.",
                "trading-research",
                "market_read",
                required_evidence=("market_quote",),
                relations=("none", "continue", "revise"),
                assistant="The current quote has been checked.",
            ),
            A(
                "Using only the quote, filings, and news facts already gathered in this conversation, relate the move to those confirmed facts; do not fetch anything new and do not invent causality.",
                "trading-research",
                forbidden_actions=("market_read",),
                relations=("continue", "revise"),
                assistant="The discussion is constrained to already gathered confirmed facts.",
            ),
            Q(
                "Compare volume context with the confirmed catalyst if reliable current information is available.",
                "trading-research",
                "market_read",
                relations=("continue",),
                assistant="Available current context has been compared.",
            ),
            A(
                "Summarize what is known, what is inference, and what is still unknown.",
                "trading-research",
                assistant="The established facts, inferences, and remaining unknowns are summarized from the prior discussion.",
                forbidden_actions=("market_read",),
                relations=("continue",),
            ),
        ),
    ),
    ConversationScenario(
        "trading_07_memory_only_then_current",
        "trading",
        (
            C(
                "From memory only, explain the difference between a bull flag and a bear flag.",
                "A bull flag usually consolidates after an upward impulse; a bear flag consolidates after a downward impulse.",
                forbidden_actions=("market_read",),
            ),
            C(
                "What makes volume confirmation useful conceptually?",
                "Volume can help distinguish active participation from a weak move.",
                forbidden_actions=("market_read",),
            ),
            Q(
                "Now check the current GME quote, but do not research news yet.",
                "trading-research",
                "market_read",
                required_evidence=("market_quote",),
                assistant="The current GME quote has been checked.",
            ),
            A(
                "Research whether there is a confirmed catalyst today.",
                "trading-research",
                "market_read",
                required_evidence=("market_news",),
                assistant="Today's confirmed catalyst information has been researched.",
            ),
            A(
                "Keep social-media claims separate unless independently verified.",
                "trading-research",
                "market_read",
                relations=("continue",),
                assistant="Unverified social claims are separated from confirmed facts.",
            ),
            Q(
                "Check for a relevant filing too.",
                "trading-research",
                "market_read",
                required_evidence=("company_filing",),
                relations=("continue",),
                assistant="Relevant filings have been checked.",
            ),
            A(
                "Give me the final evidence-based summary with uncertainty clearly labeled.",
                "trading-research",
                relations=("continue",),
            ),
        ),
    ),
    ConversationScenario(
        "trading_08_long_strategy_research",
        "trading",
        (
            C(
                "Explain the idea of buying a failed sell-off in a volatile gapper without using current market data.",
                "The setup waits for selling pressure to fail and for structure to re-establish before entry.",
                forbidden_actions=("market_read",),
            ),
            C(
                "What would make that setup invalid conceptually?",
                "Loss of the higher low, weak reclaim, poor liquidity, or a broken catalyst thesis can invalidate it.",
                forbidden_actions=("market_read",),
            ),
            A(
                "Research today's volatile US gainers and identify candidates with real catalysts; do not place any trades.",
                "trading-research",
                "market_read",
                evidence_any_of=("market_news", "general_current_web"),
                assistant="Current candidates and catalysts have been researched.",
            ),
            Q(
                "Narrow the list to names with sufficient liquidity and meaningful current volume.",
                "trading-research",
                "market_read",
                required_evidence=("market_status",),
                relations=("continue",),
                assistant="The two remaining candidates are GME and AMC; catalyst, liquidity, and supply-risk notes are captured for both.",
            ),
            Q(
                "For GME, check the current quote and spread as a concrete quote lookup before we continue.",
                "trading-research",
                "market_read",
                required_evidence=("market_quote",),
                relations=("continue",),
                assistant="The current GME quote and spread have been checked.",
            ),
            Q(
                "Check for dilution or offering-related filings that could change the risk.",
                "trading-research",
                "market_read",
                required_evidence=("company_filing",),
                relations=("continue",),
                assistant="Relevant supply-risk filings have been checked.",
            ),
            A(
                "Using only the candidate data already gathered, rank GME and AMC using catalyst quality, liquidity, and supply risk only.",
                "trading-research",
                relations=("continue",),
                assistant="The two setups have been ranked using those factors.",
            ),
            A(
                "One correction: do not treat a high-volume spike by itself as a catalyst.",
                "trading-research",
                relations=("revise", "continue"),
            ),
        ),
    ),
)


def _enabled() -> bool:
    return (
        str(os.environ.get("OMNIX_RUN_LIVE_AGENT_CONVERSATION_TESTS", ""))
        .strip()
        .casefold()
        in _TRUE
    )


def _bool_env(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().casefold()
    return raw in _TRUE


def _selected(scenario: ConversationScenario) -> bool:
    raw_domain = str(os.environ.get("OMNIX_LIVE_AGENT_CONVERSATION_DOMAIN", "")).strip()
    if raw_domain:
        domains = {value.strip().casefold() for value in raw_domain.split(",") if value.strip()}
        if scenario.domain.casefold() not in domains:
            return False
    raw_scenario = str(
        os.environ.get("OMNIX_LIVE_AGENT_CONVERSATION_SCENARIO", "")
    ).strip().casefold()
    if raw_scenario and raw_scenario not in scenario.id.casefold():
        return False
    return True


def _param(scenario: ConversationScenario):
    marks = []
    if not _selected(scenario):
        marks.append(pytest.mark.skip(reason="filtered by live conversation matrix selector"))
    return pytest.param(scenario, id=scenario.id, marks=marks)


class _ReplayParser:
    """Replay one real LLM SemanticTask through the production Chat bridge."""

    def __init__(self, task: SemanticTask) -> None:
        self.task = task

    def parse_contextual(self, _content: str, **_kwargs) -> SemanticTask:
        return self.task


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
        self.reference_contexts.append((spec.run_id, str(reference_context or "")))
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

    def command_with_context(self, command, *, reference_context="", **_kwargs):
        self.commands.append(command)
        self.reference_contexts.append((command.run_id, str(reference_context or "")))
        snapshot = self.runs[command.run_id]
        snapshot.revision += 1
        return snapshot

    def command(self, command):
        return self.command_with_context(command)

    def approvals(self, _run_id, *, state=None):
        return []


@pytest.fixture(scope="session")
def live_luna_high_parser() -> ProviderSemanticTaskParser:
    if not _enabled():
        pytest.skip(
            "live Agent conversation matrix is opt-in; set "
            "OMNIX_RUN_LIVE_AGENT_CONVERSATION_TESTS=1"
        )

    codex_path = str(os.environ.get("OMNIX_LIVE_CODEX_PATH", "codex") or "codex").strip()
    status = ChatGPTCodexProvider.auth_status(codex_path)
    if not (
        status.get("installed")
        and status.get("authenticated")
        and status.get("auth_mode") == "chatgpt"
    ):
        pytest.fail(
            "live Agent conversation tests were explicitly enabled, but Codex is not "
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
                "fast_mode": _bool_env("OMNIX_LIVE_AGENT_FAST_MODE", False),
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
    rows = []
    for message in messages:
        role = str(getattr(message, "role", "") or "").strip().title()
        content = str(getattr(message, "content", "") or "").strip()
        if role and content:
            rows.append(f"{role}: {content}")
    return "\n".join(rows)


def _environment(
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
            else ("session_selection" if selected else "none")
        ),
        "workspace_attached_this_turn": attached_this_turn,
        "attachment_kinds": ["local_folder"] if selected else [],
        "attachment_count": 1 if selected else 0,
        "agent_mode_selected": False,
    }


def _semantic_fail(label: str, payload: dict) -> None:
    pytest.fail(
        label + "\n" + json.dumps(payload, indent=2, sort_keys=True, default=str),
        pytrace=False,
    )


def _semantic_action_satisfied(
    required: str,
    *,
    actions: set[str],
    evidence: set[str],
    plan: TurnPlan,
) -> bool:
    """Accept equivalent authority plans instead of one LLM decomposition.

    External read authority is canonically compiled from evidence requirements.
    The live LLM is therefore free to express a read as an operation, a data
    dependency, or both.  Stateful/write/execute authority remains exact.
    """

    if required in actions:
        return True
    if required == "research_read":
        return bool(
            evidence.intersection(
                {"general_current_web", "breaking_news", "software_release"}
            )
        )
    if required == "market_read":
        return bool(
            plan.profile_id == "trading-research"
            and evidence.intersection(
                {
                    "market_news",
                    "market_quote",
                    "company_filing",
                    "market_status",
                    "general_current_web",
                }
            )
        )
    if required == "workspace_read":
        return bool(
            plan.profile_id == "coding"
            and (
                "repo_ci_read" in actions
                or "repo_ci_state" in evidence
                or actions.intersection(
                    {"workspace_read", "workspace_mutate", "workspace_execute"}
                )
            )
        )
    return False


def _assert_semantics(
    turn: ConversationTurn,
    task: SemanticTask,
    plan: TurnPlan,
) -> None:
    semantic = plan.compilation
    payload = {
        "user": turn.user,
        "semantic_task": task.model_dump(mode="json"),
        "turn_plan": plan.model_dump(mode="json"),
        "semantic_compilation": semantic.model_dump(mode="json"),
    }
    if task.ambiguity == "clarification_required":
        _semantic_fail("unexpected semantic clarification", payload)

    if plan.lane != turn.lane:
        _semantic_fail(
            "turn-plan lane mismatch",
            {
                "expected_final_lane": turn.lane,
                "compiled_lane": plan.lane,
                "relation": plan.relation,
                "disposition": plan.disposition,
                **payload,
            },
        )

    if turn.profile is not None and plan.profile_id != turn.profile:
        _semantic_fail(
            "turn-plan profile mismatch",
            {
                "expected_profile": turn.profile,
                "actual_profile": plan.profile_id,
                **payload,
            },
        )

    actions = set(semantic.action_intents)
    evidence = {
        row.source_class
        for row in semantic.evidence_decision.policy.requirements
    }
    missing_actions = {
        required
        for required in turn.required_actions
        if not _semantic_action_satisfied(
            required,
            actions=actions,
            evidence=evidence,
            plan=plan,
        )
    }
    if missing_actions:
        _semantic_fail(
            "missing required semantic actions",
            {
                "missing_actions": sorted(missing_actions),
                "actual_actions": sorted(actions),
                **payload,
            },
        )
    for group in turn.action_any_of:
        if not any(
            _semantic_action_satisfied(
                required,
                actions=actions,
                evidence=evidence,
                plan=plan,
            )
            for required in group
        ):
            _semantic_fail(
                "missing one-of semantic action",
                {
                    "expected_any_action": group,
                    "actual_actions": sorted(actions),
                    **payload,
                },
            )
    forbidden_actions = set(turn.forbidden_actions).intersection(actions)
    if forbidden_actions:
        _semantic_fail(
            "forbidden semantic action emitted",
            {
                "forbidden_actions": sorted(forbidden_actions),
                "actual_actions": sorted(actions),
                **payload,
            },
        )

    missing_evidence = set(turn.required_evidence) - evidence
    if missing_evidence:
        _semantic_fail(
            "missing required evidence",
            {
                "missing_evidence": sorted(missing_evidence),
                "actual_evidence": sorted(evidence),
                **payload,
            },
        )
    if turn.evidence_any_of and not evidence.intersection(turn.evidence_any_of):
        _semantic_fail(
            "missing one-of evidence source",
            {
                "expected_any_evidence": turn.evidence_any_of,
                "actual_evidence": sorted(evidence),
                **payload,
            },
        )
    forbidden_evidence = set(turn.forbidden_evidence).intersection(evidence)
    if forbidden_evidence:
        _semantic_fail(
            "forbidden evidence emitted",
            {
                "forbidden_evidence": sorted(forbidden_evidence),
                "actual_evidence": sorted(evidence),
                **payload,
            },
        )
    if turn.relations and plan.relation not in turn.relations:
        _semantic_fail(
            "objective relation mismatch",
            {
                "expected_relations": turn.relations,
                "raw_relation": task.objective_relation,
                "normalized_relation": plan.relation,
                **payload,
            },
        )


@pytest.mark.live_codex
@pytest.mark.parametrize("scenario", [_param(scenario) for scenario in SCENARIOS])
def test_live_luna_high_conversation_routing_and_agent_handoff(
    scenario: ConversationScenario,
    live_luna_high_parser: ProviderSemanticTaskParser,
    monkeypatch,
    tmp_path,
) -> None:
    workspace = tmp_path / "omnix-live-agent-matrix"
    workspace.mkdir()
    monkeypatch.delenv("OMNIX_AGENT_DEFAULT_REPOSITORY", raising=False)
    monkeypatch.setenv("OMNIX_AGENT_REASONING_EFFORT", _REASONING_EFFORT)

    service = _RecordingAgentService()
    monkeypatch.setattr(chat_bridge, "default_agent_run_service", lambda: service)
    # Chat evidence execution is outside this suite.  We validate the compiled
    # evidence contract but never hit live web/home/market connectors here.
    monkeypatch.setattr(chat_bridge, "_enforce_chat_evidence", lambda *_a, **_k: None)

    session = SimpleNamespace(
        id=f"live-conversation:{scenario.id}",
        provider_id="chatgpt_codex",
        model_id=_MODEL,
        messages=[],
    )
    active_objective: ActiveObjective | None = None
    workspace_selected = False

    for index, turn in enumerate(scenario.turns, start=1):
        workspace_selected = workspace_selected or turn.attach_workspace
        reference_context = _reference_context(session.messages)
        environment = _environment(
            workspace,
            selected=workspace_selected,
            attached_this_turn=turn.attach_workspace,
        )
        task = live_luna_high_parser.parse_contextual(
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
        task = plan.semantic_task
        semantic = plan.compilation
        _assert_semantics(turn, task, plan)

        user_metadata = {}
        if workspace_selected:
            user_metadata["workspace_root"] = str(workspace)

        # Verify least-privilege authority compilation independently of the
        # handoff record. TurnPlan already accounts for the selected Local
        # workspace, so repo_contents never needs a redundant GitHub grant.
        compiled = None
        if semantic.lane == "agent" and semantic.profile_id is not None:
            compiled = compile_task_authority(
                get_agent_profile(semantic.profile_id),
                plan.effective_request,
                semantic.evidence_decision,
                semantic_action_intents=semantic.action_intents,
                allow_text_semantic_fallback=False,
            )

        user_message = SimpleNamespace(
            id=f"{scenario.id}:user:{index}",
            role="user",
            content=turn.user,
            metadata=user_metadata,
        )
        session.messages.append(user_message)

        starts_before = len(service.starts)
        commands_before = len(service.commands)
        objective_before = active_objective
        result = route_typed_chat_turn(
            session,
            user_message,
            provider_id="chatgpt_codex",
            model_id=_MODEL,
            semantic_classifier=_ReplayParser(task),
            routing_context_factory=lambda rc=reference_context: SimpleNamespace(
                reference_context=rc
            ),
        )

        if turn.lane == "chat":
            assert result is None, {
                "scenario": scenario.id,
                "turn": index,
                "unexpected_result": result,
                "semantic_task": task.model_dump(mode="json"),
                "semantic_compilation": semantic.model_dump(mode="json"),
            }
            assert len(service.starts) == starts_before
            assert len(service.commands) == commands_before
            assistant_metadata = {}
        else:
            assert result is not None, {
                "scenario": scenario.id,
                "turn": index,
                "semantic_task": task.model_dump(mode="json"),
                "semantic_compilation": semantic.model_dump(mode="json"),
            }
            assert result.metadata["omnix_route"]["lane"] == "agent"
            expected_request = (
                turn.expected_request
                or (
                    objective_before.latest_user_request()
                    if turn.handoff == "previous" and objective_before is not None
                    else turn.user
                )
            )
            assert plan.effective_request == expected_request
            assert expected_request, {
                "scenario": scenario.id,
                "turn": index,
                "handoff": turn.handoff,
            }

            if len(service.starts) == starts_before + 1:
                spec = service.starts[-1]
                assert len(service.commands) == commands_before
                assert spec.task == expected_request
                assert spec.objective == expected_request
                assert spec.profile == semantic.profile_id
                assert spec.model.provider_id == "chatgpt_codex"
                assert spec.model.model_id == _MODEL
                assert spec.model.reasoning_effort == _REASONING_EFFORT
                assert compiled is not None
                assert set(spec.capabilities) == set(compiled.required_local)
                assert set(spec.external_capabilities) == set(compiled.required_external)
            else:
                assert len(service.starts) == starts_before
                assert len(service.commands) == commands_before + 1
                command = service.commands[-1]
                assert command.command_type == "steer"
                assert command.payload["message"] == expected_request

            # The authority payload must be exactly user-authored current text
            # or the prior canonical request for an explicit semantic resume.
            # No assistant prose or transcript projection may leak into it.
            if turn.expected_request is not None:
                assert expected_request == turn.expected_request
            elif turn.handoff == "latest":
                assert expected_request == turn.user
            else:
                assert objective_before is not None
                assert expected_request == objective_before.latest_user_request()

            assistant_metadata = dict(result.metadata)
            raw_objective = assistant_metadata.get("active_objective")
            if isinstance(raw_objective, dict):
                active_objective = ActiveObjective.model_validate(raw_objective)

        session.messages.append(
            SimpleNamespace(
                id=f"{scenario.id}:assistant:{index}",
                role="assistant",
                content=turn.assistant or (
                    result.content if result is not None else "Understood."
                ),
                metadata=assistant_metadata,
            )
        )


def test_live_conversation_matrix_is_comprehensive_and_balanced() -> None:
    """Non-live guard so normal CI notices accidental matrix shrinkage."""

    assert len(SCENARIOS) >= 34
    assert sum(len(scenario.turns) for scenario in SCENARIOS) >= 115

    lengths = {len(scenario.turns) for scenario in SCENARIOS}
    assert set(range(1, 11)) <= lengths

    for domain in ("coding", "smarthome", "web", "trading"):
        domain_scenarios = [s for s in SCENARIOS if s.domain == domain]
        assert len(domain_scenarios) >= 8
        assert sum(len(s.turns) for s in domain_scenarios) >= 30

    coding_five = next(
        scenario for scenario in SCENARIOS if scenario.id == "coding_05_multiple_refinements"
    )
    assert len(coding_five.turns) == 5
    assert sum(turn.handoff == "latest" for turn in coding_five.turns) >= 4

    assert any(
        turn.handoff == "previous"
        for scenario in SCENARIOS
        for turn in scenario.turns
    )
    assert any(
        turn.required_evidence
        for scenario in SCENARIOS
        if scenario.domain in {"web", "trading", "smarthome"}
        for turn in scenario.turns
    )
    assert any(
        "workspace_execute" in turn.required_actions
        for scenario in SCENARIOS
        if scenario.domain == "coding"
        for turn in scenario.turns
    )
