"""Rehearse a restore into a disposable database and blob root (WP-10.7).

    python scripts/restore_rehearsal.py --backup-dir backups/2026-10-02 \\
        --target-url postgresql://omnix:omnix@127.0.0.1:55433/omnix_restore_test \\
        --blob-root /tmp/omnix-restore-blobs --output artifacts/restore-rehearsal.json

The target database must be disposable (its name contains ``test``, ``bench``
or ``rehearsal``) and is overwritten (``pg_restore --clean``). The rehearsal:

1. checks every backup file against the manifest's SHA-256;
2. restores the database dump into the target;
3. runs ``python -m app.persistence verify`` there (healthy, no migration drift;
   pending migrations are applied first when the backup predates this revision);
4. compares the main tables' row counts with the manifest;
5. extracts the blobs into the blob root and checks the sampled hashes.

The report records each step's result and the total time, the measured
recovery time for this volume.
"""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
import time
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backup_omnix import persistence_cli, sha256_file, table_counts  # noqa: E402

DISPOSABLE_MARKERS = ("test", "bench", "rehearsal")


def require_disposable(url: str) -> None:
    name = urlsplit(url).path.lstrip("/")
    if not any(marker in name for marker in DISPOSABLE_MARKERS):
        raise SystemExit(f"refusing to restore into {name!r}: the database name must contain one of {DISPOSABLE_MARKERS}")


def verify_files(backup_dir: Path, manifest: dict) -> None:
    for name, expected in manifest["files"].items():
        path = backup_dir / name
        if not path.is_file():
            raise RuntimeError(f"backup file is missing: {name}")
        if sha256_file(path) != expected["sha256"]:
            raise RuntimeError(f"backup file does not match its manifest checksum: {name}")


def restore_blobs(backup_dir: Path, manifest: dict, blob_root: Path) -> dict:
    blobs = manifest["blobs"]
    if blobs.get("backend") != "local":
        return {"skipped": "s3 backend: objects are restored from bucket versions"}
    if blob_root.exists() and any(blob_root.iterdir()):
        raise SystemExit(f"{blob_root} is not empty")
    blob_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(backup_dir / "blobs.tar.gz", "r:gz") as archive:
        archive.extractall(blob_root, filter="data")
    restored = sum(1 for path in blob_root.rglob("*") if path.is_file())
    mismatched = [name for name, digest in blobs["sample"].items()
                  if not (blob_root / name).is_file() or sha256_file(blob_root / name) != digest]
    if restored != blobs["files"] or mismatched:
        raise RuntimeError(f"blob restore mismatch: {restored}/{blobs['files']} files, sample mismatches {mismatched[:5]}")
    return {"files": restored, "sample_checked": len(blobs["sample"])}


def rehearse(backup_dir: Path, target_url: str, blob_root: Path) -> dict:
    require_disposable(target_url)
    started = time.perf_counter()
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    steps: dict[str, object] = {}
    verify_files(backup_dir, manifest)
    steps["checksums"] = "ok"
    persistence_cli("restore", "--clean", str(backup_dir / "database.dump"), url=target_url)
    steps["database_restore"] = "ok"
    status = persistence_cli("status", url=target_url)
    if status.get("pending"):
        persistence_cli("migrate", url=target_url)
        steps["migrations_applied"] = list(status["pending"])
    persistence_cli("verify", url=target_url)
    steps["verify"] = "ok"
    restored_counts = table_counts(target_url)
    differences = {table: {"backup": count, "restored": restored_counts.get(table)}
                   for table, count in manifest["table_counts"].items() if restored_counts.get(table) != count}
    if differences:
        raise RuntimeError(f"row counts differ after restore: {differences}")
    steps["table_counts"] = restored_counts
    steps["blobs"] = restore_blobs(backup_dir, manifest, blob_root)
    return {
        "ok": True,
        "backup_created_at": manifest["created_at"],
        "schema_version": manifest["schema_version"],
        "steps": steps,
        "restore_seconds": round(time.perf_counter() - started, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--target-url", required=True, help="a disposable database (name contains test, bench or rehearsal)")
    parser.add_argument("--blob-root", type=Path, required=True, help="an empty directory for the restored blobs")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = rehearse(args.backup_dir, args.target_url, args.blob_root)
    except RuntimeError as exc:
        report = {"ok": False, "error": str(exc)}
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
