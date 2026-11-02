"""The play screen at 360, 768 and 1,440 px wide, in light and dark (RQ-7.5), and how two sets differ.

    python scripts/rpg_play_screenshots.py capture --session <id> --out <dir>
    python scripts/rpg_play_screenshots.py compare <dir-before> <dir-after>

``capture`` opens the campaign on a running web app (``--web``, default http://127.0.0.1:5180), leaving it as it is (no
resume after time away), and writes one
full-page image per width and appearance (``play-<width>-<appearance>.png``), animations off, and a
``manifest.json`` of their sizes and digests. ``compare`` reports, per image, the share of pixels that differ (and
writes a ``diff-*.png`` beside the second set where any do; ``--report`` keeps the results as JSON): a restyling that
should look the same is checked with it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

WIDTHS = {360: 740, 768: 1024, 1440: 900}
APPEARANCES = ("light", "dark")


def capture(args: argparse.Namespace) -> int:
    from playwright.sync_api import sync_playwright

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    shots = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chrome or None)
        for width, height in WIDTHS.items():
            for appearance in APPEARANCES:
                context = browser.new_context(viewport={"width": width, "height": height}, reduced_motion="reduce")
                context.add_init_script(
                    "(() => { try {"
                    f" localStorage.setItem('omnix.appearance.mode', '{appearance}');"
                    f" localStorage.setItem('omnix:rpg:selected-session-id', {json.dumps(args.session)});"
                    " } catch (error) {} })();")
                page = context.new_page()
                # Opening a campaign idle for ten minutes resumes it (the world moves on): a picture must not.
                page.route("**/api/rpg/sessions/*/resume", lambda route: route.abort())
                page.goto(f"{args.web}/rpg", wait_until="networkidle")
                page.locator("#rpg-story-scene-title").wait_for(timeout=30_000)
                page.wait_for_timeout(1_500)  # fonts and late images settle
                path = out / f"play-{width}-{appearance}.png"
                image = page.screenshot(path=str(path), full_page=True, animations="disabled", caret="hide")
                page_height = page.evaluate("document.documentElement.scrollHeight")
                shots.append({"file": path.name, "width": width, "viewport_height": height, "page_height": page_height,
                              "appearance": appearance, "sha256": hashlib.sha256(image).hexdigest()})
                print(path)
                context.close()
        browser.close()
    manifest = {"session": args.session, "web": args.web, "shots": shots}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


def compare(args: argparse.Namespace) -> int:
    from PIL import Image, ImageChops

    before, after = Path(args.before), Path(args.after)
    worst = 0.0
    results = []
    for left in sorted(before.glob("play-*.png")):
        right = after / left.name
        if not right.exists():
            print(f"{left.name}: missing from {after}")
            results.append({"file": left.name, "missing": True})
            worst = 1.0
            continue
        a, b = Image.open(left).convert("RGB"), Image.open(right).convert("RGB")
        if a.size != b.size:
            print(f"{left.name}: size {a.size} -> {b.size}")
            results.append({"file": left.name, "size_before": list(a.size), "size_after": list(b.size)})
            worst = 1.0
            continue
        channels = [channel.point(lambda value: 255 if value > 24 else 0) for channel in ImageChops.difference(a, b).split()]
        mask = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])  # any channel off by > 24
        changed = mask.histogram()[255]
        share = changed / (a.size[0] * a.size[1])
        worst = max(worst, share)
        print(f"{left.name}: {share:.4%} of pixels differ")
        results.append({"file": left.name, "size": list(a.size), "share_differing": round(share, 6)})
        if changed:
            mask.save(after / f"diff-{left.name}")
    if args.report:
        report = {"tolerance": args.tolerance, "worst": round(worst, 6), "pass": worst <= args.tolerance, "images": results}
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if worst <= args.tolerance else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    shoot = commands.add_parser("capture")
    shoot.add_argument("--session", required=True)
    shoot.add_argument("--out", required=True)
    shoot.add_argument("--web", default="http://127.0.0.1:5180")
    shoot.add_argument("--chrome", default="", help="a Chromium executable, when Playwright's own build is older")
    check = commands.add_parser("compare")
    check.add_argument("before")
    check.add_argument("after")
    check.add_argument("--tolerance", type=float, default=0.001, help="the largest share of differing pixels allowed")
    check.add_argument("--report", default="", help="a JSON file for the results")
    args = parser.parse_args(argv)
    return capture(args) if args.command == "capture" else compare(args)


if __name__ == "__main__":
    sys.exit(main())
