from __future__ import annotations

import threading


def _thread_label() -> str:
    current = threading.current_thread()
    return f"{current.name}:{current.ident}"