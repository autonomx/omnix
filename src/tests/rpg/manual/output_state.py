from __future__ import annotations

import threading
from typing import Any, Dict, List

_OUTPUTS: Dict[str, List[str]] = {}
_TOKEN_USAGE_ROWS: List[Dict[str, Any]] = []
_REGRESSION_WARNING_ROWS: List[Dict[str, Any]] = []
_REGRESSION_WARNINGS: List[str] = []

_OUTPUT_LOCK = threading.RLock()
_TOKEN_USAGE_LOCK = threading.RLock()
_REGRESSION_WARNING_LOCK = threading.RLock()