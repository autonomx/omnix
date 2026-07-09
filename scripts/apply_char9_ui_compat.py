from pathlib import Path

panel = Path("apps/web/src/features/chatbot/CharacterManagementPanel.tsx")
text = panel.read_text(encoding="utf-8")
text = text.replace("<details><summary>Character memories</summary>", "<details open><summary>Character memories</summary>", 1)
text = text.replace("<details><summary>Pending suggestions</summary>", "<details open><summary>Pending suggestions</summary>", 1)
panel.write_text(text, encoding="utf-8")

memory = Path("apps/web/src/features/chatbot/MemoryManagementPanel.tsx")
text = memory.read_text(encoding="utf-8")
old = "<p>Create or select a Chat session to manage session memory. Character profiles remain available below.</p>"
new = "<p>Create or select a Chat session before managing memory.</p><p>Character profiles remain available below.</p>"
if text.count(old) != 1:
    raise RuntimeError(f"expected one empty-state message, found {text.count(old)}")
memory.write_text(text.replace(old, new, 1), encoding="utf-8")
