"""Trusted Omnix prompt layer over the stable Pi RPC runtime core.

Pi's arbitrary skills, templates and context-file loading remain disabled by the
core launcher. Omnix adds only allowlisted methodology and explicitly compiled
repository guidance here, preserving capability and completion authority.
"""
from __future__ import annotations

import json

from .coding_skills import compile_coding_skills
from .contracts import AgentRunSpec
from .pi_runtime_core import (
    PiAgentRuntime as _CorePiAgentRuntime,
    PiRpcSession,
    build_agent_environment,
    normalize_pi_event,
    pi_broker_extension_path,
    pi_guard_extension_path,
    pi_model_provider_extension_path,
    pi_rpc_argv,
)
from .repository_guidance import compile_repository_guidance


_ENGINEERING_WORKFLOW = """MANDATORY ENGINEERING WORKFLOW FOR MUTATING CODING TASKS
1. INSPECT — inspect the relevant repository structure and existing implementation before editing. Locate tests, callers, interfaces, registrations, schemas and adjacent patterns; do not guess architecture.
2. DEFINE COMPLETION — re-read the user objective and required success criteria. Identify what implementation and evidence will prove each requirement.
3. PLAN — form a concise implementation plan from repository truth. Prefer the smallest coherent architectural change over patchwork fixes.
4. IMPLEMENT — make the change and add/update regression tests where behavior changes.
5. INSPECT THE COMPLETE RESULT — after the final edit, inspect the complete diff. Check accidental changes, duplication, dead/debug code, stale names, missing imports, incomplete call sites, migrations and generated contracts.
6. REREAD REQUIREMENTS — compare every requested requirement against the actual final implementation. Passing tests alone do not prove semantic completeness.
7. IMPACT / REGRESSION REVIEW — search affected callers and consumers; consider edge cases, compatibility and authority boundaries. Fix material issues found.
8. FINAL-STATE VALIDATION — run the smallest relevant tests/typecheck/lint/build against the FINAL code state. Validation from before a later mutation is stale and does not count.
9. SELF-REVIEW — critically review the change as if it were another engineer's patch. Repair incomplete requirements or regressions before settling.
10. REQUEST COMPLETION — Pi settling is only a completion request. Omnix will independently validate/review the exact final state and is the only authority that can mark the run completed.
"""


class PiAgentRuntime(_CorePiAgentRuntime):
    @staticmethod
    def _initial_prompt(
        spec: AgentRunSpec,
        *,
        reference_context: str = "",
    ) -> str:
        base = _CorePiAgentRuntime._initial_prompt(
            spec,
            reference_context=reference_context,
        )
        if spec.profile not in {"coding", "coding-reviewer"}:
            return base

        objective = spec.objective or spec.task
        guidance, guidance_digest = compile_repository_guidance(
            spec.workspace,
            objective=objective,
        )
        skills, skills_digest = compile_coding_skills(profile=spec.profile)
        execution = {
            "provider_id": spec.model.provider_id,
            "model_id": spec.model.model_id,
            "requested_reasoning_effort": spec.model.parameters.get("requested_reasoning_effort"),
            "resolved_reasoning_effort": spec.model.reasoning_effort,
            "reasoning_effort_source": spec.model.parameters.get("reasoning_effort_source"),
            "quality_policy": spec.quality_policy,
            "repository_guidance_digest": guidance_digest,
            "curated_skills_digest": skills_digest,
        }
        sections = [
            base,
            "Resolved Omnix execution profile JSON:\n" + json.dumps(execution, sort_keys=True, default=str),
            "Omnix-compiled repository guidance:\n" + guidance,
            "Omnix allowlisted coding methodology skills:\n" + (skills or "none"),
        ]
        if spec.profile == "coding":
            sections.append(_ENGINEERING_WORKFLOW)
        else:
            sections.append(
                "INDEPENDENT REVIEW MODE: remain read-only, inspect the immutable snapshot critically, "
                "do not propose authority expansion, do not modify files, and return the structured verdict "
                "requested by the review task. Reviewer process success is not approval."
            )
        return "\n\n".join(sections)


__all__ = [
    "PiAgentRuntime",
    "PiRpcSession",
    "build_agent_environment",
    "normalize_pi_event",
    "pi_broker_extension_path",
    "pi_guard_extension_path",
    "pi_model_provider_extension_path",
    "pi_rpc_argv",
]
