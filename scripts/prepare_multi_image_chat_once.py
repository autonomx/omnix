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

    helper_anchor = '''def regex_replace_once(relative: str, pattern: str, replacement: str, *, flags: int = re.S) -> None:\n'''
    count_helper = '''def replace_exact_count(relative: str, old: str, new: str, *, expected: int) -> None:\n    path = _path(relative)\n    text = path.read_text(encoding="utf-8")\n    count = text.count(old)\n    if count != expected:\n        raise RuntimeError(f"{relative}: expected {expected} occurrences, found {count}: {old[:160]!r}")\n    path.write_text(text.replace(old, new), encoding="utf-8")\n\n\n'''
    text = replace_once(text, helper_anchor, count_helper + helper_anchor, "insert exact-count helper")

    duplicate_store_patch = """    replace_once(\n        relative,\n        '''            if request.image_data_url:\\n                message_metadata[\"image_data_url\"] = request.image_data_url\\n            if request.text_attachment:''',\n        '''            if request.image_data_urls:\\n                message_metadata[\"image_data_urls\"] = list(request.image_data_urls)\\n                # Keep the legacy first-image projection for older persisted consumers.\\n                message_metadata[\"image_data_url\"] = request.image_data_urls[0]\\n            if request.text_attachment:''',\n    )\n"""
    duplicate_store_replacement = duplicate_store_patch.replace("    replace_once(\n", "    replace_exact_count(\n", 1).replace("\n    )\n", "\n        expected=2,\n    )\n", 1)
    text = replace_once(text, duplicate_store_patch, duplicate_store_replacement, "patch both chat-store persistence paths")

    broken_validation_replace = """    replace_once(\n        relative,\n        '''validate: (value) => (value.trim() || pastedChatImage || pastedChatTextFile) ? true : 'Enter a message, paste an image, or add a file before sending.' ''',\n        '''validate: (value) => (value.trim() || pastedChatImages.length > 0 || pastedChatTextFile) ? true : 'Enter a message, paste an image, or add a file before sending.' ''',\n    )\n"""
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

    text = replace_once(
        text,
        "new ProgressEvent('load')));",
        "new ProgressEvent('load') as ProgressEvent<FileReader>));",
        "FileReader load event test typing",
    )

    TARGET.write_text(text, encoding="utf-8")
    print("Prepared asserted multi-image carrier.")


if __name__ == "__main__":
    main()
