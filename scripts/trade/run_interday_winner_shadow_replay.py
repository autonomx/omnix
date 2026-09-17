from __future__ import annotations

"""Stable entry point for the dependency-aware interday SHADOW replay."""

from typing import Any

from scripts.trade import run_interday_winner_shadow_replay_dependency_v2 as _impl


def main() -> int:
    return _impl.main()


def __getattr__(name: str) -> Any:
    return getattr(_impl, name)


if __name__ == "__main__":
    raise SystemExit(main())
