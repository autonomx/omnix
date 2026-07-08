from pathlib import Path

backend = Path("src/tests/unit/assistant_memory/test_settings.py")
text = backend.read_text(encoding="utf-8")
old = '    assert "content" not in json.dumps(payload).casefold()\n'
new = '    assert "records" not in payload\n    assert "candidates" not in payload\n    assert "memory_ids" not in payload\n'
if text.count(old) != 1:
    raise SystemExit("backend diagnostics assertion missing")
backend.write_text(text.replace(old, new, 1), encoding="utf-8")

frontend = Path("apps/web/src/features/chatbot/MemoryManagementSettings.test.tsx")
text = frontend.read_text(encoding="utf-8")
old = "import { MemoryManagementPanel } from './MemoryManagementPanel';\n"
new = old + "import type { AssistantMemoryRuntimeStatus } from './memoryClient';\n"
if text.count(old) != 1:
    raise SystemExit("frontend import marker missing")
text = text.replace(old, new, 1)
old = "function settings(curated = false) {\n"
new = "function settings(curated = false): AssistantMemoryRuntimeStatus {\n"
if text.count(old) != 1:
    raise SystemExit("frontend settings function marker missing")
frontend.write_text(text.replace(old, new, 1), encoding="utf-8")
