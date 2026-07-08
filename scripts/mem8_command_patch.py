from pathlib import Path

path = Path("src/app/chat/memory_commands.py")
text = path.read_text(encoding="utf-8")
old = "_UPDATE_PATTERN = re.compile(r\"^update\\s+memory\\s+([^:]+)\\s*:\\s*(.+)$\", re.IGNORECASE | re.DOTALL)"
new = "_UPDATE_PATTERN = re.compile(r\"^update\\s+memory\\s+(memory:[A-Za-z0-9_.-]+)\\s*:\\s*(.+)$\", re.IGNORECASE | re.DOTALL)"
if text.count(old) != 1:
    raise SystemExit("update command pattern not found exactly once")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
