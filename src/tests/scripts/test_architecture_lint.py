"""Synthetic architecture lint and migration immutability regressions."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import architecture_lint as lint  # noqa: E402

CONFIG = lint.load_layers(SCRIPTS.parent / "resources/architecture/layers.toml")
APP = "src/app/"
OLD = lint.MIGRATIONS + "0001_platform.sql"
NEW = lint.MIGRATIONS + "0002_more.sql"


def report(sources):
    return lint.measure(sources, CONFIG, {})


CASES = [
    ("AL001", {APP + "jobs/a.py": "def work():\n    from app.chat import service"}),
    ("AL002", {APP + "chat/a.py": "import app.jobs.a", APP + "jobs/a.py": "import app.chat.a"}),
    ("AL003", {APP + "chat/a.py": "import external as other\nother.method = replacement"}),
    ("AL003", {APP + "chat/a.py": "from external import Foreign\nsetattr(Foreign, 'method', replacement)"}),
    ("AL003", {APP + "chat/a.py": "from external import Foreign\ndel Foreign.method"}),
    ("AL003", {APP + "chat/a.py": "import sys\nsys.modules['external'] = replacement"}),
    ("AL003", {APP + "chat/a.py": "import sys\nsys.modules['external'].method = replacement"}),
    ("AL003", {APP + "chat/a.py": "import sys\nsys.meta_path.append(finder)"}),
    ("AL003", {"src/sitecustomize.py": "import builtins\nbuiltins.open = replacement"}),
    ("AL004", {APP + "chat/a.py": "import external\ndef _install_hook():\n    external.method = replacement"}),
    ("AL005", {APP + "chat/a.py": "@router.post('/api/test')\nasync def handle():\n    return {}"}),
    ("AL006", {APP + "chat/a.py": "sql = 'SELECT * FROM omnix_jobs'"}),
    ("AL007", {APP + "chat/a.py": "from os import getenv as read\nread('SECRET')"}),
    ("AL008", {APP + "chat/a.py": "print('debug')"}),
    ("AL009", {APP + "chat/a.py": "try:\n    work()\nexcept Exception:\n    pass"}),
    ("AL010", {APP + "chat/a.py": "from external import *"}),
    ("AL011", {APP + "chat/a.py": "from app.persistence.blob_store import LocalBlobStore as Store\nStore()"}),
    ("AL012", {APP + "chat/a.py": "local_tenant_context()"}),
    ("AL013", {APP + "rpg/core/a.py": "from random import Random as RNG\nRNG()"}),
    ("AL014", {NEW: "SELECT 1", lint.MIGRATIONS + "0002_duplicate.sql": "SELECT 2"}),
]


@pytest.mark.parametrize("rule,sources", CASES, ids=[case[0] for case in CASES])
def test_each_rule_and_patch_form(rule, sources):
    current = report(sources)
    assert not current["errors"]
    assert rule in {entry["rule"] for entry in current["violations"]}


def test_all_fourteen_rules_are_exercised():
    assert {rule for rule, _ in CASES} == set(lint.RULES)


PROVENANCE_CASES = [
    ("module_alias", "import external\nmodule_alias = external\nmodule_alias.method = replacement", 1),
    ("alias_chain", "import external\na = external\nb = a\nb.method = replacement", 1),
    ("importlib", "import importlib\nm = importlib.import_module('external')\nm.method = replacement", 1),
    ("importlib_alias", "from importlib import import_module as load\nm = load('external')\nm.method = replacement", 1),
    ("builtin_import", "m = __import__('external')\nm.method = replacement", 1),
    ("getattr_class", "import external\ntarget = getattr(external, 'Foreign')\ntarget.method = replacement", 1),
    ("foreign_class_type", "from external import Foreign\ndef patch(target: type[Foreign]):\n    target.method = replacement", 1),
    ("typing_type", "from typing import Type as Class\nfrom external import Foreign\ndef patch(target: Class[Foreign]):\n    target.method = replacement", 1),
    ("forward_type", "from external import Foreign\ndef patch(target: 'type[Foreign]'):\n    target.method = replacement", 1),
    ("annotated_type", "from typing import Annotated\nfrom external import Foreign\ndef patch(target: Annotated[type[Foreign], 'metadata']):\n    target.method = replacement", 1),
    ("union_type", "from external import Foreign\ndef patch(target: type[Foreign] | None):\n    target.method = replacement", 1),
    ("type_alias", "from external import Foreign\nClass = type[Foreign]\ndef patch(target: Class):\n    target.method = replacement", 1),
    ("module_parameter", "from types import ModuleType\ndef patch(target: ModuleType):\n    target.method = replacement", 1),
    ("class_annotation", "from external import Foreign\ntarget: type[Foreign]\ntarget.method = replacement", 1),
    ("foreign_default", "from external import Foreign\ndef patch(target=Foreign):\n    target.method = replacement", 1),
    ("local_class_alias", "class Local:\n    pass\ntarget_cls = Local\ntarget_cls.method = replacement", 0),
    ("local_class_type", "class Local:\n    pass\ndef patch(target: type[Local]):\n    target.method = replacement", 0),
    ("local_union", "class Local:\n    pass\ndef patch(cls: type[Local] | None):\n    cls.method = replacement", 0),
    ("dynamic_local_class", "target_cls = type('Local', (), {})\ntarget_cls.method = replacement", 0),
    ("parameter_shadow", "import external\ndef change(external):\n    external.method = replacement", 0),
    ("local_shadow", "import external\ndef change():\n    external.method = replacement\n    external = object()", 0),
    ("local_reassignment", "import external\nexternal = object()\nexternal.method = replacement", 0),
    ("known_foreign_instance", "from external import Foreign\ninstance = Foreign()\ninstance.method = replacement", 0),
    ("typed_foreign_instance", "from external import Foreign\ndef patch(instance: Foreign):\n    instance.method = replacement", 0),
    ("foreign_instance_class", "from external import Foreign\ninstance = Foreign()\ninstance.__class__.method = replacement", 1),
    ("own_classmethod", "class Local:\n    @classmethod\n    def change(cls):\n        cls.method = replacement", 0),
    ("own_instance_type", "class Local:\n    pass\ninstance = Local()\ntype(instance).method = replacement", 0),
    ("local_subclass", "from external import Foreign\nclass Local(Foreign):\n    pass\nLocal.method = replacement", 0),
    ("own_class_member_foreign", "from external import Foreign\nclass Local:\n    Member = Foreign\n    def patch(self):\n        self.Member.method = replacement", 1),
    ("nested_own_class", "class Local:\n    class Member:\n        pass\ntarget_cls = Local.Member\ntarget_cls.method = replacement", 0),
    ("closure", "import external\ndef outer():\n    target = external\n    def inner():\n        target.method = replacement", 1),
    ("global_not_closure", "import external\ndef outer():\n    external = object()\n    def inner():\n        global external\n        external.method = replacement", 1),
    ("nonlocal_alias", "import external\ndef outer():\n    target = external\n    def inner():\n        nonlocal target\n        target.method = replacement", 1),
    ("branch_alias", "import external\nif condition:\n    target = external\nelse:\n    target = object()\ntarget.method = replacement", 1),
    ("loop_alias", "import external\nfor target in [external]:\n    target.method = replacement", 1),
    ("loop_zero_iteration", "import external\nfor external in items:\n    pass\nexternal.method = replacement", 1),
    ("comprehension_shadow", "import external\nvalues = [setattr(external, 'method', replacement) for external in items]", 0),
    ("comprehension_alias", "import external\nvalues = [setattr(target, 'method', replacement) for target in [external]]", 1),
    ("registry_alias", "import sys\nmodules = sys.modules\nmodules['external'] = replacement", 1),
    ("registry_get", "import sys\nm = sys.modules.get('external')\nm.method = replacement", 1),
    ("registry_value_alias", "import sys\nm = sys.modules['external']\nm.method = replacement", 1),
    ("meta_path_alias", "import sys\nhooks = sys.meta_path\nhooks.append(finder)", 1),
    ("builtin_setter_alias", "assign = setattr\nimport external\nassign(external, 'method', replacement)", 1),
    ("shadowed_setter", "import external\ndef patch(setattr):\n    setattr(external, 'method', replacement)", 0),
    ("local_index_read", "import external\nlocal[external.index] = replacement", 0),
    ("implicit_loop_store", "import external\nfor external.method in items:\n    pass", 1),
    ("implicit_with_store", "import external\nwith manager as external.method:\n    pass", 1),
    ("class_factory_hint", "from external import load_class\ntarget_cls = load_class()\ntarget_cls.method = replacement", 1),
    ("function_class_name_collision", "from external import Foreign\nclass Factory:\n    pass\ndef Factory():\n    def nested(target: type[Foreign]):\n        target.method = replacement", 1),
    ("getattr_owned_member", "from external import Foreign\nclass Local:\n    Member = Foreign\ngetattr(Local, 'Member').method = replacement", 1),
    ("class_redefinition", "from external import Foreign\nclass Local:\n    Member = Foreign\nold = Local\nclass Local:\n    Member = object()\nold.Member.method = replacement", 1),
    ("own_metaclass", "class Meta(type):\n    pass\nclass Local(metaclass=Meta):\n    pass\ntype(Local).method = replacement", 0),
    ("match_shadow", "import external\nmatch incoming:\n    case external:\n        external.method = replacement", 0),
    ("match_foreign_alias", "import external\nmatch external:\n    case target:\n        target.method = replacement", 1),
    ("function_match_shadow", "import external\ndef change():\n    external.method = replacement\n    match incoming:\n        case external:\n            pass", 0),
    ("comprehension_walrus", "import external\nresult = [(alias := external) for item in [1]]\nalias.method = replacement", 1),
    ("overridable_default", "def patch(target_cls=None):\n    target_cls.method = replacement", 1),
    ("inherited_own_metaclass", "class Meta(type):\n    pass\nclass Base(metaclass=Meta):\n    pass\nclass Local(Base):\n    pass\ntype(Local).method = replacement", 0),
    ("typed_own_factory", "class Local:\n    pass\ndef factory() -> type[Local]:\n    return Local\ntarget_cls = factory()\ntarget_cls.method = replacement", 0),
    ("typed_foreign_factory", "from external import Foreign\ndef factory() -> type[Foreign]:\n    return Foreign\ntarget = factory()\ntarget.method = replacement", 1),
]


@pytest.mark.parametrize("name,source,count", PROVENANCE_CASES, ids=[case[0] for case in PROVENANCE_CASES])
def test_foreign_write_provenance(name, source, count):
    current = report({APP + "chat/a.py": source})
    assert current["errors"] == [], name
    assert sum(entry["count"] for entry in current["violations"] if entry["rule"] == "AL003") == count


def test_alias_fingerprints_use_actual_qualified_target_with_scoped_imports():
    source = "import first as target\ntarget.method = replacement\ndef patch():\n    import second as target\n    target.method = replacement"
    current = report({APP + "chat/a.py": source})
    assert {entry["fingerprint"] for entry in current["violations"] if entry["rule"] == "AL003"} == {
        "<module>:first.method", "patch:second.method",
    }


def test_install_hook_cannot_hide_its_patch_behind_a_module_alias():
    current = report({APP + "chat/a.py": "import external\ndef install_hooks():\n    target = external\n    target.method = replacement"})
    assert {entry["rule"] for entry in current["violations"]} >= {"AL003", "AL004"}


def test_owned_class_metaclass_fingerprint_never_contains_definition_line():
    source = "class Local:\n    pass\ntype(Local).method = replacement"
    before = report({APP + "chat/a.py": source})
    moved = report({APP + "chat/a.py": "\n\n" + source})
    assert lint.compare(moved, before) == []
    assert {entry["fingerprint"] for entry in before["violations"]} == {"<module>:builtins.type.method"}


def test_compliant_owners_local_classes_and_tests_are_allowed():
    sources = {
        APP + "config/a.py": "import os\nos.getenv('X')",
        APP + "persistence/job_repository.py": "sql = 'SELECT * FROM omnix_jobs'",
        APP + "persistence/blob_store.py": "LocalBlobStore()",
        APP + "production.py": "bootstrap_local_tenant()",
        APP + "chat/a.py": "class Local:\n    pass\nLocal.method = replacement\n@router.post('/api/a')\nasync def route():\n    await work()",
        APP + "rpg/core/a.py": "import random\nrandom.Random(42)",
        "src/tests/test_example.py": "import builtins\nbuiltins.open = fake\nprint('test')",
    }
    assert report(sources)["violations"] == []


def test_cycles_with_three_packages_and_different_modules_are_detected():
    sources = {APP + "chat/a.py": "import app.jobs.b", APP + "jobs/a.py": "import app.providers.b",
               APP + "providers/a.py": "import app.chat.b", APP + "chat/b.py": "",
               APP + "jobs/b.py": "", APP + "providers/b.py": ""}
    cycles = [entry for entry in report(sources)["violations"] if entry["rule"] == "AL002"]
    assert len(cycles) == 3
    sources[APP + "providers/a.py"] = "def lazy():\n    import app.chat.b"
    assert not [entry for entry in report(sources)["violations"] if entry["rule"] == "AL002"]


def test_production_cycle_graph_excludes_test_imports():
    sources = {APP + "jobs/a.py": "import app.chat.a", APP + "chat/a.py": "",
               APP + "chat/test_old.py": "import app.jobs.a"}
    assert not [entry for entry in report(sources)["violations"] if entry["rule"] == "AL002"]


def test_new_cycle_edge_cannot_hide_in_an_existing_component():
    sources = {APP + "chat/a.py": "import app.jobs.a", APP + "jobs/a.py": "import app.chat.a\nimport app.providers.a",
               APP + "providers/a.py": "import app.chat.a"}
    previous = report(sources)
    sources[APP + "chat/a.py"] += "\nimport app.providers.a"
    assert any("AL002" in error for error in lint.compare(report(sources), previous))


def test_baseline_ignores_line_moves_but_detects_duplicate_violations():
    path = APP + "chat/a.py"
    previous = report({path: "import external\nexternal.method = replacement"})
    moved = report({path: "\n\nimport external\nexternal.method = replacement"})
    assert lint.compare(moved, previous) == []
    duplicate = report({path: "import external\nexternal.method = replacement\nexternal.method = second"})
    assert any("AL003" in error for error in lint.compare(duplicate, previous))
    assert lint.compare(previous, duplicate)
    assert lint.compare(previous, duplicate, shrinking=True) == []


def test_fixes_require_shrinking_and_cannot_grow_on_update():
    previous = report({APP + "chat/a.py": "print('old')"})
    fixed = report({APP + "chat/a.py": ""})
    assert any("stale" in error for error in lint.compare(fixed, previous))
    assert lint.compare(fixed, previous, shrinking=True) == []
    assert lint.compare(previous, fixed, shrinking=True)


def test_policy_and_rule_changes_cannot_silently_weaken_the_baseline():
    current = report({})
    for field, value in (("policy_digest", "different"), ("rules", []), ("scope", "tests_only")):
        changed = deepcopy(current)
        changed[field] = value
        assert lint.compare(current, changed, shrinking=True)


@pytest.mark.parametrize("entry", [
    {"rule": "AL999", "path": "a", "fingerprint": "b", "count": 1},
    {"rule": "AL001", "path": "a", "fingerprint": "b", "count": True},
    {"rule": "AL001", "path": "a", "fingerprint": "b", "count": 0},
])
def test_invalid_baseline_entries_fail_closed(entry):
    with pytest.raises(lint.AnalysisError):
        lint.entry_counts({"violations": [entry]})


@pytest.mark.parametrize("registry", [
    {}, {"schema_version": 1, "checksums": {}},
    {"schema_version": 1, "checksums": {OLD: "not-a-checksum"}},
    {"schema_version": 1, "checksums": {lint.MIGRATIONS + "../escape.sql": "0" * 64}},
])
def test_invalid_checksum_registry_fails_closed(registry):
    with pytest.raises(lint.AnalysisError):
        lint.registry_checksums(registry)


def test_migrations_append_without_editing_or_renumbering_historical_duplicates():
    second_old = lint.MIGRATIONS + "0001_legacy.sql"
    protected = {OLD: lint.checksum("SELECT 1\n"), second_old: lint.checksum("SELECT 2\n")}
    current = {OLD: "SELECT 1\r\n", second_old: "SELECT 2\n", NEW: "SELECT 3\n"}
    assert lint.migration_violations(current, protected) == []
    current[OLD] = "SELECT 4\n"
    assert lint.migration_violations(current, protected)[0].fingerprint == "existing_migration_changed_or_removed"
    del current[OLD]
    assert any(item.path == OLD for item in lint.migration_violations(current, protected))


def test_migrations_reject_duplicate_renamed_deleted_and_out_of_order_files():
    protected = {NEW: lint.checksum("SELECT 1")}
    sources = {NEW: "SELECT 1", OLD: "SELECT 2", lint.MIGRATIONS + "2_duplicate.sql": "SELECT 3"}
    violations = lint.migration_violations(sources, protected)
    assert any(item.fingerprint.startswith("new_duplicate") for item in violations)
    assert any(item.fingerprint.startswith("new_migration_before") for item in violations)


def make_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "--quiet", str(root)], check=True, capture_output=True)
    config_path = root / "resources/architecture/layers.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text((SCRIPTS.parent / "resources/architecture/layers.toml").read_text(encoding="utf-8"), encoding="utf-8")
    old = root / OLD
    old.parent.mkdir(parents=True)
    old.write_text("SELECT 1\n", encoding="utf-8")
    (root / lint.REGISTRY).write_text(json.dumps({"schema_version": 1, "checksums": {OLD: lint.checksum("SELECT 1\n")}}), encoding="utf-8")
    source = root / APP / "chat/a.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('old')", encoding="utf-8")
    subprocess.run(["git", "add", "resources", "src"], cwd=root, check=True, capture_output=True)
    return root, source


def run_lint(root, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / "architecture_lint.py"), "--root", str(root), *args],
                          capture_output=True, encoding="utf-8")


def test_cli_initializes_then_refuses_growth_and_requires_shrinking(tmp_path):
    root, source = make_repo(tmp_path)
    assert run_lint(root, "--update-baseline").returncode == 0
    assert run_lint(root, "--check").returncode == 0
    baseline = root / "resources/architecture/lint-baseline.json"
    saved = baseline.read_bytes()
    source.write_text("print('old')\nprint('new')", encoding="utf-8")
    assert run_lint(root, "--update-baseline").returncode == 1
    assert baseline.read_bytes() == saved
    source.write_text("", encoding="utf-8")
    assert run_lint(root, "--check").returncode == 1
    assert run_lint(root, "--update-baseline").returncode == 0
    assert run_lint(root, "--check").returncode == 0


def test_cli_registry_fallback_protects_migrations_even_on_initialization(tmp_path):
    root, _ = make_repo(tmp_path)
    (root / OLD).write_text("SELECT 2", encoding="utf-8")
    result = run_lint(root, "--update-baseline")
    assert result.returncode == 1
    assert "AL014" in result.stderr
    assert not (root / "resources/architecture/lint-baseline.json").exists()


def test_cli_cannot_overwrite_baseline_via_output_or_certify_invalid_python(tmp_path):
    root, source = make_repo(tmp_path)
    assert run_lint(root, "--update-baseline").returncode == 0
    baseline = root / "resources/architecture/lint-baseline.json"
    saved = baseline.read_bytes()
    assert run_lint(root, "--check", "--output", str(baseline)).returncode == 2
    assert baseline.read_bytes() == saved
    source.write_text("return 42", encoding="utf-8")
    assert run_lint(root, "--update-baseline").returncode == 1
    assert baseline.read_bytes() == saved


def test_reference_migrations_uses_immutable_resolved_commit(tmp_path):
    root, _ = make_repo(tmp_path)
    subprocess.run(["git", "-c", "user.name=Architecture Tests", "-c", "user.email=architecture@example.invalid",
                    "commit", "--quiet", "-m", "synthetic migration reference"], cwd=root, check=True, capture_output=True)
    assert lint.reference_migrations(root, "HEAD") == {OLD: lint.checksum("SELECT 1\n")}
    assert lint.reference_migrations(root, "origin/main") is None
