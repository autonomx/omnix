"""Shared constants for the audiobook pipeline."""

# Canonical speaker name for narration segments.  Every module in the
# pipeline should compare against / fall back to this value so that
# "Narrator", "narrator", None, and "unknown" are all treated the same way.
NARRATOR = "Narrator"
