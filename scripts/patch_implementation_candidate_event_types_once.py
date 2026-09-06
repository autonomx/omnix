from pathlib import Path

path = Path("src/app/agent_runtime/contracts.py")
text = path.read_text(encoding="utf-8")
needle = '    "quality.repair_requested",\n'
replacement = (
    '    "quality.implementation_continuation_requested",\n'
    '    "quality.implementation_candidate_exhausted",\n'
    + needle
)
if '"quality.implementation_continuation_requested"' not in text:
    if needle not in text:
        raise SystemExit("contracts event-type anchor not found")
    text = text.replace(needle, replacement, 1)
    path.write_text(text, encoding="utf-8")
print("implementation candidate event types patched")
