"""Compare Python allocation peaks for byte-buffered and streaming blob writes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.persistence.blob_store import LocalBlobStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size-mib", type=int, default=64)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.size_mib < 1:
        parser.error("size must be positive")
    results = {
        "schema_version": 1,
        "size_mib": args.size_mib,
        "memory_metric": "tracemalloc Python allocation peak, excludes OS file cache and native allocations",
    }
    with tempfile.TemporaryDirectory(prefix="omnix-blob-baseline-") as directory:
        root = Path(directory)
        source = root / "source.bin"
        with source.open("wb") as handle:
            block = b"x" * (1024 * 1024)
            for _ in range(args.size_mib):
                handle.write(block)
        store = LocalBlobStore(root / "blobs")
        records = []
        for name, operation in [
            ("buffered", lambda: store.put_bytes("buffered.bin", source.read_bytes())),
            ("streaming", lambda: store.put_file("streaming.bin", source)),
        ]:
            tracemalloc.start()
            started = time.perf_counter()
            records.append(operation())
            _, peak = tracemalloc.get_traced_memory()
            elapsed = (time.perf_counter() - started) * 1000
            tracemalloc.stop()
            results[name] = {
                "peak_python_mib": peak / (1024 * 1024),
                "elapsed_ms": elapsed,
            }
        assert records[0]["checksum_sha256"] == records[1]["checksum_sha256"]
        assert records[0]["byte_size"] == records[1]["byte_size"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
