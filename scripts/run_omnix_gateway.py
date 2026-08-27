"""Start the Omnix gateway with PostgreSQL authority established first."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--app", default="app.gateway.main:app")
    parser.add_argument("--reload", action="store_true")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify PostgreSQL startup and exit without serving",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    from app.persistence.startup import bootstrap_status_payload

    status = bootstrap_status_payload()
    if args.check:
        import json

        print(json.dumps(status, sort_keys=True))
        return 0

    from app.live_voice_hardware_policy import install_live_voice_hardware_policy

    install_live_voice_hardware_policy()

    import uvicorn

    uvicorn.run(
        args.app,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
