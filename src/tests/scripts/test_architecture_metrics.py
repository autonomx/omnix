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
WEB = "web/src/"
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
    ("package_cycles", {APP + "jobs/a.py": "import app.platform.chat.b", APP + "platform/chat/b.py": "import app.jobs.a"}, 1),
    ("layer_violations", {APP + "jobs/a.py": "def work():\n    import app.platform.chat.b", APP + "platform/chat/b.py": "",
                          APP + "platform/chat/feature.py": "FEATURE = FeatureModule(id='chat', title='Chat', tier='platform')"}, 1),
    ("foreign_attribute_assignments", {APP + "composition/gateway/a.py": "import another\nanother.method = replacement"}, 1),
    ("install_hook_functions", {APP + "composition/gateway/a.py": "import another\ndef install_hook():\n    another.method = replacement"}, 1),
    ("fastapi_init_patchers", {APP + "composition/gateway/a.py": "from fastapi import FastAPI as App\nApp.__init__ = wrapper\nApp.__init__ = second"}, 1),
    ("async_handlers_without_await", {APP + "composition/gateway/a.py": "@app.get('/api/a')\nasync def route():\n    return {}"}, 1),
    ("schema_excluded_routes", {APP + "composition/gateway/a.py": "@app.get('/api/a', include_in_schema=False)\ndef route():\n    return {}"}, 1),
    ("untyped_body_routes", {APP + "composition/gateway/a.py": "@app.post('/api/a')\ndef route(body: dict[str, int]):\n    return body"}, 1),
    ("routes_without_permission", {APP + "composition/gateway/a.py": "@app.get('/api/a')\ndef route():\n    return {}"}, 1),
    ("bootstrap_calls_outside_startup", {APP + "platform/chat/a.py": "from app.persistence.identity_service import bootstrap_local_tenant as bootstrap\nbootstrap()"}, 1),
    ("env_reads_outside_config", {APP + "platform/chat/a.py": "import os\nvalue = os.environ['X']\nos.environ['Y'] = 'write-only'"}, 1),
    ("print_calls", {APP + "platform/chat/a.py": "print('debug')"}, 1),
    ("silent_broad_excepts", {APP + "platform/chat/a.py": "try:\n    call()\nexcept Exception:\n    pass"}, 1),
    ("star_imports", {APP + "platform/chat/a.py": "from another import *"}, 1),
    ("platform_table_sql_outside_owner", {APP + "platform/chat/a.py": "connection.execute('SELECT id FROM omnix_jobs WHERE id = %s')"}, 1),
    ("direct_requests_calls", {APP + "platform/chat/a.py": "import requests as http\nhttp.post('/api/a')"}, 1),
    ("local_blob_store_constructions", {APP + "platform/chat/a.py": "from app.persistence.blob_store import LocalBlobStore as Store\nStore()"}, 1),
    ("absolute_storage_path_reads", {APP + "platform/chat/a.py": "a.storage_path\nb.storage_path"}, 1),
    ("unbounded_fetchall", {APP + "persistence/custom_repository.py": "connection.execute('SELECT id FROM things').fetchall()"}, 1),
    ("capped_500_queries", {APP + "persistence/custom_repository.py": "connection.execute('SELECT id FROM things LIMIT 500').fetchall()"}, 1),
    ("rpg_nondeterminism", {APP + "apps/rpg/foundation/core/a.py": "import random\nrandom.Random()"}, 1),
    ("files_over_1200_lines", {APP + "platform/chat/a.py": "# source\n" * 1201}, 1),
    ("functions_over_150_lines", {APP + "platform/chat/a.py": "def large():\n" + "    pass\n" * 151}, 1),
    ("largest_class_lines", {APP + "platform/chat/a.py": "class Large:\n" + "    pass\n" * 160}, 161),
    ("quarantined_tests", {"src/tests/quarantine.toml": '[[tests]]\nnodeid = "test_missing"\nreason = "broken fixture"\n'}, 1),
    ("fixed_sleeps_in_tests", {"src/tests/test_a.py": "from time import sleep\nsleep(1)"}, 1),
    ("mypy_ignored_modules", {"pyproject.toml": '[[tool.mypy.overrides]]\nmodule = ["app.old.*", "app.other.*"]\nignore_errors = true\n', APP + "old/a.py": "", APP + "old/b.py": "", APP + "other/a.py": ""}, 2),
    ("compat_modules", {APP + "platform/chat/old_compat.py": ""}, 1),
    ("process_local_state_unapproved", {APP + "platform/chat/a.py": "cache = {}"}, 1),
    ("unbounded_module_caches", {APP + "platform/chat/a.py": "from functools import lru_cache\n@lru_cache(maxsize=None)\ndef parse(value):\n    return value"}, 1),
    ("unreachable_rpg_modules", {APP + "composition/production.py": "import app.apps.rpg.live", APP + "apps/rpg/live.py": "", APP + "apps/rpg/dead.py": "",
                                 APP + "apps/rpg/feature.py": "", APP + "apps/rpg/declarations.py": ""}, 2),
    ("web_fetch_assignment_files", {WEB + "app/a.ts": "window.fetch = one; window.fetch = two;"}, 1),
    ("web_omnix_window_flags", {WEB + "app/a.ts": "window.__omnixFlag = true; window.__omnixFlag;"}, 1),
    ("web_raw_fetch_outside_api", {WEB + "app/a.ts": "fetch('/api/a');"}, 1),
    ("web_handwritten_api_types", {WEB + "api/a.ts": "interface SaveRequest { value: string; }"}, 1),
    ("web_important", {WEB + "styles.css": "a {color: red !important;}"}, 1),
    ("web_hardcoded_colors", {WEB + "styles.css": "#abc {color: #fff; background: rgba(0,0,0,1);}"}, 2),
    ("web_hardcoded_colors", {WEB + "styles.css": "a {color: white; background: var(--pd-red); animation: pulse-green 1s;}"}, 1),
    ("web_mutation_observer_files", {WEB + "app/a.ts": "new MutationObserver(one); new MutationObserver(two);"}, 1),
    ("web_set_interval_files", {WEB + "app/a.ts": "setInterval(one, 1); window.setInterval(two, 1);"}, 1),
    ("web_custom_event_dispatch_files", {WEB + "app/a.ts": "window.dispatchEvent(new CustomEvent('ready'));"}, 1),
    ("web_unreachable_modules", {WEB + "main.tsx": "import './live';", WEB + "live.ts": "", WEB + "dead.ts": ""}, 1),
    ("web_global_css_files", {WEB + "main.tsx": "import './a.css';\nimport 'pkg/x.css';\nimport './app';", WEB + "a.css": "@import './b.css';", WEB + "b.css": "", WEB + "app.tsx": "import './c.css';", WEB + "c.css": ""}, 3),
    ("web_error_boundaries", {WEB + "app/router.tsx": "createRoute({ errorComponent: ErrorPage });"}, 1),
    ("eslint_baseline_disables", {WEB + "app/a.ts": "// eslint-disable-next-line no-console\nconsole.log('x');"}, 1),
    ("inline_prompt_strings", {APP + "platform/chat/a.py": "SYSTEM_PROMPT = " + repr("You are a careful assistant. Answer only using the evidence in this conversation.")}, 1),
    # Platform architecture roadmap (ADR-0016), PA-0.3.
    ("reverse_contract_imports", {**{APP + "platform/chat/feature.py": "FEATURE = FeatureModule(id='chat', title='Chat', tier='platform')",
                                     APP + "platform/characters/feature.py": "FEATURE = FeatureModule(id='characters', title='Characters', tier='platform', depends_on=('chat',))"},
                                  APP + "platform/characters/contracts.py": "", APP + "platform/chat/a.py": "from app.platform.characters.contracts import Port"}, 1),
    ("any_scope_package_cycles", {APP + "platform/chat/feature.py": "FEATURE = FeatureModule(id='chat', title='Chat', tier='platform')",
                                  APP + "jobs/a.py": "def work():\n    import app.platform.chat.b", APP + "platform/chat/b.py": "def work():\n    import app.jobs.a"}, 1),
    ("app_to_app_imports", {APP + "apps/trading/feature.py": "FEATURE = FeatureModule(id='trading', title='Trading', tier='app')",
                            APP + "apps/story/feature.py": "FEATURE = FeatureModule(id='story', title='Story', tier='app')",
                            APP + "apps/story/a.py": "import app.apps.trading.b", APP + "apps/trading/b.py": ""}, 1),
    ("uncovered_app_modules", {APP + "loose_helper.py": "VALUE = 1"}, 1),
    ("composition_imports_outside_composition", {APP + "platform/chat/feature.py": "FEATURE = FeatureModule(id='chat', title='Chat', tier='platform')",
                                                 APP + "platform/chat/a.py": "def work():\n    import app.composition.gateway.b", APP + "composition/gateway/b.py": ""}, 1),
    ("string_runtime_hooks", {APP + "platform/chat/a.py": "from app.runtime.hooks import RuntimeHookSpec\nHOOK = RuntimeHookSpec('name', handler)"}, 1),
    ("kernel_tools_naming_apps", {APP + "apps/trading/feature.py": "FEATURE = FeatureModule(id='trading', title='Trading', tier='app')",
                                  APP + "capabilities/registry.py": "_cap('trading.quote', 'Quote', 'd', category='trading')\n_cap('market.status', 'Status', 'd', category='trading')\n_cap('hermes.get_status', 'Status', 'd', category='platform')\n_cap('calendar.read', 'Read', 'd', category='productivity')"}, 2),
    ("platform_feature_specific_files", {APP + "apps/rpg/feature.py": "FEATURE = FeatureModule(id='rpg', title='RPG', tier='app')",
                                         APP + "settings/profile_rpg.py": "", APP + "settings/profile_core.py": ""}, 1),
    ("module_repositories_in_kernel", {APP + "apps/rpg/feature.py": "FEATURE = FeatureModule(id='rpg', title='RPG', tier='app')",
                                       APP + "persistence/rpg_turn_repository.py": "", APP + "persistence/job_repository.py": ""}, 1),
    ("web_feature_clients_in_shared_api", {APP + "apps/rpg/feature.py": "FEATURE = FeatureModule(id='rpg', title='RPG', tier='app')",
                                           WEB + "api/rpgMapClient.ts": "export const map = 1;", WEB + "api/rpgMapClient.test.ts": "",
                                           WEB + "api/http.ts": "export const http = 1;"}, 1),
    ("src_root_service_entrypoints", {"src/tts_server.py": "", "src/launch.py": ""}, 1),
    ("tracked_runtime_data_in_src", {APP + "data/sessions.json": "{}"}, 1),
    # PA-2.2: table ownership (AL016).
    ("cross_module_sql", {APP + "platform/chat/feature.py": "FEATURE = FeatureModule(id='chat', title='Chat', tier='platform')",
                          APP + "persistence/migrations/0001_platform.sql": "CREATE TABLE omnix_rpg_turns (id int);",
                          "resources/architecture/historical-table-owners.json": '{"tables": {"omnix_rpg_turns": {"owner": "rpg", "created_by": "0001_platform"}}}',
                          APP + "platform/chat/a.py": "SQL = 'SELECT id FROM omnix_rpg_turns'"}, 1),
    ("kernel_named_module_tables", {APP + "persistence/migrations/0001_platform.sql": "CREATE TABLE omnix_rpg_turns (id int);",
                                    "resources/architecture/historical-table-owners.json": '{"tables": {"omnix_rpg_turns": {"owner": "rpg", "created_by": "0001_platform"}}}',
                                    APP + "persistence/retention.py": "SQL = 'DELETE FROM omnix_rpg_turns'"}, 1),
    ("tables_without_owner", {APP + "persistence/migrations/0001_platform.sql": "CREATE TABLE omnix_a (id int);\nCREATE TABLE omnix_b (id int);",
                              "resources/architecture/historical-table-owners.json": '{"tables": {"omnix_a": {"owner": "kernel", "created_by": "0001_platform"}}}'}, 1),
    ("app_migrations_in_kernel_dir", {APP + "persistence/migrations/0001_platform.sql": "CREATE TABLE omnix_rpg_turns (id int);",
                                      APP + "persistence/migrations/0002_more.sql": "CREATE TABLE omnix_jobs (id int);",
                                      "resources/architecture/historical-table-owners.json":
                                      '{"tables": {"omnix_rpg_turns": {"owner": "rpg", "created_by": "0001_platform"}, '
                                      '"omnix_jobs": {"owner": "kernel", "created_by": "0002_more"}}}'}, 1),
    ("historical_owner_map_additions", {"resources/architecture/historical-table-owners.json":
                                        '{"frozen_after": "0001_platform", "tables": {"omnix_a": {"owner": "kernel", "created_by": "0002_new"}}}'}, 1),
]


def test_docstrings_and_sql_in_prompt_functions_are_not_prompts():
    source = (
        "def build_prompt(connection):\n"
        "    " + repr("Build the canonical prompt once per turn for every chat backend.") + "\n"
        "    connection.execute(" + repr("SELECT id, content FROM omnix_prompt_templates WHERE id = %s") + ")\n"
        "    return " + repr("You are a careful assistant. Answer only using the evidence given.") + "\n"
    )
    assert observed({APP + "platform/chat/a.py": source})["metrics"]["inline_prompt_strings"]["value"] == 1


@pytest.mark.parametrize("key,sources,expected", CASES, ids=[case[0] for case in CASES])
def test_each_source_metric_detector(key, sources, expected):
    result = observed(sources)
    assert result["errors"] == []
    assert result["metrics"][key]["value"] == expected


def test_only_exact_documented_stream_route_is_exempt_from_schema_metric():
    source = {
        APP + "composition/gateway/events.py": "@app.get('/events', include_in_schema=False)\ndef events():\n    return response",
        "docs/architecture/api-transport-exceptions.md": (
            "| Source | Method | Route path | Transport |\n"
            "|---|---|---|---|\n"
            "| `src/app/composition/gateway/events.py` | GET | `/events` | Server-Sent Events |\n"
        ),
    }
    result = observed(source)
    assert result["metrics"]["schema_excluded_routes"]["value"] == 0

    source["docs/architecture/api-transport-exceptions.md"] = source[
        "docs/architecture/api-transport-exceptions.md"
    ].replace("GET", "POST")
    result = observed(source)
    assert result["metrics"]["schema_excluded_routes"]["value"] == 1


def test_tracked_transport_inventory_is_loaded_for_the_working_tree_scan():
    sources = metrics.tracked_sources(SCRIPTS.parent)
    result = observed(sources)
    assert "docs/architecture/api-transport-exceptions.md" in sources
    assert result["metrics"]["schema_excluded_routes"]["value"] == 0


def test_raw_request_body_parsing_is_not_a_typed_body_contract():
    result = observed({
        APP + "composition/gateway/a.py": (
            "from fastapi import Request\n"
            "@app.post('/api/a')\n"
            "async def route(request: Request):\n"
            "    return await request.json()\n"
        ),
    })
    assert result["metrics"]["untyped_body_routes"]["value"] == 1

    result = observed({
        APP + "composition/gateway/a.py": (
            "from fastapi import Request\n"
            "from pydantic import BaseModel\n"
            "class Payload(BaseModel):\n"
            "    value: int\n"
            "@app.post('/api/a')\n"
            "async def route(request: Request, payload: Payload):\n"
            "    return payload\n"
        ),
    })
    assert result["metrics"]["untyped_body_routes"]["value"] == 0


def test_scorecard_covers_every_roadmap_metric():
    roadmap = (SCRIPTS.parent / "docs/ENTERPRISE_ARCHITECTURE_ROADMAP_2026-09-27.md").read_text(encoding="utf-8")
    appendix = roadmap.split("### Appendix E", 1)[1].split("### Appendix F", 1)[0]
    import re
    expected = set(re.findall(r"\| `([^`]+)` \|", appendix))
    # The platform architecture roadmap (ADR-0016) adds metrics in its
    # "New metrics" lists, one list per work package that builds them.
    platform = (SCRIPTS.parent / "docs/PLATFORM_ARCHITECTURE_ROADMAP_2026-10-04.md").read_text(encoding="utf-8")
    for block in re.findall(r"- \*\*New metrics:\*\*\n((?:  - `[^`]+`.*\n)+)", platform):
        expected |= set(re.findall(r"  - `([^`]+)`", block))
    result = observed({})
    assert set(result["metrics"]) == expected
    exercised = {case[0] for case in CASES} | metrics.RUNTIME_METRICS | {"web_openapi_path_coverage_pct"}
    assert exercised == expected


def test_semantically_invalid_python_cannot_be_certified_even_when_ast_parse_accepts_it():
    result = observed({APP + "unused.py": "return 42"})
    assert result["errors"]
    assert result["evidence"]["python_syntax_errors"] == [APP + "unused.py"]


def test_lint_report_is_excluded_from_runtime_source_digest():
    sources = {APP + "platform/chat/a.py": "value = 1"}
    before = metrics.source_digest(sources)
    sources["resources/architecture/lint-baseline.json"] = '{"violations": []}'
    assert metrics.source_digest(sources) == before


def test_roadmap_changes_do_not_invalidate_runtime_evidence_but_markdown_inputs_do():
    sources = {
        APP + "platform/chat/a.py": "value = 1",
        "docs/roadmap/PROGRESS.md": "WP-1.1 is in progress",
        "resources/examples/voice/prompt.md": "Speak clearly.",
    }
    before = metrics.source_digest(sources)
    sources["docs/roadmap/PROGRESS.md"] = "WP-1.1 is done"
    assert metrics.source_digest(sources) == before
    sources["resources/examples/voice/prompt.md"] = "Speak naturally."
    assert metrics.source_digest(sources) != before
    sources[APP + "platform/chat/a.py"] = "value = 2"
    assert metrics.source_digest(sources) != before


def test_feature_catalog_module_attribute_is_a_reachability_root():
    result = observed({
        APP + "composition/production.py": "FEATURE = 'app.apps.rpg.feature:FEATURE'",
        APP + "apps/rpg/feature.py": "from app.apps.rpg.live import launch",
        APP + "apps/rpg/live.py": "",
        APP + "apps/rpg/dead.py": "",
    })
    assert result["metrics"]["unreachable_rpg_modules"]["value"] == 1
    assert result["evidence"]["unreachable_rpg_modules"] == [APP + "apps/rpg/dead.py"]


def test_all_export_list_is_not_counted_as_process_local_state():
    result = observed({
        APP + "platform/chat/a.py": "__all__ = ['PublicType']\ncache = {}",
    })
    assert result["metrics"]["process_local_state_unapproved"]["value"] == 1
    assert result["evidence"]["process_local_state_candidates"] == [{
        "path": APP + "platform/chat/a.py",
        "symbol": "cache",
        "approved": False,
    }]


def test_process_state_inventory_requires_reviewed_cache_policy():
    source = {
        APP + "platform/chat/a.py": (
            "_MAX_CACHE_ENTRIES = 8\n_CACHE_TTL_SECONDS = 30.0\ncache = {}\n"
            "def put(key, value, now):\n"
            "    if len(cache) >= _MAX_CACHE_ENTRIES:\n"
            "        cache.pop(next(iter(cache)))\n"
            "    cache[key] = (now + _CACHE_TTL_SECONDS, value)\n"
            "def invalidate_cache():\n    cache.clear()\n"
        ),
        "resources/architecture/process-local-state.json": json.dumps({"entries": [{
            "path": APP + "platform/chat/a.py",
            "symbol": "cache",
            "category": "cache",
            "reason": "Small derived response cache.",
            "max_entries_symbol": "_MAX_CACHE_ENTRIES",
            "ttl_symbol": "_CACHE_TTL_SECONDS",
            "invalidation": "invalidate_cache",
        }]}),
    }
    report = observed(source)
    assert report["metrics"]["process_local_state_unapproved"]["value"] == 0
    assert report["metrics"]["unbounded_module_caches"]["value"] == 0

    source["resources/architecture/process-local-state.json"] = json.dumps({"entries": [{
        "path": APP + "platform/chat/a.py",
        "symbol": "cache",
        "category": "cache",
        "reason": "Small derived response cache.",
        "max_entries_symbol": "_MAX_CACHE_ENTRIES",
        "invalidation": "invalidate_cache",
    }]})
    report = observed(source)
    assert report["metrics"]["unbounded_module_caches"]["value"] == 1


def test_process_state_cache_policy_reads_arithmetic_ttl_constants():
    source = {
        APP + "platform/chat/a.py": (
            "_MAX_CACHE_ENTRIES = 8\n_CACHE_TTL_SECONDS = 5 * 60\ncache = {}\n"
            "def put(key, value, now):\n"
            "    if len(cache) >= _MAX_CACHE_ENTRIES:\n"
            "        cache.pop(next(iter(cache)))\n"
            "    cache[key] = (now + _CACHE_TTL_SECONDS, value)\n"
            "def invalidate_cache():\n    cache.clear()\n"
        ),
        "resources/architecture/process-local-state.json": json.dumps({"entries": [{
            "path": APP + "platform/chat/a.py",
            "symbol": "cache",
            "category": "cache",
            "reason": "The parsed value is reconstructible.",
            "max_entries_symbol": "_MAX_CACHE_ENTRIES",
            "ttl_symbol": "_CACHE_TTL_SECONDS",
            "invalidation": "invalidate_cache",
        }]}),
    }
    report = observed(source)
    assert report["metrics"]["unbounded_module_caches"]["value"] == 0
    assert report["evidence"]["process_local_state"][0]["ttl_seconds"] == 300


def test_bounded_lru_cache_without_ttl_and_invalidation_is_unbounded():
    report = observed({
        APP + "platform/chat/a.py": (
            "from functools import lru_cache\n"
            "@lru_cache(maxsize=32)\n"
            "def lookup(value):\n    return value\n"
        ),
    })
    assert report["metrics"]["process_local_state_unapproved"]["value"] == 1
    assert report["metrics"]["unbounded_module_caches"]["value"] == 1
    assert report["evidence"]["process_local_state"][0]["kind"] == "function_cache"


def test_expiring_function_cache_requires_matching_invalidation_and_inventory():
    source = {
        APP + "platform/chat/a.py": (
            "from app.caching.bounded_cache import bounded_lru_cache\n"
            "@bounded_lru_cache(max_entries=8, ttl_seconds=30.0)\n"
            "def parse(value):\n    return value\n"
        ),
        "resources/architecture/process-local-state.json": json.dumps({"entries": [{
            "path": APP + "platform/chat/a.py",
            "symbol": "parse.__cache__",
            "category": "cache",
            "reason": "Pure parse result is process-local and disposable.",
            "max_entries": 8,
            "ttl_seconds": 30.0,
            "invalidation": "parse.cache_clear",
        }]}),
    }
    report = observed(source)
    assert report["metrics"]["process_local_state_unapproved"]["value"] == 0
    assert report["metrics"]["unbounded_module_caches"]["value"] == 0
    assert report["evidence"]["process_local_state"][0]["max_entries"] == 8


def test_process_state_scan_ignores_immutable_data_tables():
    source = APP + "platform/chat/a.py"
    report = observed({source: "CATALOG = {'one': 1, 'two': 2}\n"})
    assert report["metrics"]["process_local_state_unapproved"]["value"] == 0
    assert report["evidence"]["process_local_state"] == []


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
    result = observed({APP + "composition/gateway/a.py": source})
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


def test_web_api_coverage_skips_prefixes_and_reads_templates_queries_and_documented_websockets():
    sources = {
        WEB + "app/scope.ts": "const scopes = ['/api/assets', '/api/voice-'];",
        WEB + "app/a.ts": (
            "fetch(`/api/assets/${id}/file`); fetch('/api/character-live2d/runtime/core.min.js');"
            "fetch(`/api/research/status${query}`); new WebSocket('/api/tts/stream/websocket');"
        ),
        "docs/architecture/api-transport-exceptions.md": (
            "| Source | Route path |\n|---|---|\n| `src/app/platform/voice/tts.py` | `/api/tts/stream/websocket` |\n"
        ),
    }
    schema = {"paths": {
        "/api/assets/{asset_id}/file": {}, "/api/voice-profiles": {},
        "/api/character-live2d/runtime/{filename}": {}, "/api/research/status": {},
    }}
    result = observed(sources, openapi=schema)
    assert result["metrics"]["web_openapi_path_coverage_pct"]["value"] == 100
    assert result["evidence"]["web_api_path_prefixes"] == ["/api/assets", "/api/voice-"]


def test_documented_web_client_types_are_not_handwritten_api_types():
    inventory = (
        "| Web source | Type | What it describes |\n|---|---|---|\n"
        "| `web/src/features/worker.ts` | `Worker*` | Worker messages |\n"
    )
    source = {
        WEB + "features/worker.ts": "type WorkerRequest = { id: string };\ntype WorkerResponse = { id: string };",
        WEB + "api/a.ts": "type SaveRequest = { value: string };",
        "docs/architecture/api-transport-exceptions.md": inventory,
    }
    result = observed(source)
    assert result["metrics"]["web_handwritten_api_types"]["value"] == 1
    assert result["evidence"]["web_handwritten_api_types"] == [[WEB + "api/a.ts", "SaveRequest"]]

    source["docs/architecture/api-transport-exceptions.md"] = inventory + "| `web/src/features/gone.ts` | `*` | Removed |\n"
    with pytest.raises(metrics.AnalysisError, match="matches no declaration"):
        observed(source)


def test_negative_cases_do_not_count_compliant_code():
    sources = {
        APP + "config/a.py": "import os\nos.getenv('X')",
        APP + "runtime/net.py": "import os\nos.getenv('X')",
        APP + "persistence/job_repository.py": "connection.execute('SELECT * FROM omnix_jobs')",
        APP + "persistence/blob_store.py": "LocalBlobStore(); asset.storage_path",
        APP + "composition/production.py": "bootstrap_local_tenant()",
        APP + "platform/chat/a.py": "class Local:\n    pass\nLocal.attribute = 1\ntry:\n    call()\nexcept Exception:\n    logger.exception('failed')",
        APP + "apps/rpg/foundation/core/a.py": "import random\nrandom.Random(42)",
        APP + "composition/gateway/a.py": "router = APIRouter(prefix='/internal')\n@router.get('/secret', include_in_schema=False)\nasync def route():\n    await work()\n@app.get('/health')\ndef health():\n    return {}\n",
        WEB + "api/a.ts": "fetch('/api/a'); // window.fetch = replacement;\nconst text = '/* not a comment */';",
    }
    result = observed(sources)
    for key in ("env_reads_outside_config", "platform_table_sql_outside_owner", "local_blob_store_constructions", "absolute_storage_path_reads", "bootstrap_calls_outside_startup", "foreign_attribute_assignments", "silent_broad_excepts", "rpg_nondeterminism", "async_handlers_without_await", "schema_excluded_routes", "routes_without_permission", "web_raw_fetch_outside_api", "web_fetch_assignment_files"):
        assert result["metrics"][key]["value"] == 0, key


def test_nested_await_does_not_hide_a_blocking_async_handler():
    result = observed({APP + "composition/gateway/a.py": "@app.get('/api/a')\nasync def route():\n    async def unused():\n        await work()\n    return {}"})
    assert result["metrics"]["async_handlers_without_await"]["value"] == 1


def test_lazy_imports_are_layer_checked_but_do_not_form_module_level_cycles():
    result = observed({APP + "jobs/a.py": "def work():\n    import app.platform.chat.b", APP + "platform/chat/b.py": "import app.jobs.a"})
    assert result["metrics"]["package_cycles"]["value"] == 0
    assert result["metrics"]["layer_violations"]["value"] == 1


def test_same_feature_imports_are_allowed_but_other_features_are_not():
    result = observed({APP + "platform/chat/a.py": "from app.platform.chat import b\nimport app.platform.chat.c\nfrom app.apps.rpg import core"})
    assert result["metrics"]["layer_violations"]["value"] == 1


def test_whole_environment_reads_and_collection_methods_are_detected_once():
    source = "import os\nfrom os import environ\na = dict(os.environ)\nb = environ.copy()\nc = os.environ['C']\nd = os.environ.get('D')\nos.environ['WRITE_ONLY'] = 'value'"
    assert observed({APP + "platform/chat/a.py": source})["metrics"]["env_reads_outside_config"]["value"] == 4


def test_model_servers_and_python_startup_hooks_are_production_source():
    result = observed({"src/sitecustomize.py": "import sys\nsys.meta_path.append(hook)", "src/tts_server.py": "print('runtime')", "scripts/operator_cli.py": "print('cli')"})
    assert result["metrics"]["foreign_attribute_assignments"]["value"] == 0
    assert result["metrics"]["print_calls"]["value"] == 0
    assert result["evidence"]["lint_counts"]["AL003"] == 1


def test_scoped_queries_and_seeded_random_are_not_unbounded_or_nondeterministic():
    result = observed({APP + "persistence/custom_repository.py": "def list_items():\n    sql = 'SELECT id FROM things LIMIT %s'\n    return connection.execute(sql, (limit,)).fetchall()", APP + "apps/rpg/foundation/core/a.py": "import random as rng\nrng.Random(seed)"})
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


def test_type_only_imports_are_not_handwritten_api_declarations():
    source = (
        "import {\n"
        "  type SaveRequest,\n"
        "} from './contracts';\n"
        "import type { SaveResponse } from './contracts';\n"
    )
    assert observed({WEB + "api/a.ts": source})["metrics"]["web_handwritten_api_types"]["value"] == 0


def test_web_glob_reachability_resolves_parent_segments():
    sources = {WEB + "main.tsx": "import './app/registry';", WEB + "app/registry.ts": "import.meta.glob('../features/*.tsx');", WEB + "features/live.tsx": "", WEB + "dead.ts": ""}
    assert observed(sources)["metrics"]["web_unreachable_modules"]["value"] == 1


def test_unused_feature_public_api_is_not_dead_but_what_only_it_exports_is():
    sources = {
        WEB + "main.tsx": "import './features/chat/module';",
        WEB + "features/chat/module.ts": "",
        WEB + "features/chat/index.ts": "export * from './helper';",
        WEB + "features/chat/helper.ts": "",
    }
    assert observed(sources)["metrics"]["web_unreachable_modules"]["value"] == 1


def test_web_workers_loaded_by_url_are_reachable():
    sources = {
        WEB + "main.tsx": "import './scheduler';",
        WEB + "scheduler.ts": "new Worker(new URL('./indicator.worker.ts', import.meta.url), { type: 'module' });",
        WEB + "indicator.worker.ts": "",
        WEB + "dead.ts": "",
    }
    assert observed(sources)["metrics"]["web_unreachable_modules"]["value"] == 1


def test_process_state_inventory_approval_requires_category_and_reason():
    sources = {APP + "platform/chat/a.py": "import threading\nlock = threading.Lock()\nother = threading.Lock()",
               "resources/architecture/process-local-state.json": json.dumps({"entries": [
                   {"path": APP + "platform/chat/a.py", "symbol": "lock", "category": "coordination",
                    "reason": "serializes the local writer"},
                   {"path": APP + "platform/chat/a.py", "symbol": "other", "category": "coordination"},
               ]})}
    assert observed(sources)["metrics"]["process_local_state_unapproved"]["value"] == 1


def test_stale_process_state_inventory_entries_fail_closed():
    sources = {APP + "platform/chat/a.py": "provider = None", "resources/architecture/process-local-state.json": json.dumps({"entries": [
        {"path": APP + "platform/chat/a.py", "symbol": "provider", "category": "coordination", "reason": "gone"},
    ]})}
    with pytest.raises(metrics.AnalysisError, match="stale process-state inventory entries"):
        observed(sources)


def test_mypy_reports_override_pattern_count_and_effective_matching_modules():
    sources = {
        "pyproject.toml": (
            "[[tool.mypy.overrides]]\n"
            'module = ["app.platform.chat.*", "app.missing.*"]\n'
            "ignore_errors = true\n"
            "[[tool.mypy.overrides]]\n"
            'module = ["app.platform.chat.strict"]\n'
            "ignore_errors = false\n"
        ),
        APP + "platform/chat/a.py": "",
        APP + "platform/chat/strict.py": "",
        APP + "platform/chat/c.py": "",
        APP + "jobs/a.py": "",
    }
    result = observed(sources)
    assert result["metrics"]["mypy_ignored_modules"]["value"] == 2
    assert result["evidence"]["mypy_ignored_modules"] == ["app.platform.chat.a", "app.platform.chat.c"]
    assert result["evidence"]["mypy_ignored_patterns"] == ["app.missing.*", "app.platform.chat.*"]
    assert result["evidence"]["mypy_strict_patterns"] == ["app.platform.chat.strict"]


def test_web_modules_imported_with_a_vite_query_are_reachable():
    sources = {
        WEB + "main.tsx": "import './player';",
        WEB + "player.ts": "import workletUrl from './pcm.worklet.ts?worker&url';",
        WEB + "pcm.worklet.ts": "registerProcessor('pcm', class {});",
    }
    assert observed(sources)["metrics"]["web_unreachable_modules"]["value"] == 0


def test_eslint_baseline_metric_includes_all_linted_web_files():
    sources = {
        WEB + "app/a.ts": "/* eslint-disable no-console -- baseline WP-9.x */\n",
        WEB + "features/a.test.ts": "/* eslint-disable no-restricted-imports -- baseline WP-9.x */\n",
        "web/tests/e2e/a.spec.ts": "/* eslint-disable prefer-const -- baseline WP-9.x */\n",
    }
    assert observed(sources)["metrics"]["eslint_baseline_disables"]["value"] == 3


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
               "src/vendor/a.py": "print('vendor')", WEB + "api/generated/core.ts": "window.fetch = x;",
               WEB + "features/trading/api/generated.ts": "window.fetch = x;", WEB + "features/trading/api/gateway.ts": "export {};"}
    for path, source in tracked.items():
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(source)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "--", *tracked], check=True, capture_output=True)
    (tmp_path / "src/app/untracked.py").write_text("print('untracked')")
    (tmp_path / "src/app/deleted.py").unlink()
    assert tracked_sources(tmp_path) == {"src/app/a.py": "print('tracked')", WEB + "features/trading/api/gateway.ts": "export {};"}


def test_reachability_reports_any_package_from_the_same_roots():
    # scripts/reachability_report.py (WP-8.6) reads this function for every package.
    sources = {
        APP + "composition/production.py": "import app.apps.story.live\nFEATURE = 'app.apps.trading.feature:FEATURE'",
        APP + "apps/story/live.py": "", APP + "apps/story/dead.py": "",
        APP + "apps/trading/feature.py": "from . import used", APP + "apps/trading/used.py": "",
        APP + "apps/trading/unused.py": "",
    }
    analysis = metrics.SourceAnalysis(sources, config)
    assert metrics.unreachable_python(analysis, "app.apps.") == [APP + "apps/story/dead.py", APP + "apps/trading/unused.py"]
    assert metrics.unreachable_python(analysis, "app.apps.story.") == [APP + "apps/story/dead.py"]
