"""Move live-call activation before asynchronous runtime preload."""
from pathlib import Path

path = Path("apps/web/src/features/chatbot/ChatbotWorkspace.tsx")
text = path.read_text(encoding="utf-8")
old = """    setActiveUtilityPanel('voice');
    setAudioStatus('Preloading live-call identity, voice, and memory context…');
    try {
"""
new = """    setActiveUtilityPanel('voice');
    liveVoiceActiveRef.current = true;
    setCallStartedAt(Date.now());
    setCallElapsedMs(0);
    setAudioStatus('Preloading live-call identity, voice, and memory context…');
    try {
"""
if text.count(old) != 1:
    raise RuntimeError(f"expected one activation prelude, found {text.count(old)}")
text = text.replace(old, new, 1)
old_duplicate = """      liveCallRuntimeRef.current = runtime;
      setLiveCallRuntime(runtime);
      liveVoiceActiveRef.current = true;
      setCallStartedAt(Date.now());
      setCallElapsedMs(0);
"""
new_duplicate = """      liveCallRuntimeRef.current = runtime;
      setLiveCallRuntime(runtime);
"""
if text.count(old_duplicate) != 1:
    raise RuntimeError(f"expected one deferred activation block, found {text.count(old_duplicate)}")
path.write_text(text.replace(old_duplicate, new_duplicate, 1), encoding="utf-8")
