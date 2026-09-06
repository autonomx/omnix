"""Allowlisted, versioned coding methodology injected by Omnix.

Skills are prompt methodology only. They never add tools, capabilities, resource
scopes or external authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib


@dataclass(frozen=True, slots=True)
class CodingSkill:
    id: str
    version: str
    guidance: str


_SKILLS = (
    CodingSkill(
        "repository-inspection",
        "1",
        "Map the relevant module, tests, registrations and callers before editing. Read existing patterns before inventing new ones.",
    ),
    CodingSkill(
        "architecture-analysis",
        "1",
        "Identify the authoritative layer, data flow and invariants. Prefer changes at the layer that owns the behavior rather than compensating downstream.",
    ),
    CodingSkill(
        "implementation-planning",
        "1",
        "Form a concise plan tied to explicit requirements, then keep the patch as small and coherent as possible.",
    ),
    CodingSkill(
        "debugging",
        "1",
        "Reproduce the failure, trace the causal path, distinguish symptom from cause, and verify the fix with a regression test.",
    ),
    CodingSkill(
        "test-selection",
        "1",
        "Run the smallest validation that actually exercises the changed behavior, then broaden only when interfaces or shared infrastructure changed.",
    ),
    CodingSkill(
        "impact-analysis",
        "1",
        "Search callers, consumers, schemas, generated contracts and adjacent tests whenever an interface, symbol or persisted contract changes.",
    ),
    CodingSkill(
        "diff-review",
        "1",
        "Review the complete final diff for accidental edits, omissions, duplication, dead/debug code, stale names and incomplete migrations or call sites.",
    ),
    CodingSkill(
        "frontend-validation",
        "1",
        "For web changes, inspect component/style ownership, update focused UI tests, and run the package-local test/build/typecheck command from repository root.",
    ),
)


def compile_coding_skills(*, profile: str) -> tuple[str, str]:
    if profile not in {"coding", "coding-reviewer"}:
        return "", hashlib.sha256(b"").hexdigest()
    text = "\n".join(
        f"[{skill.id}@{skill.version}] {skill.guidance}"
        for skill in _SKILLS
    )
    return text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def skill_ids() -> tuple[str, ...]:
    return tuple(skill.id for skill in _SKILLS)
