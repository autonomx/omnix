"""Back up an Omnix installation: database, blobs and a manifest (WP-10.7).

    python scripts/backup_omnix.py --output-dir backups/2026-10-02

Writes, into a new directory:

- ``database.dump``: ``pg_dump --format=custom`` as the migration role
  (``OMNIX_MIGRATION_DATABASE_URL``, else ``OMNIX_DATABASE_URL``), through
  ``python -m app.persistence backup``;
- ``blobs.tar.gz``: the local blob root (``OMNIX_BLOB_ROOT``, default
  ``resources/data/blobs``). With ``OMNIX_BLOB_BACKEND=s3`` no copy is made:
  rely on bucket versioning, and the manifest says so;
- ``manifest.json``: when, from which revision and schema, the row counts of
  the main tables, every file's SHA-256 and a sample of blob hashes, which
  ``scripts/restore_rehearsal.py`` checks after restoring.

Keep backups outside the repository; they hold every workspace's data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_VERSION = 1
BLOB_SAMPLE = 50
# Tables whose row counts the rehearsal compares after a restore.
COUNTED_TABLES = (
    "omnix_workspaces", "omnix_jobs", "omnix_job_events", "omnix_assets",
    "omnix_chat_sessions", "omnix_chat_messages", "omnix_agent_runs", "omnix_audit_events",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def migration_url() -> str:
    url = os.environ.get("OMNIX_MIGRATION_DATABASE_URL") or os.environ.get("OMNIX_DATABASE_URL")
    if not url:
        raise SystemExit("set OMNIX_MIGRATION_DATABASE_URL (or OMNIX_DATABASE_URL)")
    return url


def persistence_cli(*arguments: str, url: str) -> dict:
    """Run ``python -m app.persistence`` against ``url`` (as both runtime and migration URL)."""
    environment = {**os.environ, "OMNIX_DATABASE_URL": url, "OMNIX_MIGRATION_DATABASE_URL": url,
                   "PYTHONPATH": str(ROOT / "src")}
    completed = subprocess.run([sys.executable, "-m", "app.persistence", *arguments],
                               capture_output=True, text=True, env=environment, check=False)
    output = completed.stdout.strip()
    try:
        report = json.loads(output) if output else {}
    except json.JSONDecodeError:
        report = {"output": output[-2000:]}
    if completed.returncode != 0:
        raise RuntimeError(f"app.persistence {arguments[0]} failed: {report or completed.stderr[-2000:]}")
    return report


def table_counts(url: str) -> dict[str, int]:
    import psycopg

    counts: dict[str, int] = {}
    with psycopg.connect(url, autocommit=True) as connection:
        for table in COUNTED_TABLES:
            exists = connection.execute("SELECT to_regclass(%s)", (table,)).fetchone()[0]
            if exists is not None:
                counts[table] = int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
    return counts


def blob_root() -> Path:
    configured = os.environ.get("OMNIX_BLOB_ROOT")
    return Path(configured) if configured else ROOT / "resources" / "data" / "blobs"


def archive_blobs(root: Path, destination: Path) -> dict:
    files = sorted(path for path in root.rglob("*") if path.is_file()) if root.is_dir() else []
    with tarfile.open(destination, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=path.relative_to(root).as_posix())
    sample = random.Random(0).sample(files, min(BLOB_SAMPLE, len(files)))
    return {
        "backend": "local",
        "files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
        "sample": {path.relative_to(root).as_posix(): sha256_file(path) for path in sample},
    }


def backup(output_dir: Path) -> dict:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit(f"{output_dir} is not empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    url = migration_url()
    started = datetime.now(timezone.utc)
    status = persistence_cli("status", url=url)
    counts = table_counts(url)
    dump = output_dir / "database.dump"
    persistence_cli("backup", str(dump), url=url)
    if (os.environ.get("OMNIX_BLOB_BACKEND") or "local").strip().lower() == "s3":
        blobs = {"backend": "s3", "note": "Not copied: restore objects from the bucket's versions at this time."}
    else:
        blobs = archive_blobs(blob_root(), output_dir / "blobs.tar.gz")
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "created_at": started.isoformat(timespec="seconds"),
        "software_revision": os.environ.get("OMNIX_SOFTWARE_REVISION") or None,
        "schema_version": status.get("current_schema"),
        "table_counts": counts,
        "blobs": blobs,
        "files": {path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
                  for path in sorted(output_dir.iterdir()) if path.is_file()},
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = backup(args.output_dir)
    print(json.dumps({"ok": True, "output_dir": str(args.output_dir.resolve()),
                      "schema_version": manifest["schema_version"], "table_counts": manifest["table_counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
