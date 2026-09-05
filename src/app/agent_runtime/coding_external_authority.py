"""Minimum external authority compiler for coding-specific providers.

This module is deliberately deterministic. LLM/semantic output may help route a
request into the coding profile, but it cannot directly name external authority.
Browser authority is inferred from concrete UI/browser verification work; MCP
authority is limited to tools already declared in the operator policy.
"""
from __future__ import annotations

import re

from .capabilities import browser_capability_ids
from .mcp_policy import infer_mcp_capabilities_for_task

_BROWSER_EXPLICIT = re.compile(
    r"\b(?:agent[- ]browser|browser\s+(?:test|testing|automation|validation|verify|verification)|"
    r"e2e|end[- ]to[- ]end|playwright|visual\s+(?:test|testing|validation|regression)|"
    r"click\s+(?:through|the)|interact\s+with\s+(?:the\s+)?(?:page|ui|app))\b",
    re.I,
)
_UI_SURFACE = re.compile(
    r"\b(?:frontend|front[- ]end|ui|ux|web\s+(?:app|page|screen)|html|css|react|vue|"
    r"button|form|modal|dialog|dropdown|menu|tab|sidebar|theme|light\s+mode|dark\s+mode)\b",
    re.I,
)
_UI_ACTION = re.compile(
    r"\b(?:implement|fix|debug|change|update|refactor|edit|modify|add|remove|style|restyle|"
    r"test|verify|validate|reproduce|check|inspect)\b",
    re.I,
)
_BROWSER_FORBIDDEN = re.compile(
    r"\b(?:do not|don't|never|without)\s+(?:use|open|run|launch)?\s*(?:the\s+)?"
    r"(?:browser|agent[- ]browser|playwright)\b",
    re.I,
)


def task_requires_browser_authority(task: str) -> bool:
    text = str(task or "")
    if _BROWSER_FORBIDDEN.search(text):
        return False
    return bool(
        _BROWSER_EXPLICIT.search(text)
        or (_UI_SURFACE.search(text) and _UI_ACTION.search(text))
    )


def coding_external_capabilities_for_task(task: str) -> tuple[str, ...]:
    external: list[str] = []
    if task_requires_browser_authority(task):
        external.extend(browser_capability_ids())
    external.extend(infer_mcp_capabilities_for_task(task))
    return tuple(dict.fromkeys(external))
