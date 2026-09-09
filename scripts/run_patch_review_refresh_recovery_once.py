from __future__ import annotations

from pathlib import Path
import runpy

core = Path("src/app/agent_runtime/service_core.py").read_text(encoding="utf-8")
if "resume_runtime_rehydration_failed" in core:
    print("review refresh/recovery patch already applied")
else:
    runpy.run_path("scripts/patch_review_refresh_recovery_once.py", run_name="__main__")
