#!/usr/bin/env python3
"""Canonical Omnix FastAPI gateway entrypoint."""

import uvicorn

from app.production import app
from app.runtime.net import bind_host


HOST = bind_host()
PORT = 8000


def create_app():
    return app


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("Omnix Web Gateway")
    print("=" * 50)
    print(f"Gateway: http://{HOST}:{PORT}")
    print("=" * 50 + "\n")

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
    )
