from pathlib import Path

path = Path("docs/CHAT_MEMORY_ROADMAP.md")
text = path.read_text(encoding="utf-8")
old_status = "Status: canonical implementation roadmap"
new_status = "Status: implementation complete through MEM-15; exact-head release gate required"
if text.count(old_status) != 1:
    raise SystemExit("roadmap status marker missing")
text = text.replace(old_status, new_status, 1)
old_heading = "## Current-state audit"
new_heading = "## Initial-state audit before MEM-1"
if text.count(old_heading) != 1:
    raise SystemExit("initial audit heading missing")
text = text.replace(old_heading, new_heading, 1)
marker = "Target branch: `rpg`\n"
block = """Target branch: `rpg`

## Final implementation status

MEM-0 through MEM-14 are merged into `rpg`. MEM-15 supplies the adversarial integration suite, process-local mutation serialization, atomic JSON fallback writes, rollout guidance, and rollback evidence. The roadmap is considered released only after the MEM-15 pull request passes both required GitHub Actions workflows on its exact head and is squash-merged.

Canonical phase evidence is stored under `docs/chat-memory/`, including the final `mem-15-release-gate.md` matrix.
"""
if text.count(marker) != 1:
    raise SystemExit("target branch marker missing")
text = text.replace(marker, block, 1)
path.write_text(text, encoding="utf-8")
