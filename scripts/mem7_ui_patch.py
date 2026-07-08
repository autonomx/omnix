from pathlib import Path

path = Path("apps/web/src/features/chatbot/ChatbotWorkspace.tsx")
text = path.read_text(encoding="utf-8")

replacements = [
    (
        "import { AssistantToolSettingsPanel } from './AssistantToolSettingsPanel';",
        "import { AssistantToolSettingsPanel } from './AssistantToolSettingsPanel';\nimport { MemoryManagementPanel } from './MemoryManagementPanel';",
    ),
    (
        "              onShowTools={() => setActiveUtilityPanel('tools')}\n            />",
        "              onShowTools={() => setActiveUtilityPanel('tools')}\n              selectedSessionId={selectedSessionId}\n            />",
    ),
    (
        "function AssistantWorkspaceView({ activeView, assistantSettings, chatProviders,",
        "function AssistantWorkspaceView({ activeView, assistantSettings, selectedSessionId, chatProviders,",
    ),
    (
        "assistantSettings: AssistantSettings; chatProviders:",
        "assistantSettings: AssistantSettings; selectedSessionId: string | null; chatProviders:",
    ),
    (
        "if (activeView === 'memory') return <section className=\"assistant-view-panel\" aria-label=\"Memory view\"><p className=\"eyebrow\">Omnix Assistant</p><h2>Memory</h2><p>Review assistant-scoped memory and what is available to future chat, voice, tool, and context assembly flows.</p><div className=\"platform-grid\"><article><h3>Project memory</h3><p>Project-scoped memories are enabled for this assistant workspace.</p></article><article><h3>Conversation memory</h3><p>Current session events are persisted and replayable through the assistant workspace event store.</p></article></div></section>;",
        "if (activeView === 'memory') return <MemoryManagementPanel sessionId={selectedSessionId} />;",
    ),
    (
        "memoryCount: 0,",
        "memoryCount: Number((activeSession as ApiChatSession & { memory_record_count?: number })?.memory_record_count ?? 0),",
    ),
]

for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected one occurrence, found {count}: {old[:100]!r}")
    text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
