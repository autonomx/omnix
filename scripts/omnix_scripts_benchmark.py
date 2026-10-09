"""Omnix Scripts cost measurements (TVP-11.0).

Runs every runnable template and idiom script on 5,000 synthetic hourly bars and prints, per script:
compile time, full-run time, incremental time per new bar and the retained memory of a run. Then simulates
several users loading the same scripts on the same symbols through a result cache keyed by
(script hash, inputs, instrument, interval, last bar, formula version).

    PYTHONPATH=src python scripts/omnix_scripts_benchmark.py
"""

from __future__ import annotations

import hashlib
import json
import random
import statistics
import sys
import time
import tracemalloc
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from app.apps.trading.indicators.registry import FORMULA_VERSION, BarSeries
from app.apps.trading.scripts import ScriptError, ScriptLimits, ScriptRun, compile_script

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "web" / "src" / "features" / "trading" / "indicators" / "fixtures" / "pineTemplateCorpus.json"
IDIOMS = ROOT / "resources" / "trading" / "script_corpus" / "idioms"
BARS = 5_000
APPENDED = 50


def synthetic_bars(count: int, seed: int) -> BarSeries:
    rng = random.Random(seed)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    price = 100.0
    opens, highs, lows, closes, volumes = [], [], [], [], []
    for _ in range(count):
        opened = price
        price = max(1.0, price * (1 + rng.gauss(0, 0.01)))
        opens.append(opened)
        highs.append(max(opened, price) * (1 + abs(rng.gauss(0, 0.003))))
        lows.append(min(opened, price) * (1 - abs(rng.gauss(0, 0.003))))
        closes.append(price)
        volumes.append(float(rng.randint(500, 5_000)))
    return BarSeries(tuple(start + timedelta(hours=index) for index in range(count)), tuple(opens), tuple(highs), tuple(lows), tuple(closes), tuple(volumes))


def scripts() -> dict[str, str]:
    found = {f"template:{entry['id']}": entry["source"] for entry in json.loads(CORPUS.read_text(encoding="utf-8"))["entries"]}
    found.update({f"idiom:{path.stem}": path.read_text(encoding="utf-8") for path in sorted(IDIOMS.glob("*.pine"))})
    return found


def slice_bars(bars: BarSeries, end: int) -> BarSeries:
    return BarSeries(*(field[:end] for field in (bars.start_times, bars.open, bars.high, bars.low, bars.close, bars.volume)))


def bar_at(bars: BarSeries, index: int) -> SimpleNamespace:
    return SimpleNamespace(
        start_time=bars.start_times[index], open=bars.open[index], high=bars.high[index], low=bars.low[index],
        close=bars.close[index], volume=bars.volume[index],
    )


def measure(name: str, source: str, bars: BarSeries) -> dict[str, float] | None:
    began = time.perf_counter()
    try:
        program = compile_script(source)
    except ScriptError:
        return None
    compiled = time.perf_counter() - began
    limits = ScriptLimits()
    run = ScriptRun(program, bars, {}, limits, "SYNTH", "60")
    began = time.perf_counter()
    run.run_all()
    full = time.perf_counter() - began
    # Incremental: a run on all but the last APPENDED bars, then those bars one at a time.
    tracemalloc.start()
    partial = ScriptRun(program, slice_bars(bars, BARS - APPENDED), {}, limits, "SYNTH", "60")
    partial.run_all()
    _, peak = tracemalloc.get_traced_memory()
    retained, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    timings = []
    for index in range(BARS - APPENDED, BARS):
        began = time.perf_counter()
        partial.append_bar(bar_at(bars, index))
        timings.append(time.perf_counter() - began)
    return {"compile_ms": compiled * 1000, "full_ms": full * 1000, "bar_ms": statistics.median(timings) * 1000, "retained_kb": retained / 1024, "peak_kb": peak / 1024}


def cache_simulation(sources: dict[str, str], users: int, symbols: int, minutes: int) -> dict[str, float]:
    """Users open one of the popular scripts on one of a few symbols; each minute a new bar closes on every symbol
    and every open chart asks for the script's result at that bar."""
    rng = random.Random(7)
    popular = list(sources.items())[:10]
    datasets = [synthetic_bars(BARS + minutes, seed) for seed in range(symbols)]
    charts = [(rng.randrange(len(popular)), rng.randrange(symbols)) for _ in range(users)]
    cache: OrderedDict[tuple[str, str, int, str, str, str], ScriptRun] = OrderedDict()
    runs: dict[tuple[str, int], ScriptRun] = {}
    requests = hits = 0
    compute = 0.0
    for minute in range(minutes + 1):
        last = BARS + minute
        for script_index, symbol in charts:
            name, source = popular[script_index]
            key = (hashlib.sha256(source.encode()).hexdigest(), "{}", symbol, "60", str(last), FORMULA_VERSION)
            requests += 1
            if key in cache:
                hits += 1
                cache.move_to_end(key)
                continue
            began = time.perf_counter()
            state = runs.get((name, symbol))
            if state is None:
                state = ScriptRun(compile_script(source), slice_bars(datasets[symbol], last), {}, ScriptLimits(), str(symbol), "60")
                state.run_all()
                runs[(name, symbol)] = state
            else:
                # New bars extend the cached run incrementally.
                while len(state) < last:
                    state.append_bar(bar_at(datasets[symbol], len(state)))
            compute += time.perf_counter() - began
            cache[key] = state
            while len(cache) > 1_000:
                cache.popitem(last=False)
    return {"requests": requests, "hit_rate": hits / requests, "compute_s": compute, "distinct_runs": len(runs)}


def main() -> None:
    bars = synthetic_bars(BARS, 1)
    sources = scripts()
    rows = []
    for name, source in sources.items():
        measured = measure(name, source, bars)
        if measured is None:
            print(f"{name:34} not runnable")
            continue
        rows.append((name, measured))
        print(
            f"{name:34} compile {measured['compile_ms']:6.1f} ms  full {measured['full_ms']:7.1f} ms  "
            f"new bar {measured['bar_ms']:6.3f} ms  retained {measured['retained_kb']:8.0f} KB"
        )
    fulls = [row[1]["full_ms"] for row in rows]
    per_bar = [row[1]["bar_ms"] for row in rows]
    print(f"\n{len(rows)} scripts on {BARS} bars: full run median {statistics.median(fulls):.0f} ms, max {max(fulls):.0f} ms; "
          f"new bar median {statistics.median(per_bar):.3f} ms, max {max(per_bar):.3f} ms")
    runnable = {name: sources[name] for name, _ in rows}
    for users in (10, 100):
        result = cache_simulation(runnable, users=users, symbols=5, minutes=30 if "--quick" not in sys.argv else 5)
        print(f"cache, {users} users / 5 symbols / 10 scripts: {result['requests']} requests, hit rate {result['hit_rate']:.1%}, "
              f"{result['distinct_runs']} runs kept, compute {result['compute_s']:.1f} s")


if __name__ == "__main__":
    main()
