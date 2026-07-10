# Milestone 7 — Live Agent via Hermes

Status: repository implementation complete; disabled by default pending Milestone 6 target-runtime evidence and an intentional controlled rollout.

## Objective

Route clear action-oriented live voice requests to the existing Hermes-backed Omnix Agent Mode while keeping casual conversation on the low-latency provider path.

```text
live voice utterance
        ↓
deterministic cheap router
        ├─ conversation / information / ambiguity → direct provider chat
        └─ explicit actionable task             → Hermes proposal
                                                     ↓
                                               Omnix review boundary
```

Hermes is a planner, not an execution owner. Omnix continues to own identity, memory policy, approval, execution, persistence, cancellation, and auditability.

## Feature flags

```text
OMNIX_LIVE_AGENT_ENABLED=0
OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED=0
OMNIX_LIVE_AGENT_REQUIRE_HERMES=1
OMNIX_LIVE_AGENT_TIMEOUT_SECONDS=6
HERMES_ENABLED=0
HERMES_BASE_URL=http://127.0.0.1:8642
```

Recommended staged enablement:

1. Complete Milestone 6 physical runtime evidence and obtain a `pass` report.
2. Enable `HERMES_ENABLED=1` and verify Hermes health separately.
3. Enable `OMNIX_LIVE_AGENT_ENABLED=1` with auto-route still disabled.
4. Exercise explicit Agent Mode and confirm every tool result is non-executing or review-held.
5. Enable `OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED=1` for a controlled live-call pilot.

## Routing policy

Automatic routing is considered only when the authoritative user message contains a voice `user_turn_id` or `speech_segment_id`. Normal typed chat never auto-routes.

Agent-plan examples:

- “Turn off the kitchen light.”
- “Can you schedule a meeting for tomorrow?”
- “Send an email to Alex.”
- “Create a reminder for six.”
- “Use the agent to update the repository issue.”

Direct-chat examples:

- “Hello.”
- “How are you?”
- “Explain how the thermostat works.”
- “What do you think about my schedule?”
- Ambiguous action words without a concrete target.

The deterministic router does not call an LLM and therefore does not add model latency to ordinary conversation.

## Proposal and execution boundary

Automatically routed work always uses:

```text
dry_run = true
proposal_only = true
review_required = true
executes = false
```

Hermes may return structured tool calls. `apply_mode_result` may evaluate readouts or dry-run adapters, but every returned tool result is forced to `executed=false`. No automatically routed request can apply a real action.

A later approval/execution phase must use the existing Omnix confirmation and tool-policy system. This milestone does not add automatic approval.

## Failure behavior

- Live Agent disabled: direct provider chat.
- Auto-route disabled: direct provider chat.
- Hermes disabled while required: direct provider chat without attempting a connection.
- Hermes enabled but unreachable: bounded planner attempt, then original provider stream.
- Ambiguous intent: direct provider chat.
- Client interruption: authoritative assistant-turn cancellation remains in force; late Hermes output is inert.

Fallback metadata records the route decision and a bounded error string without placing credentials or transcript content in diagnostics.

## Character and memory behavior

The adapter wraps the final character-aware JSON and SQLite Chat store classes. Consequently:

- the active System/Character identity remains authoritative;
- memory and transcript policies are unchanged;
- the same user and assistant turn IDs are retained;
- interrupted delivery projection remains active;
- fallback provider responses use normal prompt assembly;
- no second transcript or memory store is introduced.

## Rollback

Set:

```text
OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED=0
OMNIX_LIVE_AGENT_ENABLED=0
```

This immediately restores the direct live-chat path without deleting sessions, route diagnostics, Hermes configuration, or Agent Mode support. Removing the Chat adapter import is the code-level rollback.
