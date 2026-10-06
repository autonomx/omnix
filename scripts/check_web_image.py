"""Check a built web image's ingress behaviour in a running container (WP-11.3).

Runs the image with stand-in upstream hosts (no gateway is needed) and checks
`nginx -t`, the SPA security headers and caching, the login body limit and the
login rate limit. With --browser, Chromium also loads the app and must report
no Content-Security-Policy violation.

    python scripts/check_web_image.py omnix-web:ci [--browser]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_gateway_ingress import SPA_CONTENT_SECURITY_POLICY  # noqa: E402

HOSTS = ("--add-host", "gateway-worker:127.0.0.1", "--add-host", "api:127.0.0.1")


def _run(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def check(image: str, *, browser: bool) -> list[str]:
    problems: list[str] = []
    syntax = subprocess.run(["docker", "run", "--rm", *HOSTS, image, "nginx", "-t"], capture_output=True, text=True)
    if syntax.returncode != 0:
        return [f"nginx -t failed: {syntax.stderr.strip()[-500:]}"]
    name = f"omnix-web-check-{uuid.uuid4().hex[:8]}"
    _run("docker", "run", "-d", "--rm", "--name", name, "--read-only", "--tmpfs", "/tmp", *HOSTS,
         "-p", "127.0.0.1::8080", image)
    try:
        port = _run("docker", "port", name, "8080/tcp").strip().splitlines()[0].rsplit(":", 1)[1]
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 30
        while True:
            try:
                index = httpx.get(f"{base}/", timeout=5)
                break
            except httpx.TransportError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        expected = {
            "content-security-policy": SPA_CONTENT_SECURITY_POLICY,
            "x-content-type-options": "nosniff",
            "x-frame-options": "DENY",
            "referrer-policy": "no-referrer",
            "cache-control": "no-cache",
        }
        for header, value in expected.items():
            if index.headers.get(header) != value:
                problems.append(f"/: {header} is {index.headers.get(header)!r}")
        if "server" in index.headers and re.search(r"\d", index.headers["server"]):
            problems.append(f"/: server header reveals a version: {index.headers['server']}")
        asset = re.search(r'src="(/assets/[^"]+\.js)"', index.text)
        if asset is None:
            problems.append("/: no bundled script in index.html")
        else:
            cached = httpx.get(f"{base}{asset.group(1)}", timeout=5)
            if "immutable" not in cached.headers.get("cache-control", ""):
                problems.append(f"{asset.group(1)}: not cached as immutable")
            if cached.headers.get("content-security-policy") != SPA_CONTENT_SECURITY_POLICY:
                problems.append(f"{asset.group(1)}: missing the content security policy")
        oversized = httpx.post(f"{base}/api/auth/local/login", content=b"x" * (2 * 1024 * 1024), timeout=10)
        if oversized.status_code != 413:
            problems.append(f"2 MB login body answered {oversized.status_code}, expected 413")
        statuses = [httpx.post(f"{base}/api/auth/local/login", json={}, timeout=5).status_code for _ in range(15)]
        if 429 not in statuses:
            problems.append(f"15 rapid logins were never rate limited: {statuses}")
        if browser:
            problems.extend(_browser_violations(base))
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    return problems


def _browser_violations(base: str) -> list[str]:
    from playwright.sync_api import sync_playwright

    violations: list[str] = []
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        page = chromium.new_page()
        page.on("console", lambda message: violations.append(message.text)
                if "Content Security Policy" in message.text else None)
        page.goto(f"{base}/", wait_until="networkidle")
        page.wait_for_timeout(1500)
        chromium.close()
    return [f"CSP violation: {text[:300]}" for text in violations]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image")
    parser.add_argument("--browser", action="store_true", help="also load the app in Chromium")
    args = parser.parse_args()
    problems = check(args.image, browser=args.browser)
    for problem in problems:
        print(f"FAIL {problem}")
    if not problems:
        print(f"{args.image}: ingress checks passed")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
