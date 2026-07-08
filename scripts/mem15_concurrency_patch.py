from pathlib import Path

store = Path("src/app/chat/store.py")
text = store.read_text(encoding="utf-8")
marker = "from .models import (\n"
replacement = "from .concurrency import serialized_chat_mutation\n\n" + marker
if text.count(marker) != 1:
    raise SystemExit("store import marker missing")
text = text.replace(marker, replacement, 1)
for signature in (
    "    def create_session(self, request: CreateChatSessionRequest) -> ChatSession:\n",
    "    def delete_session(self, session_id: str) -> bool:\n",
    "    def append_user_message(\n",
    "    def begin_user_message(\n",
    "    def complete_streamed_reply(\n",
):
    if text.count(signature) != 1:
        raise SystemExit(f"mutation signature missing: {signature!r}")
    text = text.replace(signature, "    @serialized_chat_mutation\n" + signature, 1)
old = """    def _save_sessions(self, sessions: list[ChatSession]) -> None:
        payload = {"sessions": [session.model_dump(mode="json") for session in sessions]}
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
"""
new = """    def _save_sessions(self, sessions: list[ChatSession]) -> None:
        payload = {"sessions": [session.model_dump(mode="json") for session in sessions]}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)
"""
if text.count(old) != 1:
    raise SystemExit("atomic save block missing")
store.write_text(text.replace(old, new, 1), encoding="utf-8")

memory_session = Path("src/app/chat/memory_session.py")
text = memory_session.read_text(encoding="utf-8")
marker = "from .models import ChatSession\n"
replacement = "from .concurrency import CHAT_MUTATION_LOCK\n" + marker
if text.count(marker) != 1:
    raise SystemExit("memory session import marker missing")
text = text.replace(marker, replacement, 1)
old = """    with _SESSION_MEMORY_LOCK:
        sessions = store._load_sessions()
"""
new = """    with _SESSION_MEMORY_LOCK, CHAT_MUTATION_LOCK:
        sessions = store._load_sessions()
"""
if text.count(old) != 1:
    raise SystemExit("memory refresh lock block missing")
memory_session.write_text(text.replace(old, new, 1), encoding="utf-8")
