from pathlib import Path
path = Path("src/app/chat/prompt_store.py")
text = path.read_text(encoding="utf-8")
old = "                **self._active_memory_metadata(assembly, rendered),\n            **self._active_history_metadata(assembly),\n"
new = "                **self._active_memory_metadata(assembly, rendered),\n                **self._active_history_metadata(assembly),\n"
if text.count(old) != 1:
    raise SystemExit("stream metadata indentation pattern missing")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
