"""Detached worker entrypoint for process-backed inline feature jobs."""
from __future__ import annotations

import sys

from .inline_feature_jobs import execute_feature_job_by_id


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: python -m app.jobs.inline_feature_job_worker <db_path> <job_id>", file=sys.stderr)
        return 2

    db_path, job_id = args
    execute_feature_job_by_id(db_path, job_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
