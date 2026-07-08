from pathlib import Path
path = Path("src/tests/unit/chat/test_compaction.py")
text = path.read_text(encoding="utf-8")
old = '    assert "Conversation detail 0" in first.summary\n'
new = '    assert "Always preserve decision 0" in first.summary\n'
if text.count(old) != 1:
    raise SystemExit("summary assertion pattern missing")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
