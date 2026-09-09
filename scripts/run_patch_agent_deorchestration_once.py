from __future__ import annotations

from pathlib import Path
import runpy

planning = Path("src/app/agent_runtime/planning.py").read_text(encoding="utf-8")
if "planning_requirement_for_operation" in planning and "Return no server-authored semantic task taxonomy" in planning:
    print("agent de-orchestration patch already applied")
else:
    runpy.run_path("scripts/patch_agent_deorchestration_once.py", run_name="__main__")
