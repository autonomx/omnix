"""Container health probe: exit 0 when the URL answers 2xx (the images ship no curl)."""
from __future__ import annotations

import sys
import urllib.request


def main(argv: list[str]) -> int:
    url = argv[1] if len(argv) > 1 else "http://127.0.0.1:8000/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - fixed local probe URL
            return 0 if 200 <= response.status < 300 else 1
    except OSError:
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
