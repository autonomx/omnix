from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
needle = '.replace("' + chr(92) + '", "/")'
replacement = '.replace(chr(92), "/")'
changed = 0
for path in (ROOT / "src").rglob("*.py"):
    text = path.read_text(encoding="utf-8")
    updated = text.replace(needle, replacement)
    if updated != text:
        path.write_text(updated, encoding="utf-8", newline="\n")
        changed += 1

# RunChangeSet identity serialization in service_core uses json.dumps. Keep the
# generated source explicit rather than letting the exception be swallowed by
# the fail-closed diff-capture boundary.
service_core = ROOT / "src" / "app" / "agent_runtime" / "service_core.py"
text = service_core.read_text(encoding="utf-8")
updated = text.replace("import hashlib\nimport os\n", "import hashlib\nimport json\nimport os\n", 1)
if updated != text:
    service_core.write_text(updated, encoding="utf-8", newline="\n")

# Server attribution may downgrade an LLM changes_required verdict only when it
# is fully explained by baseline-context findings. A bare changes_required or a
# finding that touches the run-owned subject remains fail-closed.
coding_quality = ROOT / "src" / "app" / "agent_runtime" / "coding_quality.py"
text = coding_quality.read_text(encoding="utf-8")
updated = text.replace(
    '''def review_is_acceptable(result: ReviewResult, revision: TaskRevision) -> bool:\n    if result.verdict != "approve":\n        return False\n''',
    '''def review_is_acceptable(result: ReviewResult, revision: TaskRevision) -> bool:\n    if result.verdict == "blocked":\n        return False\n    if result.verdict == "changes_required":\n        if not result.findings:\n            return False\n        if any(item.attribution != "baseline_context" for item in result.findings):\n            return False\n''',
    1,
)
if updated != text:
    coding_quality.write_text(updated, encoding="utf-8", newline="\n")

# Path-claim attribution is a protocol change, so give it a new durable protocol
# identity. Already-running/recovered v1/v2 reviewers may be consumed using the
# old schema, but they are treated conservatively: without an authoritative
# RunChangeSet claim they can never be downgraded to baseline_context.
review_runtime = ROOT / "src" / "app" / "agent_runtime" / "review_runtime.py"
text = review_runtime.read_text(encoding="utf-8")
text = text.replace(
    'REVIEW_PROTOCOL_VERSION = "review-v2"',
    'REVIEW_PROTOCOL_VERSION = "review-v3-subject-attribution"',
    1,
)
text = text.replace(
    'def review_payload_is_protocol_valid(text: str, revision: TaskRevision) -> bool:',
    'def review_payload_is_protocol_valid(\n    text: str,\n    revision: TaskRevision,\n    *,\n    require_path_claims: bool = True,\n) -> bool:',
    1,
)
text = text.replace(
    '''        if not isinstance(finding.get("subject_paths"), list) or not isinstance(finding.get("context_paths"), list):\n            return False\n        if any(not isinstance(path, str) for path in finding.get("subject_paths", [])):\n            return False\n        if any(not isinstance(path, str) for path in finding.get("context_paths", [])):\n            return False\n''',
    '''        if require_path_claims:\n            if not isinstance(finding.get("subject_paths"), list) or not isinstance(finding.get("context_paths"), list):\n                return False\n            if any(not isinstance(path, str) for path in finding.get("subject_paths", [])):\n                return False\n            if any(not isinstance(path, str) for path in finding.get("context_paths", [])):\n                return False\n''',
    1,
)
review_runtime.write_text(text, encoding="utf-8", newline="\n")

review_orchestration = ROOT / "src" / "app" / "agent_runtime" / "review_orchestration.py"
text = review_orchestration.read_text(encoding="utf-8")
text = text.replace(
    'protocol_version="review-v1-legacy" if _slot_from_child(child) is None else REVIEW_PROTOCOL_VERSION,',
    'protocol_version="review-v1-legacy" if _slot_from_child(child) is None else "review-v2-legacy",',
    1,
)
text = text.replace(
    'elif not review_payload_is_protocol_valid(text, revision):',
    'elif not review_payload_is_protocol_valid(\n        text,\n        revision,\n        require_path_claims=attempt.protocol_version == REVIEW_PROTOCOL_VERSION,\n    ):',
    1,
)
review_orchestration.write_text(text, encoding="utf-8", newline="\n")

quality_recovery = ROOT / "src" / "app" / "agent_runtime" / "quality_recovery.py"
text = quality_recovery.read_text(encoding="utf-8")
text = text.replace(
    '''            if not review_payload_is_protocol_valid(text, revision):\n                continue\n''',
    '''            get_attempt = getattr(quality, "get_review_attempt_by_reviewer", None)\n            attempt = get_attempt(child.run_id) if callable(get_attempt) else None\n            require_path_claims = bool(\n                attempt is not None\n                and attempt.protocol_version == "review-v3-subject-attribution"\n            )\n            if not review_payload_is_protocol_valid(\n                text,\n                revision,\n                require_path_claims=require_path_claims,\n            ):\n                continue\n''',
    1,
)
quality_recovery.write_text(text, encoding="utf-8", newline="\n")

# UI token availability is explicit. Numeric fixture values represent reported
# telemetry only when the corresponding availability flags are true; otherwise
# the UI intentionally renders "Not reported" even when the numeric fallback is
# nonzero. Keep the existing progress/evidence fixture semantically reported.
run_card_test = ROOT / "src" / "apps" / "web" / "src" / "features" / "chatbot" / "OmnixRunCard.test.tsx"
text = run_card_test.read_text(encoding="utf-8")
updated = text.replace(
    "usage: { input_tokens: 1234, output_tokens: 567 },",
    "usage: { input_tokens: 1234, output_tokens: 567, input_tokens_reported: true, output_tokens_reported: true },",
    1,
)
if updated != text:
    run_card_test.write_text(updated, encoding="utf-8", newline="\n")

# The regression transformer contains a regex block replacement whose generated
# source deliberately includes escaped newlines. Python re.sub interprets
# backslashes in a string replacement template, which would turn those escapes
# into literal line breaks inside a quoted Python string. Use a callback so the
# replacement text is inserted byte-for-byte.
regression_fixer = ROOT / "scripts" / "fix_pr1519_candidate_authority_regressions.py"
if regression_fixer.exists():
    text = regression_fixer.read_text(encoding="utf-8")
    updated = text.replace(
        "updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)",
        "updated, count = re.subn(pattern, lambda _match: replacement, text, count=1, flags=re.S)",
    )
    if updated != text:
        regression_fixer.write_text(updated, encoding="utf-8", newline="\n")

print(f"normalized generated path literals in {changed} files")
