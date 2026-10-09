"""Compiles a script into closures and runs it bar by bar.

Series semantics: every variable is a series. A ``Slot`` holds a variable's value on the current bar and its
committed history; at the end of each bar every slot commits (a ``var`` keeps its value, others reset to ``na``).
A user function's variables and ``ta.*`` calls live in a ``Context`` per call site (Pine gives each call of a function
its own series), and so does the history buffer of any ``expr[n]``.

A compiled ``Program`` doesn't depend on a run: compile once (per script and version) and run it on any bars with
any inputs. A ``ScriptRun`` can then take new bars one at a time (``append_bar``), which only runs the new bar.
"""

from __future__ import annotations

import contextvars
import copy
import math
import time as clock
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..indicators.registry import BarSeries
from .errors import ScriptError, ScriptLimitError, ScriptRuntimeError, ScriptSyntaxError, ScriptUnsupportedError
from .parser import parse_script
from .syntax import (
    Assign,
    Binary,
    Block,
    Break,
    Call,
    ColorLiteral,
    Continue,
    Declare,
    For,
    ForIn,
    FunctionDef,
    History,
    If,
    Literal,
    MethodCall,
    Name,
    Node,
    Script,
    Switch,
    Ternary,
    TupleDeclare,
    TupleExpr,
    Unary,
    While,
)

Closure = Callable[["Context"], Any]


@dataclass(frozen=True)
class ScriptLimits:
    max_bars: int = 20_000
    # Loop iterations over the whole run, and per bar.
    max_loop_iterations: int = 5_000_000
    max_loop_iterations_per_bar: int = 100_000
    max_seconds: float = 20.0
    # Per kind (labels, lines, boxes); a script's own max_*_count is capped by it.
    max_drawings: int = 500
    max_plots: int = 64
    # Values: one string's length, one array's or map's size, and the array items a run may allocate in all.
    max_string_length: int = 40_000
    max_collection_size: int = 100_000
    max_allocated_items: int = 10_000_000
    max_alerts: int = 1_000


# Pine's ints are 64-bit; Python's grow without bound, so arithmetic past this is an error.
INT_LIMIT = 2**63 - 1

# The run on this thread, for built-ins that count allocations against its limits.
CURRENT_RUN: contextvars.ContextVar[ScriptRun | None] = contextvars.ContextVar("omnix_script_run", default=None)


def current_limits() -> ScriptLimits:
    run = CURRENT_RUN.get()
    return run.limits if run is not None else ScriptLimits()


def check_string(value: str) -> str:
    limit = current_limits().max_string_length
    if len(value) > limit:
        raise ScriptLimitError(f"a string holds at most {limit} characters")
    return value


def allocate(items: int, size_after: int = 0) -> None:
    """Counts `items` new array or map entries against the run's budget, and the collection's size after the change."""
    run = CURRENT_RUN.get()
    limits = run.limits if run is not None else ScriptLimits()
    if size_after > limits.max_collection_size:
        raise ScriptLimitError(f"an array or map holds at most {limits.max_collection_size} values")
    if run is not None:
        run.allocated += max(0, items)
        if run.allocated > limits.max_allocated_items:
            raise ScriptLimitError(f"the script created more than {limits.max_allocated_items} array values")


# Runtime state


class Slot:
    __slots__ = ("current", "history", "persistent", "initialized")

    def __init__(self, persistent: bool) -> None:
        self.current: Any = None
        self.history: list[Any] = []
        self.persistent = persistent
        self.initialized = False

    def at(self, offset: int) -> Any:
        if offset == 0:
            return self.current
        history = self.history
        return history[-offset] if 0 < offset <= len(history) else None


class Context:
    """The script's own series (the root), or one call site of a user function. The root's series advance once
    per bar; a function's advance once per call, as Pine's do (`x[1]` in a function is its previous call's value)."""

    __slots__ = ("run", "root", "slots", "sites", "children", "calls")

    def __init__(self, run: ScriptRun, root: Context | None) -> None:
        self.run = run
        self.root = root or self
        self.slots: dict[int, Slot] = {}
        self.sites: dict[int, Any] = {}
        self.children: dict[int, Context] = {}
        # Calls committed so far (function call sites only).
        self.calls = 0

    def slot(self, key: int, persistent: bool) -> Slot:
        slot = self.slots.get(key)
        if slot is None:
            slot = self.slots[key] = Slot(persistent)
            # Back-fill: a variable first set on a later bar (or call) was na before.
            if self.root is self:
                slot.history = [None] * self.run.committed
                self.run.all_slots.append(slot)
            else:
                slot.history = [None] * self.calls
        return slot

    def commit_call(self) -> None:
        """Ends one call of a function: its series move on, as the root's do at the end of a bar."""
        for slot in self.slots.values():
            slot.history.append(slot.current)
            if not slot.persistent:
                slot.current = None
        self.calls += 1

    def child(self, key: int) -> Context:
        child = self.children.get(key)
        if child is None:
            child = self.children[key] = Context(self.run, self.root)
        return child


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


# Outputs


@dataclass
class PlotOutput:
    index: int
    kind: str  # plot, plotshape, plotchar, plotarrow, plotcandle, plotbar, bgcolor, barcolor, alertcondition
    title: str
    options: dict[str, Any]
    values: list[Any] = field(default_factory=list)
    colors: list[Any] | None = None


@dataclass
class Drawing:
    kind: str  # label, line, box, table
    id: int
    fields: dict[str, Any]
    deleted: bool = False


@dataclass
class ScriptInput:
    title: str
    type: str
    default: Any
    options: dict[str, Any]


@dataclass
class ScriptResult:
    declaration: dict[str, Any]
    inputs: list[ScriptInput]
    plots: list[PlotOutput]
    hlines: list[dict[str, Any]]
    fills: list[dict[str, Any]]
    drawings: list[Drawing]
    alerts: list[dict[str, Any]]
    bars: int
    seconds: float


# The program


@dataclass
class _Binding:
    kind: str  # "slot", "function"
    key: int = 0
    persistent: bool = False
    is_global: bool = True
    function: _Function | None = None


@dataclass
class _Function:
    name: str
    params: list[tuple[str, int, Closure | None]]  # name, slot key, default (compiled in the definition's scope)
    body: Closure | None = None


class _Scope:
    def __init__(self, parent: _Scope | None, in_function: bool) -> None:
        self.parent = parent
        self.in_function = in_function
        self.names: dict[str, _Binding] = {}

    def lookup(self, name: str) -> _Binding | None:
        scope: _Scope | None = self
        while scope is not None:
            binding = scope.names.get(name)
            if binding is not None:
                return binding
            scope = scope.parent
        return None


@dataclass
class Program:
    script: Script
    body: list[Closure]
    declaration: dict[str, Any]
    inputs: list[ScriptInput]
    plot_specs: list[tuple[str, str, dict[str, Any]]]  # kind, title, static options
    uses_drawings: bool
    # The line of each top-level statement in `body`, for runtime errors.
    lines: list[int] = field(default_factory=list)
    # Reads the last bar (barstate.islast, last_bar_index, ...): a run can't be extended bar by bar, since bars that
    # were last when they ran no longer are; such a script runs again in full on new bars.
    uses_last_bar: bool = False


def compile_script(source: str | Script) -> Program:
    """Parses and compiles a script. Any problem is a ScriptError with a line."""
    try:
        script = parse_script(source) if isinstance(source, str) else source
        if script.version is None:
            raise ScriptUnsupportedError("a script starts with //@version=5 or //@version=6", 1)
        if script.version < 5:
            raise ScriptUnsupportedError(f"Pine v{script.version} scripts are not supported: use v5 or v6", 1)
        return _Compiler(script).program()
    except ScriptError:
        raise
    except RecursionError:
        raise ScriptSyntaxError("the script is nested too deeply", 0) from None
    except Exception as error:  # noqa: BLE001 - anything else is a bug reported against the script, not a crash
        raise ScriptSyntaxError(f"the script can't be compiled: {error}", 0) from None


def run_script(
    program: Program | str,
    bars: BarSeries,
    inputs: dict[str, Any] | None = None,
    limits: ScriptLimits | None = None,
    symbol: str = "",
    timeframe: str = "",
) -> ScriptResult:
    if isinstance(program, str):
        program = compile_script(program)
    run = ScriptRun(program, bars, inputs or {}, limits or ScriptLimits(), symbol, timeframe)
    run.run_all()
    return run.result()


class ScriptRun:
    def __init__(
        self,
        program: Program,
        bars: BarSeries,
        inputs: dict[str, Any],
        limits: ScriptLimits,
        symbol: str = "",
        timeframe: str = "",
    ) -> None:
        if len(bars) > limits.max_bars:
            raise ScriptLimitError(f"a script runs on at most {limits.max_bars} bars")
        self.program = program
        self.limits = limits
        self.inputs = validate_inputs(program, inputs)
        self.symbol = symbol
        self.timeframe = timeframe
        self.open = list(bars.open)
        self.high = list(bars.high)
        self.low = list(bars.low)
        self.close = list(bars.close)
        self.volume = list(bars.volume)
        self.starts: list[datetime] = list(bars.start_times)
        self.time = [int(start.timestamp() * 1000) for start in self.starts]
        self.t = 0
        self.committed = 0
        self.all_slots: list[Slot] = []
        self.root = Context(self, None)
        self.plots = [PlotOutput(index, kind, title, dict(options)) for index, (kind, title, options) in enumerate(program.plot_specs)]
        self.hlines: list[dict[str, Any]] = []
        self.fills: list[dict[str, Any]] = []
        self.statics_done = False
        self.drawings: dict[str, list[Drawing]] = {}
        self.drawing_ids = 0
        self.alerts: list[dict[str, Any]] = []
        self.loop_iterations = 0
        self.bar_loop_iterations = 0
        self.seconds = 0.0
        self.deadline = 0.0
        self.allocated = 0
        self.last_bar_index = len(self.close) - 1
        self.interval_ms = interval_ms(timeframe)

    @property
    def can_extend(self) -> bool:
        """Whether new bars can be run one at a time (see Program.uses_last_bar)."""
        return not self.program.uses_last_bar

    def __len__(self) -> int:
        return len(self.close)

    def run_all(self) -> None:
        self._run_bars(self.committed, len(self.close))

    def append_bar(self, bar: Any) -> None:
        """Adds one closed bar and runs only it (incremental execution). A script that reads the last bar can't be
        extended (`can_extend`); run it again in full."""
        if not self.can_extend:
            raise RuntimeError("this script reads the last bar: run it again on all the bars instead of extending it")
        series = BarSeries.from_bars([bar])
        self.open.append(series.open[0])
        self.high.append(series.high[0])
        self.low.append(series.low[0])
        self.close.append(series.close[0])
        self.volume.append(series.volume[0])
        self.starts.append(series.start_times[0])
        self.time.append(int(series.start_times[0].timestamp() * 1000))
        self.last_bar_index = len(self.close) - 1
        if len(self.close) > self.limits.max_bars:
            raise ScriptLimitError(f"a script runs on at most {self.limits.max_bars} bars")
        self._run_bars(self.committed, len(self.close))

    def _run_bars(self, start: int, end: int) -> None:
        began = clock.perf_counter()
        body = self.program.body
        lines = self.program.lines
        root = self.root
        self.deadline = began + self.limits.max_seconds - self.seconds
        token = CURRENT_RUN.set(self)
        index = 0
        try:
            for t in range(start, end):
                self.t = t
                self.bar_loop_iterations = 0
                for index, statement in enumerate(body):
                    statement(root)
                self.statics_done = True
                for slot in self.all_slots:
                    slot.history.append(slot.current)
                    if not slot.persistent:
                        slot.current = None
                self.committed = t + 1
                self.check_time()
        except ScriptError as error:
            if not error.line and index < len(lines):
                error.line = lines[index]
            raise
        except RecursionError:
            raise ScriptLimitError("the script is nested too deeply", lines[index] if index < len(lines) else 0) from None
        except MemoryError:
            raise ScriptLimitError("the script ran out of memory", lines[index] if index < len(lines) else 0) from None
        except (_Break, _Continue):
            raise ScriptSyntaxError("break and continue belong in a loop", lines[index] if index < len(lines) else 0) from None
        except Exception as error:  # noqa: BLE001 - any other failure is the script's error, with its line
            raise ScriptRuntimeError(f"{type(error).__name__}: {error}", lines[index] if index < len(lines) else 0) from None
        finally:
            CURRENT_RUN.reset(token)
            self.seconds += clock.perf_counter() - began

    def check_time(self) -> None:
        if clock.perf_counter() > self.deadline:
            raise ScriptLimitError(f"the script ran for more than {self.limits.max_seconds:g} s")

    def count_loop(self) -> None:
        self.loop_iterations += 1
        self.bar_loop_iterations += 1
        if self.bar_loop_iterations > self.limits.max_loop_iterations_per_bar or self.loop_iterations > self.limits.max_loop_iterations:
            raise ScriptLimitError("a loop ran too many times")
        if self.loop_iterations % 1024 == 0:
            self.check_time()

    def add_drawing(self, kind: str, fields: dict[str, Any]) -> Drawing:
        self.drawing_ids += 1
        drawing = Drawing(kind, self.drawing_ids, fields)
        items = self.drawings.setdefault(kind, [])
        items.append(drawing)
        declared = self.program.declaration.get({"label": "max_labels_count", "line": "max_lines_count", "box": "max_boxes_count"}.get(kind, ""), 50)
        cap = min(int(declared) if isinstance(declared, int | float) else 50, self.limits.max_drawings)
        live = [item for item in items if not item.deleted]
        # Like Pine, the oldest drawings are removed once a script has more than its maximum.
        while len(live) > cap:
            live.pop(0).deleted = True
        if len(items) > 4 * cap:
            self.drawings[kind] = [item for item in items if not item.deleted]
        return drawing

    def result(self) -> ScriptResult:
        drawings = [drawing for items in self.drawings.values() for drawing in items if not drawing.deleted]
        drawings.sort(key=lambda drawing: drawing.id)
        return ScriptResult(
            declaration=copy.deepcopy(self.program.declaration),
            inputs=copy.deepcopy(self.program.inputs),
            plots=self.plots,
            hlines=self.hlines,
            fills=self.fills,
            drawings=drawings,
            alerts=self.alerts,
            bars=len(self.close),
            seconds=self.seconds,
        )

    # Series

    def series(self, name: str, t: int) -> Any:
        if t < 0 or t >= len(self.close):
            return None
        if name == "close":
            return self.close[t]
        if name == "open":
            return self.open[t]
        if name == "high":
            return self.high[t]
        if name == "low":
            return self.low[t]
        if name == "volume":
            return self.volume[t]
        if name == "hl2":
            return (self.high[t] + self.low[t]) / 2
        if name == "hlc3":
            return (self.high[t] + self.low[t] + self.close[t]) / 3
        if name == "ohlc4":
            return (self.open[t] + self.high[t] + self.low[t] + self.close[t]) / 4
        if name == "hlcc4":
            return (self.high[t] + self.low[t] + self.close[t] + self.close[t]) / 4
        if name == "time":
            return self.time[t]
        if name == "time_close":
            # The bar's start plus the interval; without a known interval, the next bar's start.
            if self.interval_ms is not None:
                return self.time[t] + self.interval_ms
            return self.time[t + 1] if t + 1 < len(self.time) else None
        if name == "bar_index":
            return t
        raise ScriptRuntimeError(f"unknown series {name}")


SERIES_NAMES = {"open", "high", "low", "close", "volume", "hl2", "hlc3", "ohlc4", "hlcc4", "time", "time_close", "bar_index"}


def interval_ms(timeframe: str) -> int | None:
    """A fixed interval in milliseconds ("60" minutes, "15S", "D", "W"); None for months or unknown."""
    text = timeframe.strip().upper()
    if not text:
        return None
    unit = text[-1] if not text[-1].isdigit() else ""
    number = text[:-1] if unit else text
    count = int(number) if number.isdigit() else 1 if number == "" else None
    if count is None:
        return None
    seconds = {"": 60, "S": 1, "D": 86_400, "W": 604_800}.get(unit)
    return None if seconds is None else count * seconds * 1000


def validate_inputs(program: Program, inputs: dict[str, Any]) -> dict[str, Any]:
    """Checks a run's inputs against the script's declarations: known titles, the declared type, options and range."""
    declared = {item.title: item for item in program.inputs}
    for title, value in inputs.items():
        item = declared.get(title)
        if item is None:
            raise ScriptRuntimeError(f"the script has no input {title!r}")
        kind = item.type
        if kind == "int" and not (isinstance(value, int) and not isinstance(value, bool)):
            raise ScriptRuntimeError(f"input {title!r} takes a whole number")
        if kind == "float" and not (isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)):
            raise ScriptRuntimeError(f"input {title!r} takes a number")
        if kind == "bool" and not isinstance(value, bool):
            raise ScriptRuntimeError(f"input {title!r} takes true or false")
        if kind in ("string", "color", "timeframe", "symbol", "session", "text_area") and not isinstance(value, str):
            raise ScriptRuntimeError(f"input {title!r} takes text")
        if isinstance(value, str) and len(value) > 4_096:
            raise ScriptRuntimeError(f"input {title!r} is too long")
        if kind == "source" and value not in SERIES_NAMES:
            raise ScriptRuntimeError(f"input {title!r} takes a built-in series (close, hl2, ...)")
        options = item.options.get("options")
        if isinstance(options, list) and options and value not in options:
            raise ScriptRuntimeError(f"input {title!r} takes one of {options}")
        if kind in ("int", "float"):
            low, high = item.options.get("minval"), item.options.get("maxval")
            if isinstance(low, int | float) and value < low or isinstance(high, int | float) and value > high:
                raise ScriptRuntimeError(f"input {title!r} is out of its range")
    return dict(inputs)


def truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    return bool(value)


def _na(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _is_number(value: Any) -> bool:
    kind = type(value)
    return kind is int or kind is float


def _not_numbers(op: str, a: Any, b: Any) -> None:
    raise ScriptRuntimeError(f"can't apply {op} to {_type_name(a)} and {_type_name(b)}")


def _type_name(value: Any) -> str:
    return {bool: "bool", int: "int", float: "float", str: "string"}.get(type(value), type(value).__name__.lower().replace("script", ""))


def _checked_int(value: Any) -> Any:
    if type(value) is int and not -INT_LIMIT <= value <= INT_LIMIT:
        raise ScriptRuntimeError("integer overflow: a value went past Pine's 64-bit int range")
    return value


def _divide(a: Any, b: Any) -> Any:
    if _na(a) or _na(b):
        return None
    if not (_is_number(a) and _is_number(b)):
        _not_numbers("/", a, b)
    if b == 0:
        return None
    if isinstance(a, int) and isinstance(b, int) and not isinstance(a, bool) and a % b == 0:
        return a // b
    return a / b


def _modulo(a: Any, b: Any) -> Any:
    if _na(a) or _na(b):
        return None
    if not (_is_number(a) and _is_number(b)):
        _not_numbers("%", a, b)
    if b == 0:
        return None
    result = math.fmod(a, b)
    return int(result) if isinstance(a, int) and isinstance(b, int) else result


def _add(a: Any, b: Any) -> Any:
    if a is None or b is None:
        return None
    if type(a) is str and type(b) is str:
        return check_string(a + b)
    if not (_is_number(a) and _is_number(b)):
        _not_numbers("+", a, b)
    return _checked_int(a + b)


def _sub(a: Any, b: Any) -> Any:
    if a is None or b is None:
        return None
    if not (_is_number(a) and _is_number(b)):
        _not_numbers("-", a, b)
    return _checked_int(a - b)


def _mul(a: Any, b: Any) -> Any:
    if a is None or b is None:
        return None
    if not (_is_number(a) and _is_number(b)):
        _not_numbers("*", a, b)
    return _checked_int(a * b)


def _compare(op: str) -> Callable[[Any, Any], Any]:
    import operator

    function = {"<": operator.lt, ">": operator.gt, "<=": operator.le, ">=": operator.ge, "==": operator.eq, "!=": operator.ne}[op]

    ordering = op in ("<", ">", "<=", ">=")

    def compare(a: Any, b: Any) -> Any:
        if _na(a) or _na(b):
            # na compares false, except na != value.
            return op == "!=" and not (_na(a) and _na(b))
        if ordering and not ((_is_number(a) and _is_number(b)) or (type(a) is str and type(b) is str)):
            _not_numbers(op, a, b)
        return function(a, b)

    return compare


_ARITHMETIC: dict[str, Callable[[Any, Any], Any]] = {"+": _add, "-": _sub, "*": _mul, "/": _divide, "%": _modulo}


class _Compiler:
    def __init__(self, script: Script) -> None:
        from . import builtins

        self.builtins = builtins
        self.script = script
        self.scope = _Scope(None, in_function=False)
        self.declaration: dict[str, Any] = {}
        self.inputs: list[ScriptInput] = []
        self.plot_specs: list[tuple[str, str, dict[str, Any]]] = []
        self.uses_drawings = False
        self.uses_last_bar = False
        self.function_depth = 0
        self.loop_depth = 0
        self.version = script.version or 6

    def program(self) -> Program:
        body: list[Closure] = []
        lines: list[int] = []
        for statement in self.script.body:
            closure = self.statement(statement)
            if closure is not None:
                body.append(closure)
                lines.append(statement.line)
        if not self.declaration:
            raise ScriptSyntaxError("a script declares itself with indicator(...)", 1)
        return Program(self.script, body, self.declaration, self.inputs, self.plot_specs, self.uses_drawings, lines, self.uses_last_bar)

    def fail(self, node: Node, message: str, unsupported: bool = False) -> None:
        error = ScriptUnsupportedError if unsupported else ScriptSyntaxError
        raise error(message, node.line)

    # Statements

    def statement(self, node: Node) -> Closure | None:
        if isinstance(node, FunctionDef):
            self.function_def(node)
            return None
        if isinstance(node, Declare):
            return self.declare(node)
        if isinstance(node, TupleDeclare):
            return self.tuple_declare(node)
        if isinstance(node, Assign):
            return self.assign(node)
        if isinstance(node, For):
            return self.for_loop(node)
        if isinstance(node, ForIn):
            return self.for_in(node)
        if isinstance(node, While):
            return self.while_loop(node)
        if isinstance(node, (Break, Continue)) and self.loop_depth == 0:
            self.fail(node, "break and continue belong in a loop")
        if isinstance(node, Break):
            def do_break(ctx: Context) -> Any:
                raise _Break

            return do_break
        if isinstance(node, Continue):
            def do_continue(ctx: Context) -> Any:
                raise _Continue

            return do_continue
        return self.expression(node)

    def block(self, block: Block) -> Closure:
        outer = self.scope
        self.scope = _Scope(outer, outer.in_function)
        try:
            closures = [closure for statement in block.body if (closure := self.statement(statement)) is not None]
        finally:
            self.scope = outer
        if not closures:
            return lambda ctx: None
        if len(closures) == 1:
            return closures[0]

        def run_block(ctx: Context) -> Any:
            value = None
            for closure in closures:
                value = closure(ctx)
            return value

        return run_block

    def bind(self, node: Node, name: str, persistent: bool) -> _Binding:
        if name in self.builtins.RESERVED_NAMES:
            self.fail(node, f"{name!r} is a built-in name and can't be declared")
        if name in self.scope.names:
            self.fail(node, f"{name!r} is already declared: assign it with :=")
        binding = _Binding("slot", key=node.id * 1000 + len(self.scope.names), persistent=persistent, is_global=not self.scope.in_function)
        self.scope.names[name] = binding
        return binding

    def slot_writer(self, binding: _Binding) -> Callable[[Context], Slot]:
        key, persistent = binding.key, binding.persistent
        if binding.is_global:
            return lambda ctx: ctx.root.slot(key, persistent)
        return lambda ctx: ctx.slot(key, persistent)

    def declare(self, node: Declare) -> Closure:
        value = self.expression(node.value)
        if node.name in ("indicator", "strategy"):
            self.fail(node, f"{node.name!r} can't be used as a variable name")
        binding = self.bind(node, node.name, persistent=node.mode in ("var", "varip"))
        get_slot = self.slot_writer(binding)
        if node.mode:
            def declare_var(ctx: Context) -> Any:
                slot = get_slot(ctx)
                if not slot.initialized:
                    slot.current = value(ctx)
                    slot.initialized = True
                return slot.current

            return declare_var

        def declare_value(ctx: Context) -> Any:
            result = value(ctx)
            get_slot(ctx).current = result
            return result

        return declare_value

    def tuple_declare(self, node: TupleDeclare) -> Closure:
        value = self.expression(node.value)
        writers = [self.slot_writer(self.bind(node, name, persistent=False)) for name in node.names]
        count = len(writers)

        def declare_tuple(ctx: Context) -> Any:
            result = value(ctx)
            if not isinstance(result, tuple) or len(result) != count:
                raise ScriptRuntimeError(f"expected {count} values, got {result!r}", node.line)
            for writer, item in zip(writers, result, strict=True):
                writer(ctx).current = item
            return result

        return declare_tuple

    def assign(self, node: Assign) -> Closure:
        binding = self.scope.lookup(node.name)
        if binding is None or binding.kind != "slot":
            self.fail(node, f"{node.name!r} is assigned with {node.op} before it is declared")
        assert binding is not None
        value = self.expression(node.value)
        get_slot = self.slot_writer(binding)
        if node.op == ":=":
            def reassign(ctx: Context) -> Any:
                result = value(ctx)
                get_slot(ctx).current = result
                return result

            return reassign
        operation = _ARITHMETIC[node.op[0]]

        def update(ctx: Context) -> Any:
            slot = get_slot(ctx)
            slot.current = operation(slot.current, value(ctx))
            return slot.current

        return update

    def loop_body(self, body: Block, bindings: list[tuple[str, _Binding]]) -> Closure:
        outer = self.scope
        self.scope = _Scope(outer, outer.in_function)
        for name, binding in bindings:
            self.scope.names[name] = binding
        self.loop_depth += 1
        try:
            return self.block(body)
        finally:
            self.loop_depth -= 1
            self.scope = outer

    def for_loop(self, node: For) -> Closure:
        start, end = self.expression(node.start), self.expression(node.end)
        step = self.expression(node.step) if node.step is not None else None
        binding = _Binding("slot", key=node.id * 1000, is_global=not self.scope.in_function)
        body = self.loop_body(node.body, [(node.var, binding)])
        get_slot = self.slot_writer(binding)

        # v6 checks the `to` bound again before each iteration; v5 reads it once.
        dynamic = self.version >= 6

        def run_for(ctx: Context) -> Any:
            first, last = start(ctx), end(ctx)
            if _na(first) or _na(last):
                return None
            increment = step(ctx) if step is not None else (1 if last >= first else -1)
            if _na(increment) or increment == 0:
                return None
            increment = abs(increment) if last >= first else -abs(increment)
            counter = get_slot(ctx)
            value = None
            index = first
            run = ctx.run
            while (index <= last) if increment > 0 else (index >= last):
                run.count_loop()
                counter.current = index
                try:
                    value = body(ctx)
                except _Continue:
                    pass
                except _Break:
                    break
                index += increment
                if dynamic:
                    last = end(ctx)
                    if _na(last):
                        break
            return value

        return run_for

    def for_in(self, node: ForIn) -> Closure:
        iterable = self.expression(node.iterable)
        item_binding = _Binding("slot", key=node.id * 1000, is_global=not self.scope.in_function)
        bindings = [(node.item_var, item_binding)]
        index_binding = None
        if node.index_var is not None:
            index_binding = _Binding("slot", key=node.id * 1000 + 1, is_global=not self.scope.in_function)
            bindings.append((node.index_var, index_binding))
        body = self.loop_body(node.body, bindings)
        item_slot = self.slot_writer(item_binding)
        index_slot = self.slot_writer(index_binding) if index_binding else None

        def run_for_in(ctx: Context) -> Any:
            items = iterable(ctx)
            if items is None:
                return None
            values = list(getattr(items, "items", items))
            value = None
            for index, item in enumerate(values):
                ctx.run.count_loop()
                item_slot(ctx).current = item
                if index_slot is not None:
                    index_slot(ctx).current = index
                try:
                    value = body(ctx)
                except _Continue:
                    pass
                except _Break:
                    break
            return value

        return run_for_in

    def while_loop(self, node: While) -> Closure:
        condition = self.expression(node.condition)
        self.loop_depth += 1
        try:
            body = self.block(node.body)
        finally:
            self.loop_depth -= 1

        def run_while(ctx: Context) -> Any:
            value = None
            while truthy(condition(ctx)):
                ctx.run.count_loop()
                try:
                    value = body(ctx)
                except _Continue:
                    continue
                except _Break:
                    break
            return value

        return run_while

    def function_def(self, node: FunctionDef) -> None:
        if self.scope.in_function or self.scope.parent is not None:
            self.fail(node, "functions are declared at the top level of a script")
        function = _Function(node.name, [])
        outer = self.scope
        self.scope = _Scope(outer, in_function=True)
        try:
            for param in node.params:
                default = self.expression(param.default) if param.default is not None else None
                binding = _Binding("slot", key=node.id * 1000 + len(function.params) + 1, is_global=False)
                self.scope.names[param.name] = binding
                function.params.append((param.name, binding.key, default))
            self.function_depth += 1
            function.body = self.block(node.body)
        finally:
            self.function_depth -= 1
            self.scope = outer
        # Bound after its body is compiled: a function can't call itself (Pine has no recursion).
        self.scope.names[node.name] = _Binding("function", function=function)

    # Expressions

    def expression(self, node: Node) -> Closure:
        if isinstance(node, Literal):
            value = node.value
            return lambda ctx: value
        if isinstance(node, ColorLiteral):
            color = node.value
            return lambda ctx: color
        if isinstance(node, Name):
            return self.name(node)
        if isinstance(node, Binary):
            return self.binary(node)
        if isinstance(node, Unary):
            return self.unary(node)
        if isinstance(node, Ternary):
            condition, then, otherwise = self.expression(node.condition), self.expression(node.then), self.expression(node.otherwise)
            return lambda ctx: then(ctx) if truthy(condition(ctx)) else otherwise(ctx)
        if isinstance(node, History):
            return self.history(node)
        if isinstance(node, Call):
            return self.call(node)
        if isinstance(node, MethodCall):
            return self.method_call(node, self.expression(node.target), node.method, node.args, node.kwargs)
        if isinstance(node, TupleExpr):
            items = [self.expression(item) for item in node.items]
            return lambda ctx: tuple(item(ctx) for item in items)
        if isinstance(node, If):
            return self.if_expression(node)
        if isinstance(node, Switch):
            return self.switch(node)
        self.fail(node, f"{type(node).__name__} can't be used as a value")
        raise AssertionError("unreachable")

    def name(self, node: Name) -> Closure:
        binding = self.scope.lookup(node.name)
        if binding is not None and binding.kind == "slot":
            key = binding.key
            if binding.is_global:
                def read_global(ctx: Context) -> Any:
                    slot = ctx.root.slots.get(key)
                    return None if slot is None else slot.current

                return read_global

            def read_local(ctx: Context) -> Any:
                slot = ctx.slots.get(key)
                return None if slot is None else slot.current

            return read_local
        if binding is not None:
            self.fail(node, f"{node.name!r} is a function: call it with ()")
        builtin = self.builtins.builtin_variable(self, node)
        if builtin is None:
            self.fail(node, f"undeclared identifier {node.name!r}", unsupported=self.builtins.is_unsupported(node.name))
        assert builtin is not None
        return builtin

    def binary(self, node: Binary) -> Closure:
        left, right = self.expression(node.left), self.expression(node.right)
        if node.op in ("and", "or"):
            if self.version >= 6:
                # v6 evaluates and/or lazily.
                if node.op == "and":
                    return lambda ctx: truthy(left(ctx)) and truthy(right(ctx))
                return lambda ctx: truthy(left(ctx)) or truthy(right(ctx))
            # v5 evaluates both sides on every bar (a ta.* call on the right still advances).
            if node.op == "and":
                return lambda ctx: (lambda a, b: truthy(a) and truthy(b))(left(ctx), right(ctx))
            return lambda ctx: (lambda a, b: truthy(a) or truthy(b))(left(ctx), right(ctx))
        if node.op in _ARITHMETIC:
            operation = _ARITHMETIC[node.op]
            if node.op == "/" and self.version <= 5:
                # v5 truncates only an int constant divided by an int constant (7 / 2 == 3).
                a_constant, b_constant = _int_constant(node.left), _int_constant(node.right)
                if a_constant is not None and b_constant is not None and b_constant != 0:
                    truncated = int(a_constant / b_constant)
                    return lambda ctx: truncated
            if node.op in ("+", "-", "*"):
                # The hot path: two numbers.
                symbol = node.op

                def arithmetic(ctx: Context) -> Any:
                    a = left(ctx)
                    b = right(ctx)
                    if a is None or b is None:
                        return None
                    kind_a, kind_b = type(a), type(b)
                    if (kind_a is float or kind_a is int) and (kind_b is float or kind_b is int):
                        result = a + b if symbol == "+" else a - b if symbol == "-" else a * b
                        if type(result) is int and not -INT_LIMIT <= result <= INT_LIMIT:
                            return _checked_int(result)
                        return result
                    return operation(a, b)

                return arithmetic
            return lambda ctx: operation(left(ctx), right(ctx))
        compare = _compare(node.op)
        return lambda ctx: compare(left(ctx), right(ctx))

    def unary(self, node: Unary) -> Closure:
        operand = self.expression(node.operand)
        if node.op == "not":
            return lambda ctx: not truthy(operand(ctx))
        if node.op == "-":
            def negate(ctx: Context) -> Any:
                value = operand(ctx)
                return None if value is None else -value

            return negate
        return operand

    def history(self, node: History) -> Closure:
        offset = self.expression(node.offset)
        target = node.target
        if isinstance(target, Name):
            binding = self.scope.lookup(target.name)
            if binding is not None and binding.kind == "slot":
                key = binding.key
                is_global = binding.is_global

                def read_history(ctx: Context) -> Any:
                    n = offset(ctx)
                    if _na(n) or n < 0:
                        return None
                    slot = (ctx.root if is_global else ctx).slots.get(key)
                    return None if slot is None else slot.at(int(n))

                return read_history
            if binding is None and target.name in SERIES_NAMES:
                series = target.name

                def read_series(ctx: Context) -> Any:
                    n = offset(ctx)
                    if _na(n) or n < 0:
                        return None
                    run = ctx.run
                    return run.series(series, run.t - int(n))

                return read_series
        # Any other expression: its own history buffer, filled on the bars it runs.
        value = self.expression(target)
        key = node.id * 1000 + 999

        def read_expression_history(ctx: Context) -> Any:
            slot = ctx.slot(key, False)
            slot.current = value(ctx)
            n = offset(ctx)
            if _na(n) or n < 0:
                return None
            return slot.at(int(n))

        return read_expression_history

    def if_expression(self, node: If) -> Closure:
        condition = self.expression(node.condition)
        then = self.block(node.then)
        otherwise = self.block(node.otherwise) if node.otherwise is not None else None

        def run_if(ctx: Context) -> Any:
            if truthy(condition(ctx)):
                return then(ctx)
            return otherwise(ctx) if otherwise is not None else None

        return run_if

    def switch(self, node: Switch) -> Closure:
        subject = self.expression(node.subject) if node.subject is not None else None
        cases = [(self.expression(match) if match is not None else None, self.block(body)) for match, body in node.cases]

        def run_switch(ctx: Context) -> Any:
            value = subject(ctx) if subject is not None else None
            for match, body in cases:
                if match is None:
                    return body(ctx)
                candidate = match(ctx)
                # na equals nothing, so an na subject takes the default case.
                if (subject is not None and not _na(value) and not _na(candidate) and candidate == value) or (subject is None and truthy(candidate)):
                    return body(ctx)
            return None

        return run_switch

    def call(self, node: Call) -> Closure:
        binding = self.scope.lookup(node.callee)
        if binding is not None and binding.kind == "function":
            assert binding.function is not None
            return self.user_call(node, binding.function)
        head, _, method = node.callee.partition(".")
        if method and "." not in method:
            target = self.scope.lookup(head)
            if target is not None and target.kind == "slot":
                return self.method_call(node, self.name(Name(line=node.line, name=head)), method, node.args, node.kwargs)
        factory = self.builtins.builtin_function(node.callee)
        if factory is None:
            if self.builtins.is_unsupported(node.callee):
                self.fail(node, f"{node.callee}() is not supported yet", unsupported=True)
            self.fail(node, f"unknown function {node.callee}()")
        assert factory is not None
        return factory(self, node)

    def method_call(self, node: Node, target: Closure, method: str, args: list[Node], kwargs: dict[str, Node]) -> Closure:
        # obj.method(...) is <type>.method(obj, ...), with the type known at run time.
        arguments = [self.expression(arg) for arg in args]
        named = {key: self.expression(value) for key, value in kwargs.items()}
        builtins = self.builtins

        def call_method(ctx: Context) -> Any:
            obj = target(ctx)
            kind = builtins.kind_of(obj)
            function = builtins.method(kind, method)
            if function is None:
                raise ScriptRuntimeError(f"{kind or 'na'} has no method {method}()", node.line)
            return function(ctx, obj, *[a(ctx) for a in arguments], **{key: value(ctx) for key, value in named.items()})

        return call_method

    def user_call(self, node: Call, function: _Function) -> Closure:
        if len(node.args) > len(function.params):
            self.fail(node, f"{function.name}() takes {len(function.params)} arguments")
        names = [name for name, _, _ in function.params]
        values: list[Closure | None] = [None] * len(names)
        for index, arg in enumerate(node.args):
            values[index] = self.expression(arg)
        for key, arg in node.kwargs.items():
            if key not in names:
                self.fail(node, f"{function.name}() has no argument {key!r}")
            values[names.index(key)] = self.expression(arg)
        params: list[tuple[int, Closure]] = []
        for (name, key, default), value in zip(function.params, values, strict=True):
            chosen = value or default
            if chosen is None:
                self.fail(node, f"{function.name}() needs a value for {name!r}")
            assert chosen is not None
            params.append((key, chosen))
        site = node.id
        body = function

        def call_user(ctx: Context) -> Any:
            arguments = [(key, value(ctx)) for key, value in params]
            child = ctx.child(site)
            # The previous call's values become the series' history (x[1] in a function is its last call's x).
            if child.slots or child.calls:
                child.commit_call()
            for key, argument in arguments:
                child.slot(key, False).current = argument
            assert body.body is not None
            return body.body(child)

        return call_user


def _int_constant(node: Node) -> int | None:
    """An int literal, or a negated one."""
    if isinstance(node, Literal) and type(node.value) is int:
        return node.value
    if isinstance(node, Unary) and node.op == "-" and isinstance(node.operand, Literal) and type(node.operand.value) is int:
        return -node.operand.value
    return None
