"""Start the Omnix gateway with PostgreSQL authority established first."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--app", default="app.production:app")
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--api-replicas", type=int, default=None)
    parser.add_argument("--managed-stdin", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify PostgreSQL startup and exit without serving",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.check:
        from app.persistence.startup import bootstrap_status_payload

        print(json.dumps(bootstrap_status_payload(), sort_keys=True))
        return 0

    import uvicorn

    from gateway_cluster import replica_ports, serve_cluster, watch_parent_stdin

    count = args.api_replicas
    if count is None:
        configured = os.environ.get("OMNIX_GATEWAY_API_REPLICAS")
        path = Path(__file__).resolve().parents[1] / "resources/data/gateway-deployment.json"
        if configured is None and path.exists():
            configured = json.loads(path.read_text(encoding="utf-8")).get("api_replicas", 0)
        count = int(configured or 0)
    replica_ports(args.port, count)
    if count:
        return serve_cluster(args, count)
    if args.managed_stdin:
        if args.reload:
            raise ValueError("Managed gateway shutdown requires reload disabled")
        server = uvicorn.Server(uvicorn.Config(args.app, host=args.host, port=args.port))
        watch_parent_stdin(server)
        server.run()
        return 0

    uvicorn.run(
        args.app,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
