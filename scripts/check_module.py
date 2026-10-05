"""Check one catalog module end to end (PA-4.4).

    python scripts/check_module.py <module_id> [--skip-web]

Runs, and reports each step:

1. the architecture lint, failing only on new violations in the module's files;
2. module conformance (PA-4.1): no gap beyond the module's baseline entry;
3. mypy on the module's package;
4. ``scripts/test_module.py`` (its test directory and characterization scenarios);
5. for each web feature whose manifest lists the module in ``backendModules``,
   that feature's web tests and the web typecheck.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src" / "apps" / "web"
sys.path.insert(0, str(ROOT / "scripts"))

import module_conformance  # noqa: E402
import test_module  # noqa: E402


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")


def lint_step(package: str) -> tuple[bool, str]:
    prefix = "src/" + package.replace(".", "/") + "/"
    with tempfile.TemporaryDirectory() as directory:
        result = _run([sys.executable, "scripts/architecture_lint.py", "--check", "--output", str(Path(directory) / "lint.json")])
    failures = [line for line in result.stderr.splitlines() if line.startswith("architecture lint: ")]
    own = [line for line in failures if prefix in line]
    others = len(failures) - len(own)
    note = f"; {others} failure(s) elsewhere" if others else ""
    return not own, "\n".join(own) or f"no new violations in {prefix}{note}"


def conformance_step(module_id: str) -> tuple[bool, str]:
    gaps = module_conformance.static_gaps().get(module_id, [])
    allowed = module_conformance.load_baseline()["modules"].get(module_id, [])
    new = [gap for gap in gaps if gap not in allowed]
    fixed = [gap for gap in allowed if gap not in gaps]
    if new:
        return False, "new conformance gaps: " + ", ".join(new)
    if fixed:
        return False, "fixed gaps still in the baseline (delete them): " + ", ".join(fixed)
    return True, "gaps: " + (", ".join(gaps) or "none")


def mypy_step(package: str) -> tuple[bool, str]:
    result = _run([sys.executable, "-m", "mypy", "-p", package])
    return result.returncode == 0, (result.stdout.strip().splitlines() or ["mypy passed"])[-1]


def test_step(module_id: str) -> tuple[bool, str]:
    result = _run([sys.executable, "scripts/test_module.py", module_id, "-p", "no:cacheprovider"])
    lines = result.stdout.strip().splitlines()
    summary = [line for line in lines if " passed" in line or " failed" in line or " error" in line]
    return result.returncode == 0, (summary or lines or ["no output"])[-1].strip("= ")


def web_features(module_id: str) -> list[str]:
    features = []
    for manifest in sorted((WEB / "src" / "features").glob("*/module.ts")):
        lists = re.findall(r"\bbackendModules:\s*\[([^\]]*)\]", manifest.read_text(encoding="utf-8"))
        if any(f"'{module_id}'" in item for item in lists):
            features.append(manifest.parent.name)
    return features


def web_steps(module_id: str) -> list[tuple[str, bool, str]]:
    features = web_features(module_id)
    if not features:
        return [("web", True, "no web feature lists this module")]
    npm = shutil.which("npm") or "npm"
    steps = []
    for feature in features:
        result = _run([npm, "--prefix", "src/apps/web", "run", "test", "--", f"src/features/{feature}"])
        summary = [line.strip() for line in result.stdout.splitlines() if line.strip().startswith("Tests")]
        steps.append((f"web tests ({feature})", result.returncode == 0, summary[-1] if summary else "see npm output"))
    result = _run([npm, "--prefix", "src/apps/web", "run", "typecheck"])
    steps.append(("web typecheck", result.returncode == 0, "passed" if result.returncode == 0 else result.stdout.strip()[-2000:]))
    return steps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("module_id")
    parser.add_argument("--skip-web", action="store_true")
    args = parser.parse_args(argv)
    packages = test_module.catalog()
    if args.module_id not in packages:
        print(f"unknown module {args.module_id!r}; catalog modules: {', '.join(sorted(packages))}", file=sys.stderr)
        return 2
    package = packages[args.module_id]
    steps = [
        ("architecture lint", *lint_step(package)),
        ("conformance", *conformance_step(args.module_id)),
        ("mypy", *mypy_step(package)),
        ("tests", *test_step(args.module_id)),
    ]
    if not args.skip_web:
        steps.extend(web_steps(args.module_id))
    for name, passed, detail in steps:
        print(f"[{'pass' if passed else 'FAIL'}] {name}: {detail}")
    return 0 if all(passed for _, passed, _ in steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
