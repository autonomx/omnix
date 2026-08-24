from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import re
import subprocess
from pathlib import Path

SOURCE_COMMIT = "5529cb1bc223aa6f018630792aa5ce5e16c5071f"
SOURCE_PATH = ".github/workflows/trading-v3-recovery-precision-search.yml"
EXPECTED_SHA256 = "5c98837cc96ad7c692d45b0bafff6a025f04f52599985cc6e85af734f6917607"
EXPECTED_REMOVED_INDEX = 3382


def _git_show() -> str:
    ref = f"{SOURCE_COMMIT}:{SOURCE_PATH}"
    try:
        return subprocess.check_output(["git", "show", ref], text=True)
    except subprocess.CalledProcessError:
        subprocess.run(
            ["git", "fetch", "--no-tags", "--depth=1", "origin", SOURCE_COMMIT],
            check=True,
        )
        return subprocess.check_output(["git", "show", ref], text=True)


def recover(output: Path) -> tuple[int, str]:
    historical = _git_show()
    match = re.search(r'payload = "([A-Za-z0-9+/=]+)"', historical)
    if match is None:
        raise SystemExit("historical embedded selector payload not found")
    payload = match.group(1)

    for removed_index in range(len(payload)):
        candidate = payload[:removed_index] + payload[removed_index + 1 :]
        try:
            source = gzip.decompress(base64.b64decode(candidate, validate=True))
        except Exception:
            continue
        digest = hashlib.sha256(source).hexdigest()
        if digest != EXPECTED_SHA256:
            continue
        if removed_index != EXPECTED_REMOVED_INDEX:
            raise SystemExit(f"unexpected corruption index: {removed_index}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(source)
        return removed_index, digest

    raise SystemExit("exact selector source fingerprint not recoverable")


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover the immutable reviewed V3 selector source.")
    parser.add_argument("--output", default="/tmp/recovery_selector.py")
    args = parser.parse_args()
    index, digest = recover(Path(args.output))
    print(f"Recovered exact selector source sha256={digest}; removed_index={index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
