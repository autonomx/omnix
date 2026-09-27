"""Synthetic scorecard detectors; no application imports or provider execution."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("omnix_metrics_tests_target", SCRIPTS / "architecture_metrics.py")
metrics = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(metrics)
config = metrics.load_layers(SCRIPTS.parent / "resources/architecture/layers.toml")
WEB = "src/apps/web/src/"
APP = "src/app/"


def observed(sources, *, openapi=None):
    report = {
        "schema_version": 1, "environment": "disposable",
        "source_digest": metrics.source_digest(sources),
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {key: 0 for key in metrics.RUNTIME_METRICS},
    }
    return metrics.measure(sources, config, openapi=openapi or {"paths": {}}, runtime_report=report)


CASES = [
    ("package_cycles", {APP + "jobs/a.py": "import app.chat.b", APP + "chat/b.py": "import app.jobs.a"}, 1),
    ("layer_violations", {APP + "jobs/a.py": "def work():\n    import app.chat.b", APP + "chat/b.py": ""}, 1),
    ("foreign_attribute_assignments", {APP + "gateway/a.py": "import another\nanother.method = replacement"}, 1),
    ("install_hook_functions", {APP + "gateway/a.py": "import another\ndef install_hook():\n    another.method = replacement"}, 1),
    ("fastapi_init_patchers", {APP + "gateway/a.py": "from fastapi import FastAPI as App\nApp.__init__ = wrapper\nApp.__init__ = second"}, 1),
    ("async_handlers_without_await", {APP + "gateway/a.py": "@app.get('/api/a')\nasync def route():\n    return {}"}, 1),
    ("schema_excluded_routes", {APP + "gateway/a.py": "@app.get('/api/a', include_in_schema=False)\ndef route():\n    return {}"}, 1),
    ("untyped_body_routes", {APP + "gateway/a.py": "@app.post('/api/a')\ndef route(body: dict[str, int]):\n    return body"}, 1),
    ("routes_without_permission", {APP + "gateway/a.py": "@app.get('/api/a')\ndef route():\n    return {}"}, 1),
    ("bootstrap_calls_outside_startup", {APP + "chat/a.py": "from app.persistence.identity_service import bootstrap_local_tenant as bootstrap\nbootstrap()"}, 1),
    ("env_reads_outside_config", {APP + "chat/a.py": "import os\nvalue = os.environ['X']\nos.environ['Y'] = 'write-only'"}, 1),
    ("print_calls", {APP + "chat/a.py": "print('debug')"}, 1),
    ("silent_broad_excepts", {APP + "chat/a.py": "try:\n    call()\nexcept Exception:\n    pass"}, 1),
    ("star_imports", {APP + "chat/a.py": "from another import *"}, 1),
    ("platform_table_sql_outside_owner", {APP + "chat/a.py": "connection.execute('SELECT id FROM omnix_jobs WHERE id = %s')"}, 1),
    ("direct_requests_calls", {APP + "chat/a.py": "import requests as http\nhttp.post('/api/a')"}, 1),
    ("local_blob_store_constructions", {APP + "chat/a.py": "from app.persistence.blob_store import LocalBlobStore as Store\nStore()"}, 1),
    ("absolute_storage_path_reads", {APP + "chat/a.py": "a.storage_path\nb.storage_path"}, 1),
    ("unbounded_fetchall", {APP + "persistence/custom_repository.py": "connection.execute('SELECT id FROM things').fetchall()"}, 1),
    ("capped_500_queries", {APP + "persistence/custom_repository.py": "connection.execute('SELECT id FROM things LIMIT 500').fetchall()"}, 1),
    ("rpg_nondeterminism", {APP + "rpg/core/a.py": "import random\nrandom.Random()"}, 1),
    ("files_over_1200_lines", {APP + "chat/a.py": "# source\n" * 1201}, 1),
    ("functions_over_150_lines", {APP + "chat/a.py": "def large():\n" + "    pass\n" * 151}, 1),
    ("largest_class_lines", {APP + "chat/a.py": "class Large:\n" + "    pass\n" * 160}, 161),
    ("quarantined_tests", {"src/tests/quarantine.toml": '[[tests]]\nnodeid = "test_missing"\nreason = "broken fixture"\n'}, 1),
    ("fixed_sleeps_in_tests", {"src/tests/test_a.py": "from time import sleep\nsleep(1)"}, 1),
    ("mypy_ignored_modules", {"pyproject.toml": '[[tool.mypy.overrides]]\nmodule = ["app.old.*", "app.other.*"]\nignore_errors = true\n', APP + "old/a.py": "", APP + "old/b.py": "", APP + "other/a.py": ""}, 2),
    ("compat_modules", {APP + "chat/old_compat.py": ""}, 1),
    ("process_local_state_unapproved", {APP + "chat/a.py": "cache = {}"}, 1),
    ("unreachable_rpg_modules", {APP + "production.py": "import app.rpg.live", APP + "rpg/live.py": "", APP + "rpg/dead.py": ""}, 1),
    ("web_fetch_assignment_files", {WEB + "app/a.ts": "window.fetch = one; window.fetch = two;"}, 1),
    ("web_omnix_window_flags", {WEB + "app/a.ts": "window.__omnixFlag = true; window.__omnixFlag;"}, 1),
    ("web_raw_fetch_outside_api", {WEB + "app/a.ts": "fetch('/api/a');"}, 1),
    ("web_handwritten_api_types", {WEB + "api/a.ts": "interface SaveRequest { value: string; }"}, 1),
    ("web_important", {WEB + "styles.css": "a {color: red !important;}"}, 1),
    ("web_hardcoded_colors", {WEB + "styles.css": "#abc {color: #fff; background: rgba(0,0,0,1);}"}, 2),
    ("web_mutation_observer_files", {WEB + "app/a.ts": "new MutationObserver(one); new MutationObserver(two);"}, 1),
    ("web_set_interval_files", {WEB + "app/a.ts": "setInterval(one, 1); window.setInterval(two, 1);"}, 1),
    ("web_custom_event_dispatch_files", {WEB + "app/a.ts": "window.dispatchEvent(new CustomEvent('ready'));"}, 1),
    ("web_unreachable_modules", {WEB + "main.tsx": "import './live';", WEB + "live.ts": "", WEB + "dead.ts": ""}, 1),
    ("web_error_boundaries", {WEB + "app/router.tsx": "createRoute({ errorComponent: ErrorPage });"}, 1),
    ("eslint_baseline_disables", {WEB + "app/a.ts": "// eslint-disable-next-line no-console\nconsole.log('x');"}, 1),
    ("inline_prompt_strings", {APP + "chat/a.py": "SYSTEM_PROMPT = " + repr("You are a careful assistant. Answer only using the evidence in this conversation.")}, 1),
]


@pytest.mark.parametrize("key,sources,expected", CASES, ids=[case[0] for case in CASES])
def test_each_source_metric_detector(key, sources, expected):
    result = observed(sources)
    assert result["errors"] == []
    assert result["metrics"][key]["value"] == expected


def test_scorecard_covers_every_roadmap_metric():
    roadmap = (SCRIPTS.parent / "docs/ENTERPRISE_ARCHITECTURE_ROADMAP_2026-09-27.md").read_text(encoding="utf-8")
    appendix = roadmap.split("### Appendix E", 1)[1].split("### Appendix F", 1)[0]
    import re
    expected = set(re.findall(r"\| `([^`]+)` \|", appendix))
    result = observed({})
    assert set(result["metrics"]) == expected
    exercised = {case[0] for case in CASES} | metrics.RUNTIME_METRICS | {"web_openapi_path_coverage_pct"}
    assert exercised == expected


def test_semantically_invalid_python_cannot_be_certified_even_when_ast_parse_accepts_it():
    result = observed({APP + "unused.py": "return 42"})
    assert result["errors"]
    assert result["evidence"]["python_syntax_errors"] == [APP + "unused.py"]


def test_lint_report_is_excluded_from_runtime_source_digest():
    sources = {APP + "chat/a.py": "value = 1"}
    before = metrics.source_digest(sources)
    sources["resources/architecture/lint-baseline.json"] = '{"violations": []}'
    assert metrics.source_digest(sources) == before


@pytest.mark.parametrize("source,foreign,patchers", [
    ("import external\ntarget = external\ntarget.method = replacement", 1, 0),
    ("import importlib\ntarget = importlib.import_module('external')\ntarget.method = replacement", 1, 0),
    ("from external import Foreign\ndef patch(target: type[Foreign]):\n    target.method = replacement", 1, 0),
    ("class Local:\n    pass\ntarget_cls = Local\ntarget_cls.method = replacement", 0, 0),
    ("import external\ndef patch(external):\n    external.method = replacement", 0, 0),
    ("from fastapi import FastAPI\ntarget = FastAPI\ntarget.__init__ = replacement", 1, 1),
    ("from fastapi import FastAPI\ndef patch(target: type[FastAPI]):\n    target.__init__ = replacement", 1, 1),
    ("from fastapi import FastAPI\nassign = setattr\nassign(FastAPI, '__init__', replacement)", 1, 1),
    ("class FastAPI:\n    pass\nFastAPI.__init__ = replacement", 0, 0),
    ("from external import FastAPI\nFastAPI.__init__ = replacement", 1, 0),
    ("from fastapi import FastAPI\ninstance = FastAPI()\ninstance.__init__ = replacement", 0, 0),
    ("from fastapi import FastAPI\nclass Local(FastAPI):\n    pass\nLocal.__init__ = replacement", 0, 0),
    ("from fastapi import FastAPI\nfor FastAPI.__init__ in replacements:\n    pass", 1, 1),
    ("from fastapi import FastAPI\ndel FastAPI.__init__", 1, 1),
])
def test_patch_metrics_share_lexical_provenance_with_lint(source, foreign, patchers):
    result = observed({APP + "gateway/a.py": source})
    assert not result["errors"]
    assert result["metrics"]["foreign_attribute_assignments"]["value"] == foreign
    assert result["metrics"]["fastapi_init_patchers"]["value"] == patchers


@pytest.mark.parametrize("key", sorted(metrics.RUNTIME_METRICS))
def test_each_runtime_metric_consumes_bound_disposable_evidence(key):
    result = observed({})
    report = {"schema_version": 1, "source_digest": result["source_digest"],
              "environment": "disposable", "measured_at": datetime.now(timezone.utc).isoformat(),
              "metrics": {name: 7 for name in metrics.RUNTIME_METRICS}}
    updated = metrics.measure({}, config, openapi={"paths": {}}, runtime_report=report)
    assert updated["errors"] == []
    assert updated["metrics"][key]["value"] == 7


def test_web_api_coverage_normalizes_template_parameters_and_counts_unknown_calls():
    sources = {WEB + "app/a.ts": "fetch(`/api/jobs/${id}`); fetch('/api/missing'); fetch(dynamicPath);"}
    result = observed(sources, openapi={"paths": {"/api/jobs/{job_id}": {}}})
    assert result["metrics"]["web_openapi_path_coverage_pct"]["value"] == pytest.approx(100 / 3, abs=1e-6)


def test_negative_cases_do_not_count_compliant_code():
    sources = {
        APP + "config/a.py": "import os\nos.getenv('X')",
        APP + "runtime/net.py": "import os\nos.getenv('X')",
        APP + "persistence/job_repository.py": "connection.execute('SELECT * FROM omnix_jobs')",
        APP + "persistence/blob_store.py": "LocalBlobStore(); asset.storage_path",
        APP + "production.py": "bootstrap_local_tenant()",
        APP + "chat/a.py": "class Local:\n    pass\nLocal.attribute = 1\ntry:\n    call()\nexcept Exception:\n    logger.exception('failed')",
        APP + "rpg/core/a.py": "import random\nrandom.Random(42)",
        APP + "gateway/a.py": "router = APIRouter(prefix='/internal')\n@router.get('/secret', include_in_schema=False)\nasync def route():\n    await work()\n@app.get('/health')\ndef health():\n    return {}\n",
        WEB + "api/a.ts": "fetch('/api/a'); // window.fetch = replacement;\nconst text = '/* not a comment */';",
    }
    result = observed(sources)
    for key in ("env_reads_outside_config", "platform_table_sql_outside_owner", "local_blob_store_constructions", "absolute_storage_path_reads", "bootstrap_calls_outside_startup", "foreign_attribute_assignments", "silent_broad_excepts", "rpg_nondeterminism", "async_handlers_without_await", "schema_excluded_routes", "routes_without_permission", "web_raw_fetch_outside_api", "web_fetch_assignment_files"):
        assert result["metrics"][key]["value"] == 0, key


def test_nested_await_does_not_hide_a_blocking_async_handler():
    result = observed({APP + "gateway/a.py": "@app.get('/api/a')\nasync def route():\n    async def unused():\n        await work()\n    return {}"})
    assert result["metrics"]["async_handlers_without_await"]["value"] == 1


def test_lazy_imports_are_layer_checked_but_do_not_form_module_level_cycles():
    result = observed({APP + "jobs/a.py": "def work():\n    import app.chat.b", APP + "chat/b.py": "import app.jobs.a"})
    assert result["metrics"]["package_cycles"]["value"] == 0
    assert result["metrics"]["layer_violations"]["value"] == 1


def test_same_feature_imports_are_allowed_but_other_features_are_not():
    result = observed({APP + "chat/a.py": "from app.chat import b\nimport app.chat.c\nfrom app.rpg import core"})
    assert result["metrics"]["layer_violations"]["value"] == 1


def test_whole_environment_reads_and_collection_methods_are_detected_once():
    source = "import os\nfrom os import environ\na = dict(os.environ)\nb = environ.copy()\nc = os.environ['C']\nd = os.environ.get('D')\nos.environ['WRITE_ONLY'] = 'value'"
    assert observed({APP + "chat/a.py": source})["metrics"]["env_reads_outside_config"]["value"] == 4


def test_model_servers_and_python_startup_hooks_are_production_source():
    result = observed({"src/sitecustomize.py": "import sys\nsys.meta_path.append(hook)", "src/tts_server.py": "print('runtime')", "scripts/operator_cli.py": "print('cli')"})
    assert result["metrics"]["foreign_attribute_assignments"]["value"] == 0
    assert result["metrics"]["print_calls"]["value"] == 0
    assert result["evidence"]["lint_counts"]["AL003"] == 1


def test_scoped_queries_and_seeded_random_are_not_unbounded_or_nondeterministic():
    result = observed({APP + "persistence/custom_repository.py": "def list_items():\n    sql = 'SELECT id FROM things LIMIT %s'\n    return connection.execute(sql, (limit,)).fetchall()", APP + "rpg/core/a.py": "import random as rng\nrng.Random(seed)"})
    assert result["metrics"]["unbounded_fetchall"]["value"] == 0
    assert result["metrics"]["rpg_nondeterminism"]["value"] == 0


def test_limited_query_in_another_scope_cannot_hide_unbounded_fetchall():
    source = "def other():\n    sql = 'SELECT id FROM things LIMIT 10'\ndef list_items():\n    return connection.execute(sql).fetchall()"
    assert observed({APP + "persistence/custom_repository.py": source})["metrics"]["unbounded_fetchall"]["value"] == 1


def test_reassigned_dynamic_sql_cannot_inherit_an_earlier_limit():
    source = "def list_items():\n    sql = 'SELECT id FROM things LIMIT 10'\n    sql = external_query\n    return connection.execute(sql).fetchall()"
    assert observed({APP + "persistence/custom_repository.py": source})["metrics"]["unbounded_fetchall"]["value"] == 1


def test_cursor_assignment_resolves_query_within_same_scope():
    source = "def list_items():\n    sql = 'SELECT id FROM things LIMIT %s'\n    cursor = connection.execute(sql, (limit,))\n    return cursor.fetchall()"
    assert observed({APP + "persistence/custom_repository.py": source})["metrics"]["unbounded_fetchall"]["value"] == 0


def test_typescript_functions_are_measured_and_control_blocks_are_not_functions():
    result = observed({WEB + "main.tsx": "const large = () => {\n" + "  doWork();\n" * 151 + "};\n"})
    assert result["metrics"]["functions_over_150_lines"]["value"] == 1
    assert metrics.js_function_spans("if (ready) {\n work();\n}") == []


def test_window_flags_include_typed_aliases_casts_and_computed_installation_keys():
    result = observed({WEB + "app/a.ts": "const INSTALL_KEY = '__omnixInstall';\nconst liveWindow = window as Window & {__omnixReady?: boolean};\nliveWindow.__omnixReady = true;\n(window as SomeWindow)[INSTALL_KEY] = true;"})
    assert result["metrics"]["web_omnix_window_flags"]["value"] == 2


def test_route_factories_count_concrete_routes_and_boundaries():
    source = "const root = createRootRoute({});\nfunction moduleRoute<const T extends string>(id: string, path: T) { return createRoute({path, errorComponent: ErrorPage}); }\nconst one = moduleRoute('one', 'one');\nconst two = moduleRoute('two', 'two');"
    result = observed({WEB + "app/router.tsx": source})
    assert result["evidence"]["web_route_count"] == 3
    assert result["metrics"]["web_error_boundaries"]["value"] == 2


def test_invalid_hex_lengths_are_not_colors():
    result = observed({WEB + "styles.css": "a { color: #12345; border-color: #1234567; background: #1234;}"})
    assert result["metrics"]["web_hardcoded_colors"]["value"] == 1


def test_async_and_browser_fixed_waits_are_inventory_evidence_separate_from_time_sleep():
    source = "import asyncio\nimport time\nasync def test_wait():\n    await asyncio.sleep(1)\n    time.sleep(2)\n    page.wait_for_timeout(3000)\n    await asyncio.sleep(delay)"
    result = observed({"src/tests/test_a.py": source})
    assert result["metrics"]["fixed_sleeps_in_tests"]["value"] == 1
    assert len(result["evidence"]["other_fixed_sleeps_in_tests"]) == 2


def test_handwritten_api_aliases_are_counted_but_generated_schema_aliases_are_not():
    source = "type SaveResponse = string | null;\ntype GoodResponse = components['schemas']['SaveResponse'];\nconst text = 'type FakeRequest = string';"
    assert observed({WEB + "api/a.ts": source})["metrics"]["web_handwritten_api_types"]["value"] == 1


def test_web_glob_reachability_resolves_parent_segments():
    sources = {WEB + "main.tsx": "import './app/registry';", WEB + "app/registry.ts": "import.meta.glob('../features/*.tsx');", WEB + "features/live.tsx": "", WEB + "dead.ts": ""}
    assert observed(sources)["metrics"]["web_unreachable_modules"]["value"] == 1


def test_process_state_inventory_approval_requires_exact_subject_and_reason():
    sources = {APP + "chat/a.py": "cache = {}; other = {}",
               "resources/architecture/process-local-state.json": json.dumps({"entries": [
                   {"path": APP + "chat/a.py", "symbol": "cache", "approved": True, "reason": "bounded temporary cache"},
                   {"path": APP + "chat/a.py", "symbol": "other", "approved": True},
               ]})}
    assert observed(sources)["metrics"]["process_local_state_unapproved"]["value"] == 1


def test_explicit_state_inventory_entries_are_counted_even_when_not_mutable_literals():
    sources = {APP + "chat/a.py": "provider = None", "resources/architecture/process-local-state.json": json.dumps({"entries": [
        {"path": APP + "chat/a.py", "symbol": "provider", "approved": False},
    ]})}
    assert observed(sources)["metrics"]["process_local_state_unapproved"]["value"] == 1


def test_mypy_reports_override_pattern_count_and_actual_matching_modules():
    sources = {"mypy.ini": "[mypy-app.chat.*, app.missing.*]\nignore_errors = true\n", APP + "chat/a.py": "", APP + "chat/b.py": "", APP + "chat/c.py": "", APP + "jobs/a.py": ""}
    result = observed(sources)
    assert result["metrics"]["mypy_ignored_modules"]["value"] == 2
    assert result["evidence"]["mypy_ignored_modules"] == ["app.chat.a", "app.chat.b", "app.chat.c"]
    assert result["evidence"]["mypy_ignored_patterns"] == ["app.chat.*", "app.missing.*"]


@pytest.mark.parametrize("change", ["source", "environment", "expired", "missing", "nan"])
def test_unknown_or_stale_runtime_evidence_fails_closed(change):
    result = observed({})
    report = {"schema_version": 1, "source_digest": result["source_digest"], "environment": "disposable",
              "measured_at": datetime.now(timezone.utc).isoformat(), "metrics": {name: 0 for name in metrics.RUNTIME_METRICS}}
    if change == "source":
        report["source_digest"] = "wrong"
    elif change == "environment":
        report["environment"] = "operator"
    elif change == "expired":
        report["measured_at"] = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat()
    elif change == "missing":
        report["metrics"].pop("collection_errors")
    else:
        report["metrics"]["collection_errors"] = float("nan")
    updated = metrics.measure({}, config, openapi={"paths": {}}, runtime_report=report)
    assert updated["errors"]
    assert metrics.compare(updated, result)


@pytest.mark.parametrize("key,delta", [("print_calls", 1), ("rls_coverage_pct", -1)])
def test_ratchet_rejects_regression_in_either_direction(key, delta):
    baseline = observed({})
    baseline["metrics"][key]["value"] = 10
    current = deepcopy(baseline)
    current["metrics"][key]["value"] += delta
    assert metrics.compare(current, baseline) == [f"{key}: worsened from 10 to {10 + delta}"]


def test_ratchet_accepts_improvements_and_rejects_metric_contract_changes():
    baseline = observed({})
    baseline["metrics"]["print_calls"]["value"] = 10
    current = deepcopy(baseline)
    current["metrics"]["print_calls"]["value"] = 9
    assert metrics.compare(current, baseline) == []
    current["metrics"]["print_calls"]["direction"] = "higher"
    assert "direction or target changed" in metrics.compare(current, baseline)[0]
    current["metrics"].pop("compat_modules")
    assert "baseline metric set mismatch" in metrics.compare(current, baseline)


def test_cli_cannot_overwrite_baseline_through_output_argument(tmp_path):
    baseline = tmp_path / "baseline.json"
    baseline.write_text("original baseline", encoding="utf-8")
    assert metrics.main(["--root", str(tmp_path), "--check", "--baseline", str(baseline), "--output", str(baseline)]) == 2
    assert baseline.read_text(encoding="utf-8") == "original baseline"


def test_cli_update_keeps_baseline_intact_when_any_metric_regresses(tmp_path, monkeypatch):
    baseline = observed({})
    current = deepcopy(baseline)
    current["metrics"]["print_calls"]["value"] += 1
    path = tmp_path / "baseline.json"
    original = json.dumps(baseline)
    path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(metrics, "tracked_sources", lambda *args, **kwargs: {})
    monkeypatch.setattr(metrics, "load_layers", lambda *args: config)
    monkeypatch.setattr(metrics, "measure", lambda *args, **kwargs: current)
    assert metrics.main(["--root", str(tmp_path), "--baseline", str(path), "--update-baseline", "--output", str(tmp_path / "report.json")]) == 1
    assert path.read_text(encoding="utf-8") == original


def test_cli_update_atomically_accepts_improved_scorecard(tmp_path, monkeypatch):
    baseline = observed({})
    baseline["metrics"]["print_calls"]["value"] = 2
    current = deepcopy(baseline)
    current["metrics"]["print_calls"]["value"] = 1
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")
    monkeypatch.setattr(metrics, "tracked_sources", lambda *args, **kwargs: {})
    monkeypatch.setattr(metrics, "load_layers", lambda *args: config)
    monkeypatch.setattr(metrics, "measure", lambda *args, **kwargs: current)
    assert metrics.main(["--root", str(tmp_path), "--baseline", str(path), "--update-baseline", "--output", str(tmp_path / "report.json")]) == 0
    assert json.loads(path.read_text(encoding="utf-8")) == current
    assert sorted(file.name for file in tmp_path.iterdir()) == ["baseline.json", "report.json"]


def test_tracked_scope_excludes_untracked_vendor_generated_and_deleted_files(tmp_path):
    from architecture_analysis import tracked_sources

    tracked = {"src/app/a.py": "print('tracked')", "src/app/deleted.py": "",
               "src/vendor/a.py": "print('vendor')", WEB + "api/generated/types.ts": "window.fetch = x;"}
    for path, source in tracked.items():
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(source)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "--", *tracked], check=True, capture_output=True)
    (tmp_path / "src/app/untracked.py").write_text("print('untracked')")
    (tmp_path / "src/app/deleted.py").unlink()
    assert tracked_sources(tmp_path) == {"src/app/a.py": "print('tracked')"}
