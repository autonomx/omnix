from pathlib import Path

path = Path("apps/web/src/features/chatbot/MemoryManagementPanel.tsx")
text = path.read_text(encoding="utf-8")
text = text.replace(
    "import { CharacterModePanel } from './CharacterModePanel';\n",
    "import { CharacterManagementPanel } from './CharacterManagementPanel';\nimport { CharacterModePanel } from './CharacterModePanel';\n",
    1,
)
old_empty = "  if (!sessionId) return <section className=\"assistant-view-panel memory-management-panel\" aria-label=\"Memory view\"><p className=\"eyebrow\">Omnix Assistant</p><h2>Memory</h2><p>Create or select a Chat session before managing memory.</p></section>;"
new_empty = "  if (!sessionId) return <section className=\"assistant-view-panel memory-management-panel\" aria-label=\"Memory view\"><p className=\"eyebrow\">Omnix Assistant</p><h2>Memory</h2><p>Create or select a Chat session to manage session memory. Character profiles remain available below.</p><CharacterManagementPanel /></section>;"
if text.count(old_empty) != 1:
    raise RuntimeError(f"expected one empty-session return, found {text.count(old_empty)}")
text = text.replace(old_empty, new_empty, 1)
old_panel = "      <CharacterModePanel sessionId={sessionId} />\n"
new_panel = "      <CharacterModePanel sessionId={sessionId} />\n      <CharacterManagementPanel />\n"
if text.count(old_panel) != 1:
    raise RuntimeError(f"expected one character mode panel, found {text.count(old_panel)}")
path.write_text(text.replace(old_panel, new_panel, 1), encoding="utf-8")
