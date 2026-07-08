from pathlib import Path

jobs = Path("src/app/assistant_memory/jobs.py")
text = jobs.read_text(encoding="utf-8")
text = text.replace("from typing import Any\n", "from typing import TYPE_CHECKING, Any\n", 1)
text = text.replace("from app.chat import ChatSessionStore\n", "", 1)
needle = "from .service import MemoryService, default_memory_service\n"
replacement = needle + "\nif TYPE_CHECKING:\n    from app.chat import ChatSessionStore\n"
if text.count(needle) != 1:
    raise SystemExit("jobs service import marker missing")
text = text.replace(needle, replacement, 1)
jobs.write_text(text, encoding="utf-8")

store = Path("src/app/chat/prompt_store.py")
text = store.read_text(encoding="utf-8")
old = "from app.assistant_memory import MemoryService, default_memory_service\n\nfrom .memory_commands import execute_memory_command, parse_memory_command\nfrom app.assistant_memory.jobs import enqueue_memory_suggestion_job\n"
new = "from app.assistant_memory import MemoryService, default_memory_service\nfrom app.assistant_memory.jobs import enqueue_memory_suggestion_job\n\nfrom .memory_commands import execute_memory_command, parse_memory_command\n"
if text.count(old) != 1:
    raise SystemExit("prompt store import block missing")
store.write_text(text.replace(old, new, 1), encoding="utf-8")
