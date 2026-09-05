from __future__ import annotations

from pathlib import Path
import re


path = Path("src/app/agent_runtime/coding_quality.py")
text = path.read_text(encoding="utf-8")
replacement = '''def self_review_prompt(revision: TaskRevision, *, attempt: int) -> str:
    requirements = [item.model_dump(mode="json") for item in revision.requirements]
    schema = {
        "verdict": "approve|changes_required|blocked",
        "requirements": [
            {
                "requirement_id": "R",
                "status": "satisfied|partial|missing|not_applicable",
                "evidence": "...",
            }
        ],
        "findings": [
            {
                "severity": "blocker|high|medium|low",
                "category": "correctness",
                "file": None,
                "location": None,
                "problem": "...",
                "recommended_fix": None,
            }
        ],
        "missing_tests": [],
        "residual_risks": [],
    }
    return (
        f"Mandatory engineering self-review for quality attempt {attempt}. Do not declare completion yet.\\n"
        f"Authoritative requirements JSON: {json.dumps(requirements, ensure_ascii=False)}\\n"
        "Inspect the complete current diff, callers, interfaces, generated contracts, edge cases and regression coverage. "
        "Fix material issues before returning. Rerun required validation after the final mutation.\\n"
        f"Return ONLY one JSON object matching this schema: {json.dumps(schema, ensure_ascii=False)}"
    )


def validation_prompt'''
text, count = re.subn(
    r"def self_review_prompt\(revision: TaskRevision, \*, attempt: int\) -> str:.*?def validation_prompt",
    replacement,
    text,
    count=1,
    flags=re.S,
)
if count != 1:
    raise RuntimeError("structured self-review prompt block not found")
legacy = '''    self_review_ok = any(
        item.workspace_state_id == workspace_state.state_id
'''
guarded = '''    self_review_ok = any(
        isinstance(item, SelfReviewResult)
        and item.workspace_state_id == workspace_state.state_id
'''
if text.count(legacy) != 1:
    raise RuntimeError("self-review evidence guard block changed")
path.write_text(text.replace(legacy, guarded), encoding="utf-8")
print("hardening output normalized")
