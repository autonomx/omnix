"""Retire an Omnix module (ADR-0016, PA-4.3).

    python scripts/retire_module.py <module-id> [--drain-timeout 600] [--cancel-grace 30]
                                    [--database-only | --files-only] [--no-generate]
    python scripts/retire_module.py <module-id> --reactivate

Refuses first if another catalog module or web feature depends on, uses or
imports the module. Then, in the database (``OMNIX_DATABASE_URL``), across
every workspace:

1. sets the module ``draining`` until a deadline and waits for its running jobs
   and its outbox consumers' deliveries to finish;
2. cancels what is left, with reason ``module_retired``: waiting jobs are
   canceled, running ones asked to stop and failed after a grace period, its
   consumers' undelivered events dead-lettered and its tools' open approvals
   expired (its scheduled tasks have no durable state; draining stopped them);
3. stops, leaving the module draining, if any of that work is not final;
4. sets it ``retired``.

Then, in the checkout:

5. removes its catalog line and web manifest line, its package, tests and web
   feature, and its conformance baseline entry;
6. moves its ``migrations/`` to ``src/app/persistence/retired/<package>/``
   and writes ``tombstone.py`` there: its id, a settings stub that keeps stored
   values, and its job types, outbox consumers and tools;
7. refreshes the generated contract files (skipped with ``--no-generate``).

A retirement that stops at step 3 leaves the module draining: rerun it once
the remaining work is final, or ``--reactivate`` it. Deleting the module's
data is a separate, owner-approved contract migration in the tombstone folder.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.persistence.authority import PostgresAuthorityError  # noqa: E402
from new_module import CATALOG, WEB, WEB_MANIFESTS, generate  # noqa: E402

APP = ROOT / "src" / "app"
RETIRED = APP / "persistence" / "retired"
CONFORMANCE_BASELINE = ROOT / "resources" / "architecture" / "module-conformance-baseline.json"


class RetirementError(RuntimeError):
    pass


def _log(message: str) -> None:
    print(f"retire_module: {message}", flush=True)


def module_package(module_id: str) -> str:
    """The module's package below ``app``, e.g. ``apps.recipe_probe`` or ``apps.rpg.hermes``."""
    from app.runtime.feature_catalog import FEATURE_CATALOG

    if module_id not in FEATURE_CATALOG:
        raise RetirementError(f"{module_id!r} is not a catalog module")
    return FEATURE_CATALOG[module_id].split(":", 1)[0].removeprefix("app.").removesuffix(".feature")


def unit_name(package: str) -> str:
    """The package without its tier folder (PA-5.3), as tests and retired folders name it: ``rpg_hermes``."""
    tier, _, rest = package.partition(".")
    return (rest if tier in {"platform", "apps", "composition"} and rest else package).replace(".", "_")


def dependents(module_id: str, package: str) -> list[str]:
    """What would break without the module: catalog modules that depend on or use it, other web
    features that list it, and code outside it that imports it."""
    from app.runtime.feature_catalog import FEATURE_CATALOG, load_feature

    found = []
    for other in sorted(set(FEATURE_CATALOG) - {module_id}):
        feature = load_feature(other)
        if module_id in feature.depends_on or module_id in feature.uses:
            found.append(f"catalog module {other} {'depends on' if module_id in feature.depends_on else 'uses'} it")
    for manifest in sorted((WEB / "src" / "features").glob("*/module.ts")):
        if manifest.parent.name != module_id and re.search(rf"backendModules:\s*\[[^\]]*'{re.escape(module_id)}'",
                                                           manifest.read_text(encoding="utf-8")):
            found.append(f"web feature {manifest.parent.name} lists it in backendModules")
    own = (APP.joinpath(*package.split(".")), ROOT / "src" / "tests" / unit_name(package))
    importer = re.compile(rf"^\s*(?:from|import)\s+app\.{re.escape(package)}\b", re.M)
    for path in sorted([*APP.glob("**/*.py"), *(ROOT / "src" / "tests").glob("**/*.py")]):
        if not any(path.is_relative_to(folder) for folder in own):
            if importer.search(path.read_text(encoding="utf-8", errors="replace")):
                found.append(f"{path.relative_to(ROOT).as_posix()} imports it")
    return found


def _tools(feature: Any) -> list[Any]:
    from app.capabilities.registry import TOOL_DECLARATIONS

    context = SimpleNamespace(feature_id=feature.id, config=None, runtime=None, capabilities=None, services=None,
                              logger=None, runtime_state=None)
    return [spec.factory(context) for spec in feature.contributions if spec.port is TOOL_DECLARATIONS]


def describe(module_id: str) -> dict[str, Any]:
    """The module's job types, outbox consumers, tools and settings sections, read from its code."""
    import importlib

    from app.runtime.feature_catalog import load_feature

    package = module_package(module_id)
    feature = load_feature(module_id)
    tools = _tools(feature)
    try:
        sections = tuple(getattr(importlib.import_module(f"app.{package}.declarations"), "SETTINGS", ()))
    except ModuleNotFoundError:
        sections = ()
    return {
        "package": package,
        "job_types": tuple(sorted(spec.type for spec in feature.job_handlers)),
        "consumers": tuple(
            (consumer.consumer_name, tuple(sorted(consumer.aggregate_types)), consumer.event_type_pattern)
            for consumer in feature.outbox_consumers
        ),
        "tool_ids": tuple(sorted(tool.tool_id for tool in tools)),
        "capability_ids": tuple(sorted({
            name for tool in tools for capability in tool.capabilities()
            for name in (capability.id, *getattr(capability, "aliases", ()))
        })),
        "settings": sections,
        "scheduled_tasks": len(feature.scheduled_tasks),
    }


def retire_database(module_id: str, described: dict[str, Any], *, drain_timeout: float, cancel_grace: float,
                    poll: float) -> None:
    from app.persistence.database import default_database
    from app.persistence.module_retirement import (
        OutboxSubscription,
        RetirementSubject,
        cancel_remaining,
        fail_unfinished_jobs,
        in_flight_work,
        set_state,
    )

    database = default_database()
    subject = RetirementSubject(
        module_id,
        job_types=described["job_types"],
        subscriptions=tuple(OutboxSubscription(*consumer) for consumer in described["consumers"]),
        capability_ids=described["capability_ids"],
    )
    deadline = datetime.now(timezone.utc) + timedelta(seconds=drain_timeout)
    set_state(database, module_id, "draining", drain_deadline=deadline)
    _log(f"draining until {deadline.isoformat(timespec='seconds')}")
    while not (work := in_flight_work(database, subject)).drained and datetime.now(timezone.utc) < deadline:
        time.sleep(poll)
    _log(f"drained: {work}" if work.drained else f"drain timeout with {work}")
    report = cancel_remaining(database, subject)
    _log(f"canceled {report.canceled_jobs} waiting jobs, asked {report.cancel_requested_jobs} running jobs to stop, "
         f"dead-lettered {report.dead_lettered_deliveries} deliveries, expired {report.expired_approvals} approvals")
    grace_end = time.monotonic() + cancel_grace
    while in_flight_work(database, subject).active_jobs and time.monotonic() < grace_end:
        time.sleep(poll)
    failed = fail_unfinished_jobs(database, subject)
    if failed:
        _log(f"failed {failed} jobs that did not stop")
    # Again, for deliveries a consumer was still processing the first time.
    cancel_remaining(database, subject)
    remaining = in_flight_work(database, subject)
    if not remaining.empty:
        raise RetirementError(f"work is still in flight, the module stays draining: {remaining}")
    set_state(database, module_id, "retired")
    _log("retired in the database")


def _literal(value: Any) -> str:
    """A string or tuple of them as Python source, in the repository's double quotes."""
    if isinstance(value, str):
        return json.dumps(value)
    items = [_literal(item) for item in value]
    return "(" + ", ".join(items) + ("," if len(items) == 1 else "") + ")"


def _settings_stub(module_id: str, sections: tuple[Any, ...]) -> tuple[str, str]:
    """The tombstone's settings models and SETTINGS line: same fields, order and aliases, any stored values kept."""
    if not sections:
        return "", ""
    models, entries = [], []
    for section in sections:
        name = "Retired" + "".join(part.capitalize() for part in re.split(r"[-_]", section.field)) + "Settings"
        models.append(f'\n\nclass {name}(BaseModel):\n    """Stored values of the retired {module_id} section, kept as they are."""\n\n'
                      f'    model_config = ConfigDict(extra="allow")\n')
        alias = f", alias={_literal(section.alias)}" if section.alias else ""
        entries.append(f"SettingsSection({_literal(section.field)}, {name}, order={section.order}{alias})")
    return "".join(models), f"SETTINGS = ({', '.join(entries)},)\n"


def tombstone_source(module_id: str, described: dict[str, Any], retired_on: str) -> str:
    models, settings = _settings_stub(module_id, described["settings"])
    imports = ("from pydantic import BaseModel, ConfigDict\n\nfrom app.persistence.declarations import SettingsSection\n"
               if settings else "")
    consumers = "".join(f"\n    {_literal(consumer)}," for consumer in described["consumers"])
    return f'''"""Tombstone of the retired module {module_id} (PA-4.3), written by scripts/retire_module.py on {retired_on}.

Kernel-only, read by convention: the migrations next to it stay known, its
tables are owned by ``retired:{module_id}``, recovery fails its job types once,
and its settings section keeps stored values. A later settings migration may
drop the section.
"""
from __future__ import annotations
{"" if not imports else chr(10) + imports}
MODULE_ID = {_literal(module_id)}
JOB_TYPES: tuple[str, ...] = {_literal(described["job_types"])}
# (consumer, aggregate types, event type pattern)
OUTBOX_CONSUMERS: tuple[tuple[str, tuple[str, ...], str], ...] = ({consumers}{chr(10) if consumers else ""})
TOOL_IDS: tuple[str, ...] = {_literal(described["tool_ids"])}
CAPABILITY_IDS: tuple[str, ...] = {_literal(described["capability_ids"])}
{models}{chr(10) + chr(10) + settings if settings else ""}'''


def _remove_registration(module_id: str) -> list[Path]:
    text = CATALOG.read_text(encoding="utf-8")
    line = re.compile(rf'^\s*"{re.escape(module_id)}": "[^"]+",\n', re.M)
    if not line.search(text):
        raise RetirementError(f"no catalog line for {module_id}")
    CATALOG.write_text(line.sub("", text, count=1), encoding="utf-8", newline="\n")
    edited = [CATALOG]
    manifests = WEB_MANIFESTS.read_text(encoding="utf-8")
    imported = re.compile(rf"^import \{{ ([\w, ]+) \}} from '\.\./features/{re.escape(module_id)}/module';\n", re.M)
    match = imported.search(manifests)
    if match:
        manifests = imported.sub("", manifests, count=1)
        for name in (name.strip() for name in match[1].split(",")):
            manifests = re.sub(rf"^\s*{re.escape(name)},\n", "", manifests, count=1, flags=re.M)
        WEB_MANIFESTS.write_text(manifests, encoding="utf-8", newline="\n")
        edited.append(WEB_MANIFESTS)
    return edited


def _update_conformance_baseline(module_id: str) -> None:
    baseline = json.loads(CONFORMANCE_BASELINE.read_text(encoding="utf-8"))
    changed = baseline.get("modules", {}).pop(module_id, None) is not None
    gaps = baseline.get("tenant_isolation", {})
    if module_id in gaps:
        gaps[f"retired:{module_id}"] = gaps.pop(module_id)
        changed = True
    if changed:
        CONFORMANCE_BASELINE.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8",
                                        newline="\n")


def retire_files(module_id: str, described: dict[str, Any]) -> dict[str, list[Path]]:
    package = described["package"]
    source = APP.joinpath(*package.split("."))
    folder = RETIRED / unit_name(package)
    if folder.exists():
        raise RetirementError(f"{folder.relative_to(ROOT).as_posix()} already exists")
    edited = _remove_registration(module_id)
    folder.mkdir(parents=True)
    written = [folder / "tombstone.py"]
    if (source / "migrations").is_dir():
        (source / "migrations").rename(folder / "migrations")
        written.append(folder / "migrations")
    written[0].write_text(tombstone_source(module_id, described, datetime.now(timezone.utc).date().isoformat()),
                          encoding="utf-8", newline="\n")
    removed = [path for path in (source, ROOT / "src" / "tests" / unit_name(package),
                                 WEB / "src" / "features" / module_id) if path.is_dir()]
    for path in removed:
        shutil.rmtree(path)
    _update_conformance_baseline(module_id)
    return {"edited": edited, "written": written, "removed": removed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("module_id")
    parser.add_argument("--drain-timeout", type=float, default=600.0, help="seconds to wait for in-flight work")
    parser.add_argument("--cancel-grace", type=float, default=30.0, help="seconds running jobs get to stop")
    parser.add_argument("--poll", type=float, default=2.0, help=argparse.SUPPRESS)
    phase = parser.add_mutually_exclusive_group()
    phase.add_argument("--database-only", action="store_true")
    phase.add_argument("--files-only", action="store_true")
    phase.add_argument("--reactivate", action="store_true", help="set a draining module active again")
    parser.add_argument("--no-generate", action="store_true")
    args = parser.parse_args(argv)
    try:
        package = module_package(args.module_id)
        if args.reactivate:
            from app.persistence.database import default_database
            from app.persistence.module_retirement import reactivate

            try:
                reactivate(default_database(), args.module_id)
            except ValueError as error:
                raise RetirementError(str(error)) from error
            _log(f"{args.module_id} is active again")
            return 0
        blockers = dependents(args.module_id, package)
        if blockers:
            raise RetirementError("refused, the module is still needed:\n  " + "\n  ".join(blockers))
        described = describe(args.module_id)
        if not args.files_only:
            retire_database(args.module_id, described, drain_timeout=args.drain_timeout,
                            cancel_grace=args.cancel_grace, poll=args.poll)
        if not args.database_only:
            result = retire_files(args.module_id, described)
            relative = lambda path: path.relative_to(ROOT).as_posix()  # noqa: E731
            print("hand-edited registration: " + ", ".join(relative(path) for path in result["edited"]))
            print("tombstone: " + ", ".join(relative(path) for path in result["written"]))
            print("removed: " + ", ".join(relative(path) for path in result["removed"]))
            for item in [] if args.no_generate else generate(web=True):
                print(f"skipped: {item}")
    except RetirementError as error:
        print(f"retire_module: {error}", file=sys.stderr)
        return 2
    except PostgresAuthorityError as error:
        print(f"retire_module: the database takes no runtime writes yet; start Omnix against it first ({error})",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
