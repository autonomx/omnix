"""Render the desktop app's icons from resources/logo/omnix.png into desktop/brand/out/.

    python desktop/brand/render_icons.py

Writes icon.ico (16-256), icon.png and icon-<size>.png (16-1024) for the windows, the installers and notifications,
and trayTemplate.png / trayTemplate@2x.png: black on transparent, which the macOS menu bar tints for light and dark.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "out"
SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)


def square(image: Image.Image) -> Image.Image:
    side = max(image.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    return canvas


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    logo = square(Image.open(ROOT / "resources" / "logo" / "omnix.png").convert("RGBA"))
    for size in SIZES:
        logo.resize((size, size), Image.LANCZOS).save(OUT / f"icon-{size}.png")
    logo.resize((512, 512), Image.LANCZOS).save(OUT / "icon.png")
    logo.resize((256, 256), Image.LANCZOS).save(OUT / "icon.ico", sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])
    alpha = logo.getchannel("A")
    for name, size in (("trayTemplate.png", 22), ("trayTemplate@2x.png", 44)):
        mask = alpha.resize((size, size), Image.LANCZOS)
        template = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        template.putalpha(mask)
        template.save(OUT / name)
    print(f"icons written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
