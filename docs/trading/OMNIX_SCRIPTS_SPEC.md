# Omnix Scripts: supported subset and runtime (TVP-11.0)

Omnix Scripts is a TradingView-compatible subset of Pine Script (decision D-1), so users can paste existing indicator scripts. This document defines the subset the interpreter supports and records the TVP-11.0 spike results that confirm the runtime decision D-9.

- Code: `src/app/apps/trading/scripts`
- Tests:
  - `src/tests/trading/test_trading_scripts_interpreter.py`
  - `src/tests/trading/test_trading_scripts_corpus.py`
- Cost measurements: `scripts/omnix_scripts_benchmark.py`

## 1. Runtime (D-9)

Scripts run only on the server, in a Python interpreter.

1. **Parse.** `parse_script` reads Pine source into a syntax tree. The lexer applies Pine's indentation rules:
   - a block is indented by 4 spaces or a tab;
   - a line indented off that grid continues the previous line;
   - so does everything inside brackets.
2. **Compile.** `compile_script` turns the tree into a `Program` of Python closures and resolves every name at compile time. A program doesn't depend on any run, so it is compiled once per script version and reused for every symbol, user and input set.
3. **Run.** `ScriptRun` executes the program bar by bar over a `BarSeries`. `append_bar` runs only a newly closed bar, so a cached run is extended incrementally.
   - A script that reads the last bar (`barstate.islast`, `islastconfirmedhistory`, `isrealtime`, `last_bar_index`, `last_bar_time`) can't be extended: a bar that was last when it ran no longer is. For such a script `ScriptRun.can_extend` is false, and it runs again in full on new bars.
   - Every failure of a script is a `ScriptError` with a line: syntax, unsupported feature, runtime error (including any Python error inside a built-in), or limit. A run that raised is discarded, never extended. (Misusing the API, such as extending a run that can't be extended, raises `RuntimeError`.)

**Series model.**
- Every variable is a `Slot`: its value on the current bar plus its committed history. At the end of a bar each slot commits; a `var` keeps its value and the others reset to `na`.
- Each call site of a user function gets its own `Context`, as in Pine: its variables and its `ta.*` calls keep their own series.
  - A function's variables and parameters advance once per **call**, as Pine documents: `x[1]` in a function is its previous call's value, even when the function isn't called on every bar.
  - Its `ta.*` calls advance once per bar on which they run (they commit by bar index), so a function called twice on one bar from a loop recomputes that bar. This matches Pine for calls on different bars; Pine warns against `ta.*` calls in loops.
- Each `ta.*` call site keeps a `ta.Site`. The function is a pure `step(state, inputs) -> (state, output)` applied to the state committed at the end of the previous bar. Calling it again on the same bar (a loop, or later a realtime bar that updates) therefore recomputes that bar instead of advancing twice.

**One source of truth.** `ta.*` functions follow the server indicator registry's order of operations (TVP-0.2), so a script and the chart's indicator agree to within a few ulps:
- SMA keeps a running sum;
- EMA and RMA seed with the mean of the first `length` values;
- RSI and ATR smooth with `(avg * (n - 1) + x) / n`.

**Result cache key:** script hash, inputs, instrument, interval, last bar time and formula version. A cache miss on a run that already exists extends that run with the new bars when `can_extend`, and runs again in full otherwise.

## 2. Supported subset

### Versions and declaration

- `//@version=5` and `//@version=6`. Older versions, and a script without a `//@version` line (v1 in Pine), are refused.
- Division follows the version, per TradingView's v6 migration guide:
  - in v5, an int **literal** divided by an int literal is truncated toward zero (`7 / 2 == 3`); any other division keeps the fraction (`bar_index / 2` is 0.5 on bar 1). Known deviation: TradingView also truncates `const int` variables (`len = 10`, then `len / 4` is 2); Omnix gives 2.5 until constants are folded through declarations (TVP-11.1);
  - in v6, `/` always returns the fraction (`7 / 2 == 3.5`).
- `and` and `or` follow the version too: v5 evaluates both sides on every bar (a `ta.*` call on the right still advances), v6 evaluates them lazily.
- `indicator(...)` with constant arguments is required. Recorded: `title`, `shorttitle`, `overlay`, `format`, `precision`, `max_*_count` and the rest.
- `strategy(...)` (TVP-11.5) declares a strategy; see [Strategies](#strategies). `library()` is refused as unsupported.

### Syntax

- **Comments:** `//`.
- **Declarations:**
  - `x = ...`, `var x = ...`, `varip x = ...`;
  - typed declarations `float x = na` and `array<float> a = ...`;
  - types are parsed but not checked.
- **Reassignment:** `:=`, `+=`, `-=`, `*=`, `/=`, `%=`.
- **Tuples:** `[a, b] = f()`, and tuple returns `[x, y]`.
- **Conditionals:**
  - `if` / `else if` / `else` as a statement, or as an expression whose value is the branch's last value;
  - `switch` with a subject, or without one (conditions), with a default `=>` case.
- **Loops:**
  - `for i = a to b [by step]` (counts down when `b < a`); v6 checks the `to` bound again before each iteration, v5 reads it once;
  - `for x in array` and `for [i, x] in array`;
  - `while`, `break`, `continue`.
- **User functions:**
  - single-line or block form, at the top level;
  - arguments with defaults, and named arguments;
  - no recursion (a function is bound after its body).
- **Operators:** `?:`, `or`, `and`, `== !=`, `< > <= >=`, `+ -`, `* / %`, unary `- + not`.
- **History:** `expr[n]` on any expression.
  - On a variable or built-in series it reads that series.
  - On any other expression it reads that expression's own series: one value per bar at the top level (`na` on bars where the branch holding it didn't run), one per call inside a function.
- **Method syntax:** `arr.push(x)` and `lbl.set_text(...)` dispatch on the value's type at run time.
- **Generic constructors:** `array.new<float>(...)`, `map.new<string, float>()`.

### Values and `na`

- `na` propagates through arithmetic.
- A comparison involving `na` is false, except `!=` between `na` and a value.
- `nz`, `na()` and `fixnan` work as in Pine.
- Conditions treat `na`, `false` and `0` as false.
- `switch` on an `na` subject takes the default case: `na` equals nothing.
- Ints are 64-bit: arithmetic past that range is a runtime error. Arithmetic needs numbers (`"x" * 5` is an error); `+` also joins two strings.
- Division by zero gives `na`.

### Built-in variables

- **Bar series:** `open`, `high`, `low`, `close`, `volume`, `hl2`, `hlc3`, `ohlc4`, `hlcc4`, `time`, `time_close`, `bar_index`, `last_bar_index`, `last_bar_time`.
- **Bar state:** `barstate.*`, where historical bars are confirmed.
- **Calendar:** `year`, `month`, `weekofyear`, `dayofmonth`, `dayofweek`, `hour`, `minute`, `second`, all in UTC.
- **Timeframe:** `timeframe.period`, `multiplier`, and the `is*` flags.
- **Symbol:** `syminfo.tickerid`, `ticker`, `timezone`, and `mintick` (0.01 until instrument tick sizes reach the runtime).
- **`ta.*` series:** `ta.tr`, `ta.obv`, `ta.vwap`, `ta.accdist`.
- **Constants:**
  - `math.pi`, `math.e`, `math.phi`, `math.rphi`;
  - `color.*`, with TradingView's palette;
  - named constants such as `shape.*`, `location.*`, `size.*`, `plot.style_*`, `line.style_*`, `label.style_*`, `extend.*`, `position.*`, `display.*`, `format.*`, `xloc.*`, `yloc.*`, `text.*`, `hline.style_*`, `dayofweek.*`.

### Functions

**`ta.*`**

| Group | Functions |
|---|---|
| Averages | `sma`, `ema`, `rma`, `wma`, `hma`, `vwma` |
| Momentum | `rsi`, `macd`, `stoch`, `cci`, `mfi`, `dmi`, `mom`, `change`, `roc` |
| Volatility and bands | `atr`, `tr()`, `stdev`, `variance`, `dev`, `bb`, `bbw`, `kc` |
| Ranges | `highest`, `lowest`, `highestbars`, `lowestbars` (each with or without a source) |
| Pivots | `pivothigh`, `pivotlow` (each with or without a source) |
| Crosses | `crossover`, `crossunder`, `cross` |
| Trend | `supertrend`, `sar` |
| Statistics | `linreg`, `correlation`, `median`, `percentrank`, `rising`, `falling` |
| Events | `barssince`, `valuewhen` |
| Volume | `cum`, `vwap(source[, anchor])` |

**Other namespaces**

| Namespace | Functions |
|---|---|
| `math` | `abs`, `sqrt`, `log`, `log10`, `exp`, `pow`, `floor`, `ceil`, `round(x[, precision])`, `round_to_mintick`, `sign`, trigonometry, `max`/`min`/`avg` (any number of values), `sum` |
| conversions | `nz`, `na`, `fixnan`, `int`, `float`, `bool` |
| `color` | `new`, `rgb`, `from_gradient`, `r`, `g`, `b`, `t` |
| `str` | `tostring` (incl. `#.##` patterns), `format` (`{0}`, `{0,number,#.##}`), `length`, `contains`, `startswith`, `endswith`, `pos`, `upper`, `lower`, `trim`, `substring`, `replace`, `replace_all`, `split`, `tonumber`, `repeat` |
| `array` | `new*`, `from`, `push`, `pop`, `shift`, `unshift`, `get`/`set` (negative indexes), `insert`, `remove`, `size`, `clear`, `sum`, `avg`, `max`, `min`, `stdev`, `median`, `includes`, `indexof`, `lastindexof`, `first`, `last`, `copy`, `reverse`, `sort`, `slice`, `fill`, `concat`, `join` |
| `map` | `new`, `put`, `get`, `contains`, `remove`, `size`, `keys`, `values`, `clear` |
| `input` | `input`, `input.int`, `float`, `bool`, `string` (with `options`), `color`, `source`, `timeframe`, `symbol`, `session`, `price`, `time`, `text_area` |
| time | `timeframe.change("D" / "W" / "M")`, `year(t)` and the other calendar functions |
| errors and logs | `runtime.error`; `log.info`/`warning`/`error`, which are accepted and ignored until the console in TVP-11.2 |

**Inputs.** `input.*` declarations are listed in `ScriptResult.inputs` with their type, default and options. A run's inputs override them by title.

**Outputs.**
- `plot`, `plotshape`, `plotchar`, `plotarrow`, `plotcandle`, `plotbar`, `bgcolor`, `barcolor`, `alertcondition`.
  - These are top level only, at most 64 per script.
  - Each records one value per bar.
  - Constant options are kept once; series options (a color that changes) are kept per bar.
- `hline` and `fill`: drawn once.
- `alert()`.

**Drawings.**
- `label.*`, `line.*`, `box.*`, `table.*` and `linefill.new`: `new`, `set_*`, `get_*`, `delete`.
- When a script exceeds its `max_*_count` (Pine's default is 50), the oldest drawings are removed, as in Pine.

### Semantics to note

- **A `ta.*` call inside a branch** advances only on the bars where the branch runs, as in Pine.
- **Warm-up:**
  - leading `na` inputs are skipped, so a `ta.*` of a `ta.*` warms up like the chart's indicators;
  - a window containing `na` is `na` until that value has passed.
- **`ta.vwap`** restarts at each UTC day. Exchange session calendars (US equities' regular session) arrive in TVP-11.1, with `syminfo.session`.
- **`ta.stoch`** is `na` on a flat window, because Pine divides by a zero range. The chart's Stochastic RSI shows 50 there. This is the one known difference between a template and its chart indicator.
- **`ta.pivothigh`:** the pivot bar must be strictly above the bars before it and at least as high as the bars after it. On a plateau, the first bar is the pivot. `ta.pivotlow` mirrors this. To be checked against TradingView in TVP-11.1.
- **Lengths:** `na` gives `na`; a length that isn't a positive whole number is a runtime error, as in Pine.
- **`ta.sar`**, **`ta.supertrend`**, **`ta.dmi`** (with `fixnan`), **`ta.wma`**, **`ta.cci`**, **`ta.dev`**, **`ta.vwma`**, **`ta.mfi`**, **`ta.obv`** and **`ta.stoch`** are checked against TradingView's documented reference implementations (`pine_sar` and the like), run through the interpreter itself (`test_trading_scripts_safety.py`).
- **`time_close`** is the bar's start plus the interval (the run's timeframe); `na` without a fixed interval (months, or no timeframe given).
- **Known deviation:** inputs to `ta.*` that are `na` in the middle of a series are not yet tested against TradingView; no golden dataset has gaps of `na`.

### Not supported yet

| Feature | Arrives with |
|---|---|
| `request.*` (`request.security` and other symbols/timeframes) | TVP-11.1, within the request budget |
| `strategy.risk.*`, `strategy.margin_liquidation_price`, margin calls, intrabar (bar magnifier) fills | Later |
| `import`/`export` libraries, user-defined types, methods, enums | Later; refused with a reason |
| `matrix.*`, `polyline.*`, `chart.point` | Later |
| `indicator(timeframe=...)` | TVP-11.1 |
| Realtime-bar semantics: `varip`, rollback of an unconfirmed bar | TVP-11.1. Runs are on closed bars, and `varip` behaves like `var` there, as in Pine's history. A script that reads the last bar runs again in full instead of being extended. |
| Type checking (declared types are parsed, not enforced) | TVP-11.1 |
| `ta.alma`, `ta.swma`, `ta.wpr`, `ta.cog`, `ta.tsi`, `ta.kcw` and other rarely used functions | TVP-11.1 |

Unsupported names are refused at compile time with "not supported yet" and the line. Unknown names are reported as unknown.

### Strategies

`strategy()` scripts (TVP-11.5) trade a simulated account on the bars they run on (`scripts/strategy.py`). They are a
research backtest only: nothing reaches an order gateway, a paper account or a broker.

- **Declaration:** `initial_capital`, `pyramiding`, `default_qty_type` (`strategy.fixed`, `strategy.cash`,
  `strategy.percent_of_equity`), `default_qty_value`, `commission_type` (`strategy.commission.percent`, `cash_per_contract`,
  `cash_per_order`), `commission_value`, `slippage` (ticks), `process_orders_on_close`, `risk_free_rate`. `overlay` defaults
  to true. Other arguments are accepted and recorded.
- **Orders:** `strategy.entry` (reverses an opposite position; `pyramiding` limits entries in one direction, 0 meaning one),
  `strategy.order` (buys or sells; closes first in, first out), `strategy.exit` (per matching trade: `profit`/`limit`,
  `loss`/`stop`, trailing with `trail_price` or `trail_points` and `trail_offset`; `qty`, `qty_percent`), `strategy.close`,
  `strategy.close_all` (with `immediately`), `strategy.cancel`, `strategy.cancel_all`; `limit` and `stop` (and both: a
  stop-limit); OCA groups with `strategy.oca.cancel` and `strategy.oca.reduce`.
- **Fills, like TradingView's broker emulator:** the script runs at a bar's close, and its orders fill from the next bar
  on. Within a bar, price moves open, then the extreme nearer the open, then the other, then close. Market orders fill
  at the open; limits at their price, or the open when it is better; stops at their price, or the open when it gapped
  past. Slippage worsens market and stop fills. `process_orders_on_close` fills market orders at the bar's close.
  Ticks are 0.01 (`syminfo.mintick`).
- **What the script reads:** `strategy.position_size`, `position_avg_price`, `position_entry_name`, `equity`, `netprofit`,
  `openprofit`, `grossprofit`, `grossloss`, `closedtrades`, `opentrades`, `wintrades`, `losstrades`, `eventrades`,
  `initial_capital`, `max_drawdown`, `max_runup`, and `strategy.closedtrades.*(i)` / `strategy.opentrades.*(i)` (profit, prices,
  bar indexes, times, size, ids, commission, run-up, drawdown, comments).
- **Report** (the run's `strategy`): every closed trade (the newest 5,000 listed), open trades, fills, equity, drawdown
  and buy and hold per bar, and a performance summary for all, long and short trades (net profit, profit factor, percent
  profitable, averages, largest trades, bars in trades, max drawdown and run-up, commission, Sharpe and Sortino from
  monthly returns).
- **Deep backtest:** `POST /api/trading/scripts/backtest` runs a strategy on up to 20,000 of the latest bars the provider
  serves, with 30 s instead of 5 s.

### Limits (`ScriptLimits`)

| Limit | Value |
|---|---|
| Bars per run | 20,000 |
| Loop iterations per run | 5,000,000 |
| Loop iterations per bar | 100,000 |
| Wall time per run | 20 s, checked after every bar and every 256 loop iterations; to be lowered per user (§4) |
| Drawings of each kind | 500 |
| Plots per script | 64 |
| One string's length | 40,000 characters, checked before a string is built (`str.repeat`, `replace_all`) or while it is built (`str.format`, `join`, `str.tostring` of an array), and on `+` and `replace` |
| One array's or map's size | 100,000, checked by every function that grows one |
| Array and map values created per run | 10,000,000 |
| Alerts kept per run | 1,000 (the newest) |
| Expression nesting | 64 levels of brackets or unary operators, 256 operators in one chain |
| Input values | checked against the declared type, options and range; unknown titles are refused |

Scripts have no file, network or OS access: the interpreter only exposes the functions above. These caps bound each value, not a run's total memory (a 40,000-character string kept in a series over 20,000 bars is about 800 MB): total memory is bounded only by the worker process's limit (§4). These checks are in-process: they can't interrupt a single long built-in operation (sorting a 100,000-value array), so production runs need a separate process with CPU and memory limits (§4).

## 3. Spike results (TVP-11.0, 2026-10-09)

### Template corpus: every Pine template against its chart indicator

`indicatorPineCorpus.test.ts` exports each indicator's "view as Pine" source, with the chart's default inputs, to `pineTemplateCorpus.json`. `test_trading_scripts_corpus.py` runs each template on the 8 indicator golden datasets, including empty, constant, gaps and negative prices.

**Compared with the native registry indicator, all within 1e-11 relative:**
- SMA, EMA, RSI, ATR, MACD, Bollinger Bands, IDEAL BB, VWAP (per day);
- Golden and Death Cross (lines and cross markers), EMA Stack;
- Log MACD (against MACD on log prices), Stochastic RSI (except flat windows, above);
- RSI Divergence's RSI.

**Compared with a brute-force reference:**
- MACD DEMA;
- RSI Divergence pivots;
- Swing Liquidity pivots;
- Fair Value Gap boxes.

**Not runnable, and refused with a reason:**
- Bull Market Support Band uses `request.security`.
- Volume Profile's template is not valid Pine (`volume.profile_fixed` doesn't exist).

**Two bugs found and fixed:**
- The Stochastic RSI template hard-coded its stochastic length and smoothing (14, 3, 3). The chart uses the instance's period and smoothing, so the template now uses those inputs.
- A drawing cap read the wrong declaration key.

### Community-idiom corpus: 18 of 20 run unchanged

`resources/trading/script_corpus/idioms` holds 20 scripts written for Omnix in the idioms of popular community indicators, among them:
- Supertrend (built-in and manual), Squeeze Momentum, RSI with MA type and a dashboard table;
- MACD with a coloured histogram, Ichimoku, Pivot labels, session VWAP with bands;
- Hull (with v5 integer lengths), DMI, Chandelier Exit, Williams %R, ATR trailing stop;
- Keltner, OBV oscillator with CCI, Heikin Ashi with SAR, ZigZag with arrays and lines.

Eighteen run (the EMA-cross strategy since TVP-11.5); the two that fail use features outside the subset on purpose: `request.security` and a user-defined type. Cross-checks in the tests:
- The session VWAP computed by hand equals `ta.vwap`.
- A hand-written Hull MA equals `ta.hma`.

*Caveat:* these are idiom reproductions, not copies of published community scripts. Running the actual top-20 published scripts needs an owner-approved list, because their licences (mostly MPL-2.0) must be checked before their source is added to the repository. The acceptance figure (15 of 20) should be re-measured on that list.

### Cost

Measured with `scripts/omnix_scripts_benchmark.py`: 5,000 hourly bars, one CPU core, CPython 3.11.

| Measure | Median | Max |
|---|---|---|
| Full run, 34 runnable scripts | 52 ms | 313 ms (ZigZag with arrays and lines) |
| Incremental, per new bar (32 scripts that can be extended) | 0.017 ms | 0.073 ms |
| Compile | about 1 ms | 7 ms |

The two scripts that read the last bar (RSI with a dashboard table, ZigZag) run again in full on each new bar: 74 ms and 313 ms. TVP-11.1 follow-up: Pine's realtime model, keeping the state before the last bar and re-running only from there, makes them incremental too.

**Memory retained by a 5,000-bar run:** 0.6–6.5 MB. Every slot keeps its full history.

**TVP-11.1 follow-up:** keep history only for the variables and expressions a script reads with `[n]`, up to the deepest offset it uses. This is known at compile time for constant offsets, and is Pine's `max_bars_back` model. It cuts retained memory by most of that figure.

**Result cache:** simulated with 10 popular scripts on 5 symbols; each user opens one script on one symbol, then 30 new bars close and every open chart asks for the result at each bar (requests = users × 31).

| Users | Hit rate | Runs kept | Compute |
|---|---|---|---|
| 10 | 10% | 9 | 0.3 s total |
| 100 | 56% | 44 | 1.3 s total |

- Identical charts share one computation per bar.
- New bars extend the cached runs incrementally, about 0.02 ms each (scripts that read the last bar run again in full).
- Compute time is dominated by first loads.

## 4. Decision D-9: confirmed

A server-side Python interpreter fits the budget:
- a typical script costs about 50 ms per 5,000 bars once, then microseconds per new bar;
- one cached run serves every chart showing the same script, inputs and symbol.

**Conditions for TVP-11.1:**
1. **Per-user limits:** a CPU budget per run (proposed 2 s for 20,000 bars) and a cap on concurrent runs per user.
2. **Memory:** history only for referenced series (above), and the cache bounded by memory as well as by entries.
3. **Execution:** runs in a separate worker process with CPU-time and memory limits (`RLIMIT_CPU`/`RLIMIT_AS` or a container), killed when it overruns. A thread is not enough: under the GIL a runaway script would starve the server, and a thread can't be killed. A `ScriptRun` is mutable and owned by one worker; the cache shares immutable results, not runs.
4. **Stale runs:** a run is reset when its bars change (an edited or backfilled bar), never patched.
