from pathlib import Path

path = Path("apps/web/src/features/chatbot/ChatbotWorkspace.tsx")
text = path.read_text(encoding="utf-8")
old = "    setAudioStatus('Preloading live-call identity, voice, and memory context…');"
new = "    setAudioStatus('Live voice call started.');"
if text.count(old) != 1:
    raise RuntimeError(f"expected one preload status, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
