#!/usr/bin/env python3
"""Canonical Omnix FastAPI gateway entrypoint."""

import uvicorn

from app.gateway.main import app


HOST = "127.0.0.1"
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
