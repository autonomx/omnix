"""Compatibility import for interactive response-quality cleanup tests.

The implementation lives in ``app.rpg.interactive_cli_response_quality`` so the
same presentation-only cleanup is available to runtime/CLI code, not just matrix
artifact post-processing.
"""

from app.rpg.interactive_cli_response_quality import *  # noqa: F401,F403
