"""
Persistence layer for the AI Role-Playing System.

Handles save/load of game sessions to JSON files in resources/data/.
"""

import json
import os
from typing import Dict, List, Optional

from app.rpg.models import GameSession


def _get_data_path() -> str:
    """Get the path to the RPG data file."""
    from app.shared import RESOURCES_DIR
    data_dir = os.path.join(RESOURCES_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "rpg_games.json")


def load_all_games() -> Dict[str, dict]:
    """Load all game sessions from disk."""
    path = _get_data_path()
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_all_games(games: Dict[str, dict]) -> None:
    """Save all game sessions to disk."""
    path = _get_data_path()
    with open(path, "w") as f:
        json.dump(games, f, indent=2)


def save_game(session: GameSession) -> None:
    """Save a single game session."""
    games = load_all_games()
    games[session.session_id] = session.to_dict()
    save_all_games(games)


def load_game(session_id: str) -> Optional[GameSession]:
    """Load a single game session by ID."""
    games = load_all_games()
    data = games.get(session_id)
    if data:
        return GameSession.from_dict(data)
    return None


def delete_game(session_id: str) -> bool:
    """Delete a game session. Returns True if it existed."""
    games = load_all_games()
    if session_id in games:
        del games[session_id]
        save_all_games(games)
        return True
    return False


def list_games() -> List[Dict]:
    """List all saved game sessions (summary info only)."""
    games = load_all_games()
    summaries = []
    for sid, data in games.items():
        summaries.append({
            "session_id": sid,
            "world_name": data.get("world", {}).get("name", "Unknown"),
            "genre": data.get("world", {}).get("genre", "Unknown"),
            "player_name": data.get("player", {}).get("name", "Player"),
            "turn_count": data.get("turn_count", 0),
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
        })
    return summaries
