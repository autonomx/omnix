from __future__ import annotations

from pathlib import Path

path = Path("src/app/agent_runtime/evidence.py")
text = path.read_text(encoding="utf-8")
needle = '''    external = list(evidence.required_external)\n    if profile.id == "house":\n'''
replacement = '''    external = list(evidence.required_external)\n    if profile.id == "coding":\n        # Browser and MCP providers remain outside Pi. Deterministic task\n        # compilation may issue only capabilities already inside the coding\n        # profile ceiling; MCP ids originate exclusively from operator policy.\n        from .coding_external_authority import coding_external_capabilities_for_task\n\n        external.extend(coding_external_capabilities_for_task(text))\n    if profile.id == "house":\n'''
if text.count(needle) != 1:
    raise SystemExit(f"expected one authority insertion point, found {text.count(needle)}")
path.write_text(text.replace(needle, replacement), encoding="utf-8")
