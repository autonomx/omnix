"""
Audiobook UX backend features: bookmarks, resume position, playback state, chapter indexing.

All data is persisted in JSON files under DATA_DIR/audiobooks/ux/<user_id>/.
"""

import os
import re
import json
import time
import uuid
import logging
from typing import List, Dict, Optional, Any, Callable

from flask import Blueprint, request, jsonify

import app.shared as shared

logger = logging.getLogger(__name__)

audiobook_ux_bp = Blueprint('audiobook_ux', __name__)

# ──────────────────────────────────────────────────────────────────
# Data persistence helpers
# ──────────────────────────────────────────────────────────────────

_SAFE_ID_RE = re.compile(r'^[a-zA-Z0-9_\-]+$')


def _sanitize_id(value: str) -> str:
    """Sanitize a user-supplied identifier to prevent path traversal."""
    if not value or not _SAFE_ID_RE.match(value):
        raise ValueError(f"Invalid identifier: {value!r}")
    return value


def _ux_data_path(user_id: str, filename: str) -> str:
    """Return path to a UX data file for a user (safe from path traversal)."""
    safe_user = _sanitize_id(user_id)
    base = os.path.abspath(os.path.join(shared.DATA_DIR, "audiobooks", "ux"))
    user_path = os.path.abspath(os.path.join(base, safe_user))
    if not user_path.startswith(base + os.sep) and user_path != base:
        raise ValueError("Path traversal attempted")
    os.makedirs(user_path, exist_ok=True)
    return os.path.join(user_path, filename)


def _load_json(path: str) -> Any:
    """Load JSON file or return empty dict."""
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_json(path: str, data: Any) -> None:
    """Save data as JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def _get_user_id() -> str:
    """Extract user_id from request args or JSON body, defaulting to 'default'."""
    if request.is_json and request.get_json(silent=True):
        uid = request.get_json(silent=True).get("user_id")
        if uid:
            return str(uid)
    return request.args.get("user_id", "default")


# ──────────────────────────────────────────────────────────────────
# 1. BOOKMARKS
# ──────────────────────────────────────────────────────────────────

@audiobook_ux_bp.route('/api/audiobook/bookmark', methods=['POST'])
def create_bookmark():
    """Create a bookmark. Body: {user_id, book_id, position, note?}"""
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id", "default")
    book_id = data.get("book_id")
    position = data.get("position")

    if not book_id:
        return jsonify({"success": False, "error": "book_id is required"}), 400
    if position is None:
        return jsonify({"success": False, "error": "position is required"}), 400

    try:
        _sanitize_id(user_id)
    except ValueError:
        return jsonify({"success": False, "error": "Invalid user_id"}), 400

    try:
        position = float(position)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "position must be a number"}), 400

    path = _ux_data_path(user_id, "bookmarks.json")
    store = _load_json(path)
    if "bookmarks" not in store:
        store["bookmarks"] = []

    bookmark = {
        "id": uuid.uuid4().hex[:12],
        "user_id": user_id,
        "book_id": book_id,
        "position": position,
        "note": data.get("note", ""),
        "created_at": time.time(),
    }
    store["bookmarks"].append(bookmark)
    _save_json(path, store)

    return jsonify({"success": True, "bookmark": bookmark})


@audiobook_ux_bp.route('/api/audiobook/bookmarks', methods=['GET'])
def get_bookmarks():
    """Get all bookmarks. Query params: user_id, book_id?"""
    user_id = request.args.get("user_id", "default")
    book_id = request.args.get("book_id")

    path = _ux_data_path(user_id, "bookmarks.json")
    store = _load_json(path)
    bookmarks = store.get("bookmarks", [])

    if book_id:
        bookmarks = [b for b in bookmarks if b.get("book_id") == book_id]

    return jsonify({"success": True, "bookmarks": bookmarks})


@audiobook_ux_bp.route('/api/audiobook/bookmark/<bookmark_id>', methods=['DELETE'])
def delete_bookmark(bookmark_id):
    """Delete a bookmark. Query params: user_id"""
    user_id = request.args.get("user_id", "default")

    path = _ux_data_path(user_id, "bookmarks.json")
    store = _load_json(path)
    bookmarks = store.get("bookmarks", [])

    original_len = len(bookmarks)
    bookmarks = [b for b in bookmarks if b.get("id") != bookmark_id]

    if len(bookmarks) == original_len:
        return jsonify({"success": False, "error": "Bookmark not found"}), 404

    store["bookmarks"] = bookmarks
    _save_json(path, store)

    return jsonify({"success": True})


# ──────────────────────────────────────────────────────────────────
# 2. RESUME POSITION (auto-save every 10-15 seconds from client)
# ──────────────────────────────────────────────────────────────────

@audiobook_ux_bp.route('/api/audiobook/progress', methods=['POST'])
def save_progress():
    """Save reading progress. Body: {user_id, book_id, last_position}"""
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id", "default")
    book_id = data.get("book_id")
    last_position = data.get("last_position")

    if not book_id:
        return jsonify({"success": False, "error": "book_id is required"}), 400
    if last_position is None:
        return jsonify({"success": False, "error": "last_position is required"}), 400

    try:
        _sanitize_id(user_id)
    except ValueError:
        return jsonify({"success": False, "error": "Invalid user_id"}), 400

    try:
        last_position = float(last_position)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "last_position must be a number"}), 400

    path = _ux_data_path(user_id, "progress.json")
    store = _load_json(path)

    store[book_id] = {
        "user_id": user_id,
        "book_id": book_id,
        "last_position": last_position,
        "updated_at": time.time(),
    }
    _save_json(path, store)

    return jsonify({"success": True})


@audiobook_ux_bp.route('/api/audiobook/progress', methods=['GET'])
def get_progress():
    """Get reading progress. Query params: user_id, book_id"""
    user_id = request.args.get("user_id", "default")
    book_id = request.args.get("book_id")

    if not book_id:
        return jsonify({"success": False, "error": "book_id is required"}), 400

    path = _ux_data_path(user_id, "progress.json")
    store = _load_json(path)
    progress = store.get(book_id)

    if not progress:
        return jsonify({"success": True, "progress": None})

    return jsonify({"success": True, "progress": progress})


# ──────────────────────────────────────────────────────────────────
# 3. PLAYBACK STATE
# ──────────────────────────────────────────────────────────────────

@audiobook_ux_bp.route('/api/audiobook/playback-state', methods=['POST'])
def save_playback_state():
    """Save playback state. Body: {user_id, book_id, speed, voice, last_chunk, volume?}"""
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id", "default")
    book_id = data.get("book_id")

    if not book_id:
        return jsonify({"success": False, "error": "book_id is required"}), 400

    try:
        _sanitize_id(user_id)
    except ValueError:
        return jsonify({"success": False, "error": "Invalid user_id"}), 400

    speed = data.get("speed")
    voice = data.get("voice")
    last_chunk = data.get("last_chunk")

    if speed is None and voice is None and last_chunk is None:
        return jsonify({"success": False, "error": "At least one of speed, voice, or last_chunk is required"}), 400

    path = _ux_data_path(user_id, "playback_state.json")
    store = _load_json(path)

    existing = store.get(book_id, {})
    if speed is not None:
        try:
            existing["speed"] = float(speed)
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "speed must be a number"}), 400
    if voice is not None:
        existing["voice"] = str(voice)
    if last_chunk is not None:
        try:
            existing["last_chunk"] = int(last_chunk)
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "last_chunk must be an integer"}), 400
    if data.get("volume") is not None:
        try:
            existing["volume"] = float(data["volume"])
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "volume must be a number"}), 400

    existing["book_id"] = book_id
    existing["user_id"] = user_id
    existing["updated_at"] = time.time()

    store[book_id] = existing
    _save_json(path, store)

    return jsonify({"success": True, "playback_state": existing})


@audiobook_ux_bp.route('/api/audiobook/playback-state', methods=['GET'])
def get_playback_state():
    """Get playback state. Query params: user_id, book_id"""
    user_id = request.args.get("user_id", "default")
    book_id = request.args.get("book_id")

    if not book_id:
        return jsonify({"success": False, "error": "book_id is required"}), 400

    path = _ux_data_path(user_id, "playback_state.json")
    store = _load_json(path)
    state = store.get(book_id)

    if not state:
        return jsonify({"success": True, "playback_state": None})

    return jsonify({"success": True, "playback_state": state})


# ──────────────────────────────────────────────────────────────────
# 4. CHAPTER INDEXING
# ──────────────────────────────────────────────────────────────────

# Regex patterns for common chapter headings
_CHAPTER_PATTERNS = [
    # "Chapter 1", "Chapter One", "CHAPTER I", "Chapter 1: Title"
    re.compile(
        r'^[ \t]*(chapter)\s+'
        r'(\d+|one|two|three|four|five|six|seven|eight|nine|ten|'
        r'eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|'
        r'eighteen|nineteen|twenty|[ivxlc]+)'
        r'([  \t:.\-—][^\n]*)?$',
        re.IGNORECASE | re.MULTILINE,
    ),
    # "Part 1", "Part One", "PART I"
    re.compile(
        r'^[ \t]*(part)\s+'
        r'(\d+|one|two|three|four|five|six|seven|eight|nine|ten|'
        r'[ivxlc]+)'
        r'([  \t:.\-—][^\n]*)?$',
        re.IGNORECASE | re.MULTILINE,
    ),
    # "Prologue", "Epilogue", "Introduction", "Preface", "Afterword"
    re.compile(
        r'^[ \t]*(prologue|epilogue|introduction|preface|afterword|foreword)'
        r'([  \t:.\-—][^\n]*)?$',
        re.IGNORECASE | re.MULTILINE,
    ),
    # Standalone Roman numerals at the start of a line: "I.", "II.", "III.", "IV."
    re.compile(
        r'^[ \t]*((?=[IVXLC])M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3}))\.'
        r'([  \t:.\-—][^\n]*)?$',
        re.MULTILINE,
    ),
]


def detect_chapters(text: str, llm_fn: Optional[Callable] = None) -> List[Dict]:
    """Detect chapter boundaries in text.

    Uses regex first, then optional LLM fallback for non-standard formats.

    Args:
        text: The full book text.
        llm_fn: Optional callable(prompt) -> str for LLM-based detection.

    Returns:
        List of dicts: [{"title": "Chapter 1", "start": 0}, ...]
    """
    chapters: List[Dict] = []

    for pattern in _CHAPTER_PATTERNS:
        for match in pattern.finditer(text):
            title = match.group(0).strip()
            chapters.append({"title": title, "start": match.start()})

    # De-duplicate by start position and sort
    seen_starts: set = set()
    unique: List[Dict] = []
    for ch in sorted(chapters, key=lambda c: c["start"]):
        if ch["start"] not in seen_starts:
            seen_starts.add(ch["start"])
            unique.append(ch)
    chapters = unique

    if chapters:
        return chapters

    # LLM fallback
    if llm_fn is not None:
        try:
            prompt = (
                "Identify chapter or section boundaries in the following text. "
                "Return a JSON array of objects with 'title' and 'start' (character offset) keys. "
                "Only return the JSON array, nothing else.\n\n"
                + text[:5000]
            )
            result = llm_fn(prompt)
            # Try to parse JSON from the LLM response
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                if isinstance(parsed, list) and all(
                    isinstance(c, dict) and "title" in c and "start" in c
                    for c in parsed
                ):
                    return parsed
        except Exception as exc:
            logger.warning("LLM chapter detection failed: %s", exc)

    # Fallback: treat entire text as one chapter
    return [{"title": "Full Text", "start": 0}]


@audiobook_ux_bp.route('/api/audiobook/chapters', methods=['POST'])
def index_chapters():
    """Detect chapters in text. Body: {text, use_llm?}"""
    data = request.get_json(silent=True) or {}
    text = data.get("text")

    if not text:
        return jsonify({"success": False, "error": "text is required"}), 400

    use_llm = data.get("use_llm", False)
    llm_fn = None
    if use_llm:
        try:
            from app.audiobook import _llm_generate
            llm_fn = _llm_generate
        except ImportError:
            logger.warning("Could not import _llm_generate for LLM chapter detection")

    chapters = detect_chapters(text, llm_fn=llm_fn)

    return jsonify({"success": True, "chapters": chapters})
