"""Stable cross-package exception contracts."""


class LegacyPersistenceRetired(RuntimeError):
    """Raised when normal runtime attempts to use retired SQLite/JSON authority."""
