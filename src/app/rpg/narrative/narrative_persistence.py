"""Narrative Event Persistence — Database storage for narrative events.

This module provides persistence for NarrativeEvent objects, enabling
save/load functionality for game sessions and historical event querying.

Purpose:
    Add NarrativeEvent serialization to database for save/load functionality,
    and enable querying historical events for story analysis.

Usage:
    store = NarrativeEventStore(db_path="narrative_events.db")
    store.save_events(events)
    history = store.get_history(limit=50)
    session_events = store.get_session_events(session_id)

Storage Formats:
    - SQLite (default, file-based)
    - In-memory (for testing)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from .narrative_event import NarrativeEvent

logger = logging.getLogger(__name__)

# Database schema
SCHEMA = """
CREATE TABLE IF NOT EXISTS narrative_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    description TEXT NOT NULL,
    actors TEXT NOT NULL DEFAULT '[]',
    location TEXT,
    importance REAL NOT NULL DEFAULT 0.5,
    emotional_weight REAL NOT NULL DEFAULT 0.0,
    tags TEXT NOT NULL DEFAULT '[]',
    session_id TEXT,
    tick INTEGER DEFAULT 0,
    timestamp REAL NOT NULL,
    raw_event TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_type ON narrative_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_session ON narrative_events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON narrative_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_importance ON narrative_events(importance DESC);
"""


class NarrativeEventStore:
    """Persistent storage for narrative events.
    
    Stores NarrativeEvent objects in SQLite database with efficient
    indexing for session-based retrieval and time-range queries.
    
    Attributes:
        db_path: Path to SQLite database file.
        session_id: Current session identifier.
    """
    
    def __init__(self, db_path: str = "narrative_events.db", session_id: str | None = None):
        """Initialize the event store.
        
        Args:
            db_path: Path to SQLite database. Use ":memory:" for in-memory.
            session_id: Session identifier for grouping events.
        """
        self.db_path = db_path
        self.session_id = session_id or f"session_{int(time.time())}"
        self._init_db()
    
    def _init_db(self) -> None:
        """Create database and tables if they don't exist."""
        with self._connect() as conn:
            conn.executescript(SCHEMA)
    
    def _connect(self) -> sqlite3.Connection:
        """Create a database connection.
        
        Returns:
            SQLite connection with row factory.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def save_events(
        self,
        events: List[NarrativeEvent],
        session_id: str | None = None,
        tick: int = 0,
    ) -> int:
        """Save narrative events to database.
        
        Args:
            events: List of NarrativeEvent objects to save.
            session_id: Session identifier. Uses store's session_id if None.
            tick: Simulation tick number.
        
        Returns:
            Number of events saved.
        """
        sid = session_id or self.session_id
        
        with self._connect() as conn:
            for event in events:
                conn.execute(
                    """INSERT OR REPLACE INTO narrative_events 
                       (id, event_type, description, actors, location,
                        importance, emotional_weight, tags, session_id, tick,
                        timestamp, raw_event)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event.id,
                        event.type,
                        event.description,
                        json.dumps(event.actors),
                        event.location,
                        event.importance,
                        event.emotional_weight,
                        json.dumps(event.tags),
                        sid,
                        tick,
                        time.time(),
                        json.dumps(event.raw_event) if event.raw_event else None,
                    ),
                )
            conn.commit()
        
        return len(events)
    
    def get_history(
        self,
        limit: int = 100,
        offset: int = 0,
        event_type: str | None = None,
        min_importance: float = 0.0,
    ) -> List[NarrativeEvent]:
        """Query historical events.
        
        Args:
            limit: Maximum events to return.
            offset: Offset for pagination.
            event_type: Filter by event type.
            min_importance: Filter by minimum importance.
        
        Returns:
            List of NarrativeEvent objects ordered by timestamp desc.
        """
        conditions = []
        params: List[Any] = []
        
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        
        if min_importance > 0:
            conditions.append("importance >= ?")
            params.append(min_importance)
        
        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)
        
        params.extend([limit, offset])
        
        query = f"""
            SELECT * FROM narrative_events
            {where}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
        """
        
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        
        return [self._row_to_event(row) for row in rows]
    
    def get_session_events(
        self,
        session_id: str | None = None,
        limit: int = 100,
    ) -> List[NarrativeEvent]:
        """Get events for a specific session.
        
        Args:
            session_id: Session identifier. Uses store's session_id if None.
            limit: Maximum events to return.
        
        Returns:
            List of NarrativeEvent objects for the session.
        """
        sid = session_id or self.session_id
        return self.get_history(limit=limit, event_type=None, min_importance=0)
    
    def get_session_ids(self) -> List[str]:
        """Get list of all session IDs in the database.
        
        Returns:
            List of unique session ID strings.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT session_id FROM narrative_events WHERE session_id IS NOT NULL"
            ).fetchall()
        return [row["session_id"] for row in rows]
    
    def get_event_counts(self, session_id: str | None = None) -> Dict[str, int]:
        """Get event counts by type.
        
        Args:
            session_id: Optional session filter.
        
        Returns:
            Dict of event_type -> count.
        """
        where = ""
        params: List[Any] = []
        
        if session_id:
            where = "WHERE session_id = ?"
            params.append(session_id)
        
        query = f"""
            SELECT event_type, COUNT(*) as count
            FROM narrative_events
            {where}
            GROUP BY event_type
            ORDER BY count DESC
        """
        
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        
        return {row["event_type"]: row["count"] for row in rows}
    
    def delete_session(self, session_id: str) -> int:
        """Delete all events for a session.
        
        Args:
            session_id: Session to delete.
        
        Returns:
            Number of events deleted.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM narrative_events WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
        return cursor.rowcount
    
    def clear_all(self) -> None:
        """Delete all events from the database."""
        with self._connect() as conn:
            conn.execute("DELETE FROM narrative_events")
            conn.commit()
    
    def get_total_count(self) -> int:
        """Get total number of events stored.
        
        Returns:
            Event count.
        """
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) as count FROM narrative_events").fetchone()
        return row["count"]
    
    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> NarrativeEvent:
        """Convert a database row to a NarrativeEvent.
        
        Args:
            row: SQLite row object.
        
        Returns:
            NarrativeEvent instance.
        """
        raw_event = row["raw_event"]
        if raw_event:
            try:
                raw_event = json.loads(raw_event)
            except (json.JSONDecodeError, TypeError):
                raw_event = {}
        
        return NarrativeEvent(
            id=row["id"],
            type=row["event_type"],
            description=row["description"],
            actors=json.loads(row["actors"]),
            location=row["location"],
            importance=row["importance"],
            emotional_weight=row["emotional_weight"],
            tags=json.loads(row["tags"]),
            raw_event=raw_event or {},
        )