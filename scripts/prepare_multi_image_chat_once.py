from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts/apply_multi_image_chat_once.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one occurrence, found {count}")
    return text.replace(old, new)


def main() -> None:
    text = TARGET.read_text(encoding="utf-8")

    broken_validation_replace = '''    replace_once(\n        relative,\n        ''' + "'''" + '''validate: (value) => (value.trim() || pastedChatImage || pastedChatTextFile) ? true : 'Enter a message, paste an image, or add a file before sending.' ''' + "'''" + ''',\n        ''' + "'''" + '''validate: (value) => (value.trim() || pastedChatImages.length > 0 || pastedChatTextFile) ? true : 'Enter a message, paste an image, or add a file before sending.' ''' + "'''" + ''',\n    )\n'''
    text = replace_once(text, broken_validation_replace, "", "remove brittle validation replacement")

    old_fallback = '''    path = _path(relative)\n    text = path.read_text(encoding="utf-8")\n    text = text.replace(\n        "validate: (value) => (value.trim() || pastedChatImage || pastedChatTextFile) ? true : 'Enter a message, paste an image, or add a file before sending.'",\n        "validate: (value) => (value.trim() || pastedChatImages.length > 0 || pastedChatTextFile) ? true : 'Enter a message, paste an image, or add a file before sending.'",\n    )\n    path.write_text(text, encoding="utf-8")\n'''
    new_fallback = '''    path = _path(relative)\n    text = path.read_text(encoding="utf-8")\n    before_validation = "validate: (value) => (value.trim() || pastedChatImage || pastedChatTextFile) ? true : 'Enter a message, paste an image, or add a file before sending.'"\n    after_validation = "validate: (value) => (value.trim() || pastedChatImages.length > 0 || pastedChatTextFile) ? true : 'Enter a message, paste an image, or add a file before sending.'"\n    if text.count(before_validation) != 1:\n        raise RuntimeError(f"ChatbotWorkspace.tsx: expected one attachment validation expression, found {text.count(before_validation)}")\n    path.write_text(text.replace(before_validation, after_validation), encoding="utf-8")\n'''
    text = replace_once(text, old_fallback, new_fallback, "assert validation replacement")

    old_pattern = "r'''  it\\('accepts a pasted image, previews it, and sends it with the chat message', async \\(\\) => \\{.*?\\n  \\}\\);\\n\\n  it\\('sends a text file chosen from the add menu through the normal chat request' '''"
    new_pattern = "r'''  it\\('accepts a pasted image, previews it, and sends it with the chat message', async \\(\\) => \\{.*?\\n  \\}\\);\\n\\n(?=  it\\('sends a text file chosen from the add menu through the normal chat request', async \\(\\) => \\{)'''"
    text = replace_once(text, old_pattern, new_pattern, "frontend test boundary pattern")

    old_replacement_tail = "    vi.stubGlobal('FileReader', originalFileReader);\\n  });\\n\\n  it('sends a text file chosen from the add menu through the normal chat request' ''',"
    new_replacement_tail = "    vi.stubGlobal('FileReader', originalFileReader);\\n  });\\n\\n''',"
    text = replace_once(text, old_replacement_tail, new_replacement_tail, "frontend test replacement boundary")

    TARGET.write_text(text, encoding="utf-8")
    print("Prepared asserted multi-image carrier.")


if __name__ == "__main__":
    main()
