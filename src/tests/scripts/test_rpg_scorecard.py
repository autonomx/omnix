"""RQ-0.1: the RPG scorecard's counting rules, on small synthetic sources."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("omnix_rpg_scorecard_tests_target", SCRIPTS / "rpg_scorecard.py")
scorecard = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(scorecard)
CONFIG = scorecard.load_layers(SCRIPTS.parent / "resources/architecture/layers.toml")
RPG = "src/app/apps/rpg/"


def measured(sources, config=None):
    return scorecard.measure(sources, CONFIG if config is None else config)["metrics"]


def test_state_reads_count_occurrences_and_distinct_keys_per_section():
    source = (
        "a = session.simulation_state['time']\n"
        "b = simulation_state.get('time', {})\n"
        "c = self.runtime_state['narration_artifacts']\n"
        "simulation_state['written'] = 1\n"          # a write, not a read
        "d = simulation_state[key]\n"                # not a literal key
        "e = other_state.get('time')\n"              # not a state section
    )
    reads = measured({RPG + "session/a.py": source})["state_string_key_reads"]
    assert reads["simulation_state"] == {"occurrences": 2, "distinct_keys": 1, "keys": {"time": 2}}
    assert reads["runtime_state"]["occurrences"] == 1
    assert reads["occurrences"] == 3
    assert reads["turn_path"].startswith("unavailable")


def test_turn_path_counts_only_listed_modules():
    config = {**CONFIG, "rpg_turn_path": {"modules": ["app.apps.rpg.session.a", RPG + "session/c.py"]}}
    sources = {
        RPG + "session/a.py": "x = simulation_state['time']",
        RPG + "session/b.py": "x = simulation_state['time']",
        RPG + "session/c.py": "import random\nx = runtime_state.get('k')\nrandom.random()",
    }
    metrics = measured(sources, config)
    assert metrics["state_string_key_reads"]["occurrences"] == 3
    assert metrics["state_string_key_reads"]["turn_path"]["occurrences"] == 2
    assert metrics["nondeterminism"]["turn_path"] == 1


def test_save_sites_exclude_definitions_and_tests():
    sources = {
        RPG + "session/a.py": "def save_session(s):\n    pass\nstore.save_session(s)\nsave_runtime_session(s)",
        RPG + "session/b.py": "repo.save_runtime_session(s)",
        "src/tests/unit/rpg/test_a.py": "save_session(s)",
    }
    saves = measured(sources)["save_call_sites"]
    assert (saves["call_sites"], saves["modules"]) == (3, 2)


def test_dict_any_deepcopy_and_broad_excepts():
    source = (
        "from copy import deepcopy\nimport copy\n"
        "a: dict[str, Any] = {}\nb: 'Dict[ str , Any ]'\nc: dict[str, int]\n"
        "deepcopy(a)\ncopy.deepcopy(a)\ndef deepcopy_like():\n    pass\n"
        "try:\n    x()\nexcept Exception:\n    raise\n"
        "try:\n    x()\nexcept (KeyError, Exception):\n    raise\n"
        "try:\n    x()\nexcept:\n    raise\n"
        "try:\n    x()\nexcept ValueError:\n    raise\n"
    )
    metrics = measured({RPG + "rules/a.py": source})
    assert metrics["dict_str_any"]["occurrences"] == 2
    assert metrics["dict_str_any"]["by_spelling"] == {"Dict": 1, "dict": 1}
    assert metrics["deepcopy_calls"]["occurrences"] == 2
    assert metrics["broad_excepts"] == {"occurrences": 3, "by_context": {"rules": 3}}


def test_world_names_are_word_bounded_and_skip_fixtures_and_other_contexts():
    sources = {
        RPG + "rules/a.py": "A = 'npc:Bran'\nB = 'npc_bran'\nC = 'Brandon and Mirabel'\nD = 'the rusty_flagon'\nE = 'demo_glimmerdeep_pass'",
        RPG + "world/map_fixtures.py": "A = 'Bran'",
        RPG + "genesis/a.py": "A = 'Elara of the Old Mill'",
    }
    names = measured(sources)["world_specific_names"]
    assert names["hits"] == 4
    assert names["by_name"]["Bran"] == {"hits": 2, "files": 1}
    assert names["file_list"] == [RPG + "rules/a.py"]
    assert names["whole_package"]["hits"] == 7


def test_word_lists_are_module_level_constants_by_context():
    sources = {
        RPG + "rules/a.py": "STOP_WORDS = {'a'}\n_TRADE_VERBS: tuple = ('buy',)\nPASSWORDS = 1\ndef f():\n    LOCAL_WORDS = 1\nwords = 2",
        RPG + "genesis/b.py": "THEME_TERMS = ()",
    }
    lists = measured(sources)["word_list_constants"]
    # PASSWORDS ends in WORDS: the pattern is the stated suffix, not a dictionary.
    assert lists["constants"] == 4
    assert lists["by_context"] == {"genesis": 1, "rules": 3}
    assert lists["in_session_rules_world_narration"] == 3


def test_nondeterminism_resolves_imports_and_ignores_seeded_and_local_names():
    source = (
        "import random\nfrom uuid import uuid4\nimport time\nfrom datetime import datetime\nimport datetime as dt\n"
        "random.choice([1])\nrandom.Random()\nrandom.Random(7)\nrandom.Random(seed=1)\n"
        "uuid4()\ntime.time()\ntime.perf_counter()\ndatetime.now()\ndt.datetime.utcnow()\n"
        "def f(rng):\n    rng.random()\n"
    )
    other = "def f(random):\n    return random.choice([1])"
    found = measured({RPG + "world/a.py": source, RPG + "world/b.py": other})["nondeterminism"]
    assert found["by_kind"] == {
        "datetime.now": 1, "datetime.utcnow": 1, "random.Random()": 1, "random.choice": 1,
        "time.time": 1, "uuid.uuid4": 1,
    }


def test_contract_bypass_counts_distinct_cross_context_pairs():
    sources = {
        RPG + "session/a.py": (
            "from app.apps.rpg.world.contracts import Port\n"
            "from app.apps.rpg.world.contracts.ports import Other\n"
            "from app.apps.rpg.world.graph import thing\n"
            "from app.apps.rpg.world import graph\n"
            "def lazy():\n    import app.apps.rpg.rules.dice\n"
            "from . import b\n"
        ),
        RPG + "session/b.py": "", RPG + "world/contracts/__init__.py": "", RPG + "world/contracts/ports.py": "",
        RPG + "world/graph.py": "", RPG + "rules/dice.py": "",
    }
    bypass = measured(sources)["contract_bypass_imports"]
    assert bypass == {"pairs": 2, "by_context_pair": {"session->rules": 1, "session->world": 1}}


def test_file_size_limits_and_web_exclusions():
    sources = {
        RPG + "session/a.py": "pass\n" * 1201,
        RPG + "session/b.py": "pass\n" * 1200,
        "web/src/features/rpg/Big.tsx": "x;\n" * 601,
        "web/src/features/rpg/Big.test.tsx": "x;\n" * 900,
        "web/src/features/rpg/api/generated.ts": "x;\n" * 900,
        "web/src/features/trading/Big.tsx": "x;\n" * 900,
    }
    metrics = measured(sources)
    assert metrics["python_files_over_1200_lines"]["list"] == [RPG + "session/a.py:1201"]
    assert metrics["web_files_over_600_lines"]["list"] == ["web/src/features/rpg/Big.tsx:601"]


def test_every_metric_publishes_its_pattern_and_every_ratchet_has_a_metric():
    report = scorecard.measure({}, CONFIG)
    assert set(report["patterns"]) == set(report["metrics"])
    assert set(report["ratchets"]) == set(scorecard.RATCHETS)
    assert {key for key, _ in scorecard.RATCHETS.values()} == set(report["metrics"])
    assert all(value == 0 for value in report["ratchets"].values())
