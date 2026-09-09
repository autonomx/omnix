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
    r"\b(?:agent[- ]browser|browser\.(?:assert_[a-z_]+|(?:open|snapshot|screenshot|get_text|get_attribute))|"
    r"browser\s+(?:test|testing|automation|validation|verify|verification)|"
    r"e2e|end[- ]to[- ]end|playwright|visual\s+(?:test|testing|validation|regression)|"
    r"click\s+(?:through|the)|interact\s+with\s+(?:the\s+)?(?:page|ui|app))\b",
    re.I,
)
# This predicate is intentionally a monotonic superset of the UI/web surface
# detector used by coding-quality validation. UI requirements are often phrased
# declaratively (for example, "the dropdown should show one name") and the
# semantic compiler can still classify those turns as workspace mutations even
# when the raw text contains no imperative action verb. Requiring a second
# action-word match here can therefore launch Pi without browser authority while
# the later quality contract correctly requires browser proof. Any coding task
# that names one of these concrete UI surfaces receives the governed browser
# capability set up front; the broker/origin policy still constrains execution.
# Representative parity is regression-tested in
# test_coding_browser_authority_alignment.py.
_UI_SURFACE = re.compile(
    r"\b(?:frontend|front[- ]end|ui|ux|web(?:\s+(?:app|page|screen))?|html|css|react|vue|typescript|tsx?|jsx?|"
    r"button|icon|element|component|layout|form|modal|dialog|dropdown|drop\s+down|menu|tab|side\s*bar|sidebar|"
    r"tool\s*bar|toolbar|header|footer|input|textarea|tooltip|badge|chip|theme|light\s+mode|dark\s+mode)\b",
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
    # Do not make authority depend on imperative wording. The coding quality
    # gate can require browser proof from a semantically mutating UI request
    # such as "the header should only show one name", so the run must already
    # possess the corresponding governed capability before Pi starts.
    return bool(_BROWSER_EXPLICIT.search(text) or _UI_SURFACE.search(text))


def coding_external_capabilities_for_task(task: str) -> tuple[str, ...]:
    external: list[str] = []
    if task_requires_browser_authority(task):
        external.extend(browser_capability_ids())
    external.extend(infer_mcp_capabilities_for_task(task))
    return tuple(dict.fromkeys(external))
