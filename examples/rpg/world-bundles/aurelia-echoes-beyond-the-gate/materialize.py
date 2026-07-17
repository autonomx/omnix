from __future__ import annotations

import argparse
import base64
import hashlib
import zlib
from pathlib import Path

BUNDLE_FILENAME = "aurelia-echoes-beyond-the-gate.omnix-world.zip"
BUNDLE_SHA256 = "9582c2ee7aecfb1d0890210bcd198baedfe4d1ef4ddfbadd6b5086a35f6eb944"


def materialize_bundle(source_dir: Path, output: Path | None = None) -> Path:
    parts_dir = source_dir / "bundle-parts"
    parts = sorted(parts_dir.glob("*.b64"))
    if not parts:
        raise FileNotFoundError(f"No bundle parts found in {parts_dir}")
    encoded = "".join(part.read_text(encoding="ascii").strip() for part in parts)
    content = zlib.decompress(base64.b64decode(encoded, validate=True))
    digest = hashlib.sha256(content).hexdigest()
    if digest != BUNDLE_SHA256:
        raise ValueError(f"Aurelia bundle checksum mismatch: {digest}")
    destination = output or source_dir.parent / BUNDLE_FILENAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize the Aurelia Omnix world bundle")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    source_dir = Path(__file__).resolve().parent
    path = materialize_bundle(source_dir, args.output)
    print(path)


if __name__ == "__main__":
    main()
