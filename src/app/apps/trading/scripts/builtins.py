"""Built-in variables and functions of Omnix Scripts.

A function is a factory ``factory(compiler, call_node) -> closure``. ``pure`` builds one for a stateless function,
``site`` for a ``ta.*`` function that keeps per-call-site state (``ta.Site``), and outputs (``plot`` and the like)
register what they produce with the compiler.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from . import ta
from .errors import ScriptLimitError, ScriptRuntimeError, ScriptSyntaxError, ScriptUnsupportedError
from .runtime import CURRENT_RUN, SERIES_NAMES, Closure, Context, Drawing, ScriptInput, _na, allocate, check_string, current_limits, truthy
from .syntax import Call, ColorLiteral, Literal, Name, Node, TupleExpr, Unary

Factory = Callable[[Any, Call], Closure]

RESERVED_NAMES = {"open", "high", "low", "close", "volume", "time", "bar_index", "na", "true", "false"}

# Namespaces Omnix Scripts doesn't support yet, so their names say so instead of "unknown".
UNSUPPORTED_PREFIXES = ("request.", "strategy.", "matrix.", "ticker.", "polyline.", "chart.", "library", "strategy")


def is_unsupported(name: str) -> bool:
    return name.startswith(UNSUPPORTED_PREFIXES)


# Argument binding


def _spec(text: str) -> tuple[list[str], dict[str, Any]]:
    params: list[str] = []
    defaults: dict[str, Any] = {}
    for part in (item.strip() for item in text.split(",") if item.strip()):
        if "=" in part:
            name, raw = (piece.strip() for piece in part.split("=", 1))
            defaults[name] = _DEFAULT_LITERALS.get(raw, raw) if not _is_number(raw) else (float(raw) if "." in raw else int(raw))
        else:
            name = part
        params.append(name)
    return params, defaults


_DEFAULT_LITERALS: dict[str, Any] = {"na": None, "true": True, "false": False, '""': ""}


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _bind(c: Any, node: Call, params: list[str], defaults: dict[str, Any], strict: bool = True) -> list[Closure]:
    if len(node.args) > len(params):
        raise ScriptSyntaxError(f"{node.callee}() takes at most {len(params)} arguments", node.line)
    bound: dict[str, Closure] = {}
    for name, arg in zip(params, node.args, strict=False):
        bound[name] = c.expression(arg)
    for key, arg in node.kwargs.items():
        if key not in params:
            if strict:
                raise ScriptSyntaxError(f"{node.callee}() has no argument {key!r}", node.line)
            continue
        if key in bound:
            raise ScriptSyntaxError(f"{node.callee}() got {key!r} twice", node.line)
        bound[key] = c.expression(arg)
    closures: list[Closure] = []
    for name in params:
        if name in bound:
            closures.append(bound[name])
        elif name in defaults:
            value = defaults[name]
            closures.append(lambda ctx, value=value: value)
        else:
            raise ScriptSyntaxError(f"{node.callee}() needs a value for {name!r}", node.line)
    return closures


def pure(spec: str, function: Callable[..., Any]) -> Factory:
    params, defaults = _spec(spec)

    def factory(c: Any, node: Call) -> Closure:
        closures = _bind(c, node, params, defaults)
        if len(closures) == 1:
            (a,) = closures
            return lambda ctx: function(a(ctx))
        if len(closures) == 2:
            a, b = closures
            return lambda ctx: function(a(ctx), b(ctx))
        return lambda ctx: function(*[closure(ctx) for closure in closures])

    return factory


def variadic(function: Callable[..., Any]) -> Factory:
    def factory(c: Any, node: Call) -> Closure:
        if node.kwargs:
            raise ScriptSyntaxError(f"{node.callee}() takes values only", node.line)
        closures = [c.expression(arg) for arg in node.args]
        return lambda ctx: function(*[closure(ctx) for closure in closures])

    return factory


BarInputs = Callable[[Any, int], tuple[Any, ...]]


def _site_closure(node_id: int, step: ta.Step, closures: list[Closure], bar: BarInputs | None) -> Closure:
    def call(ctx: Context) -> Any:
        sites = ctx.sites
        state = sites.get(node_id)
        if state is None:
            state = sites[node_id] = ta.Site()
        run = ctx.run
        t = run.t
        values = [closure(ctx) for closure in closures]
        if bar is not None:
            return state.run(t, step, *bar(run, t), *values)
        return state.run(t, step, *values)

    return call


def site(spec: str, step: ta.Step, bar: BarInputs | None = None) -> Factory:
    params, defaults = _spec(spec)

    def factory(c: Any, node: Call) -> Closure:
        return _site_closure(node.id, step, _bind(c, node, params, defaults), bar)

    return factory


def site_with_optional_source(spec: str, step: ta.Step, source: str) -> Factory:
    """ta.highest(length) reads `high`; ta.highest(source, length) the source. Same for the pivots."""
    full_params, defaults = _spec(spec)
    short_params = full_params[1:]

    def factory(c: Any, node: Call) -> Closure:
        provided = len(node.args) + sum(1 for key in node.kwargs if key in full_params)
        if provided < len(full_params) - len(defaults) and "source" not in node.kwargs:
            closures = _bind(c, node, short_params, defaults)
            return _site_closure(node.id, step, closures, lambda run, t: (run.series(source, t),))
        return _site_closure(node.id, step, _bind(c, node, full_params, defaults), None)

    return factory


def _hlc(run: Any, t: int) -> tuple[Any, ...]:
    return run.high[t], run.low[t], run.close[t]


# Values


class ScriptArray:
    __slots__ = ("items",)

    def __init__(self, items: list[Any]) -> None:
        self.items = items

    def __repr__(self) -> str:
        return f"array({self.items!r})"


class ScriptMap:
    __slots__ = ("items",)

    def __init__(self) -> None:
        self.items: dict[Any, Any] = {}


def kind_of(value: Any) -> str | None:
    if isinstance(value, ScriptArray):
        return "array"
    if isinstance(value, ScriptMap):
        return "map"
    if isinstance(value, Drawing):
        return value.kind
    if isinstance(value, str):
        return "str"
    return None


def _nz(value: Any, replacement: Any = 0) -> Any:
    return replacement if _na(value) else value


def _number_or_na(function: Callable[..., float]) -> Callable[..., Any]:
    def wrapped(*values: Any) -> Any:
        if any(_na(value) for value in values):
            return None
        try:
            result = function(*values)
        except (ValueError, ZeroDivisionError, OverflowError):
            return None
        return None if isinstance(result, float) and (math.isnan(result) or math.isinf(result)) else result

    return wrapped


def _round(value: Any, precision: Any = None) -> Any:
    if _na(value) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    if precision is None or _na(precision):
        # Pine rounds halves up, like JavaScript.
        return int(math.floor(value + 0.5))
    factor = 10 ** max(0, min(15, int(precision)))
    return math.floor(value * factor + 0.5) / factor


def _max(*values: Any) -> Any:
    if not values or any(_na(value) for value in values):
        return None
    return max(values)


def _min(*values: Any) -> Any:
    if not values or any(_na(value) for value in values):
        return None
    return min(values)


def _avg(*values: Any) -> Any:
    if not values or any(_na(value) for value in values):
        return None
    return ta.js_sum(values) / len(values)


def _sign(value: Any) -> Any:
    if _na(value):
        return None
    return 1.0 if value > 0 else -1.0 if value < 0 else 0.0


def _int(value: Any) -> Any:
    if _na(value):
        return None
    if not isinstance(value, int | float):
        raise ScriptRuntimeError("int() takes a number")
    return int(value) if math.isfinite(value) else None


def _float(value: Any) -> Any:
    if _na(value):
        return None
    if not isinstance(value, int | float):
        raise ScriptRuntimeError("float() takes a number")
    return float(value)


def _bool(value: Any) -> Any:
    return truthy(value)


# Colors


COLORS = {
    "aqua": "#00BCD4", "black": "#363A45", "blue": "#2196F3", "fuchsia": "#E040FB", "gray": "#787B86",
    "green": "#4CAF50", "lime": "#00E676", "maroon": "#880E4F", "navy": "#311B92", "olive": "#808000",
    "orange": "#FF9800", "purple": "#9C27B0", "red": "#F23645", "silver": "#B2B5BE", "teal": "#089981",
    "white": "#FFFFFF", "yellow": "#FDD835",
}


def _rgba(color: Any) -> tuple[int, int, int, float] | None:
    if not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?", color):
        return None
    red, green, blue = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    alpha = int(color[7:9], 16) if len(color) == 9 else 255
    return red, green, blue, alpha / 255


def _color(red: float, green: float, blue: float, transparency: float) -> str:
    alpha = round(255 * (1 - max(0.0, min(100.0, transparency)) / 100))
    channels = [max(0, min(255, int(round(channel)))) for channel in (red, green, blue)]
    return "#" + "".join(f"{channel:02X}" for channel in channels) + ("" if alpha == 255 else f"{alpha:02X}")


def _color_new(color: Any, transparency: Any) -> Any:
    rgba = _rgba(color)
    if rgba is None or _na(transparency):
        return None
    return _color(rgba[0], rgba[1], rgba[2], float(transparency))


def _color_rgb(red: Any, green: Any, blue: Any, transparency: Any = 0) -> Any:
    if any(_na(value) for value in (red, green, blue)):
        return None
    return _color(red, green, blue, float(_nz(transparency)))


def _color_from_gradient(value: Any, bottom: Any, top: Any, bottom_color: Any, top_color: Any) -> Any:
    low, high = _rgba(bottom_color), _rgba(top_color)
    if _na(value) or _na(bottom) or _na(top) or low is None or high is None:
        return None
    share = 0.0 if top == bottom else max(0.0, min(1.0, (value - bottom) / (top - bottom)))
    mixed = [low[i] + (high[i] - low[i]) * share for i in range(4)]
    return _color(mixed[0], mixed[1], mixed[2], 100 * (1 - mixed[3]))


def _channel(index: int) -> Callable[[Any], Any]:
    def read(color: Any) -> Any:
        rgba = _rgba(color)
        if rgba is None:
            return None
        return (100 * (1 - rgba[3])) if index == 3 else rgba[index]

    return read


# Strings


def _tostring(value: Any, format: Any = "") -> Any:
    if value is None:
        return "NaN"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if format in ("format.percent",):
            return f"{value:.2f}%"
        if isinstance(format, str) and format.startswith("#"):
            decimals = len(format.split(".", 1)[1]) if "." in format else 0
            text = f"{value:.{decimals}f}"
            return text.rstrip("0").rstrip(".") if "." in text and "0" not in format.split(".", 1)[-1] else text
        if format == "format.mintick":
            return f"{value:.2f}"
        return repr(value) if not value.is_integer() else str(int(value)) if abs(value) < 1e16 else repr(value)
    if isinstance(value, ScriptArray):
        return "[" + _bounded_join(", ", (str(_tostring(item)) for item in value.items), 2) + "]"
    return str(value)


def _bounded_join(separator: str, parts: Any, reserve: int = 0) -> str:
    """Joins parts, stopping as soon as the result would pass the string limit (never building more)."""
    limit = current_limits().max_string_length - reserve
    pieces: list[str] = []
    total = 0
    for index, part in enumerate(parts):
        total += len(part) + (len(separator) if index else 0)
        if total > limit:
            check_string(" " * (limit + reserve + 1))
        pieces.append(part)
    return separator.join(pieces)


_PLACEHOLDER = re.compile(r"\{(\d+)(?:,([^{}]*))?\}")


def _format(template: Any, *values: Any) -> Any:
    """{0}, {1,number,#.##}: one pass over the template, so a value containing braces is never re-read."""
    if not isinstance(template, str):
        return None

    limit = current_limits().max_string_length
    pieces: list[str] = []
    total = 0
    position = 0
    for match in _PLACEHOLDER.finditer(template):
        pieces.append(template[position : match.start()])
        index = int(match.group(1))
        if index >= len(values):
            text = match.group(0)
        else:
            value = values[index]
            parts = (match.group(2) or "").split(",")
            pattern = parts[1] if len(parts) > 1 else ""
            text = str(_tostring(float(value) if isinstance(value, int | float) and not isinstance(value, bool) else value, pattern))
        pieces.append(text)
        total += match.start() - position + len(text)
        # Stops as soon as the result passes the limit, before building it.
        if total > limit:
            check_string(" " * (limit + 1))
        position = match.end()
    pieces.append(template[position:])
    return check_string("".join(pieces))


def _substring(source: Any, begin: Any, end: Any = None) -> Any:
    if not isinstance(source, str) or _na(begin) or not isinstance(begin, int | float) or not (end is None or isinstance(end, int | float)):
        return None
    return source[int(begin) :] if end is None else source[int(begin) : int(end)]


def _tonumber(text: Any) -> Any:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _split(text: Any, separator: Any) -> Any:
    if not isinstance(text, str) or not isinstance(separator, str):
        return None
    parts = list(text) if separator == "" else text.split(separator)
    allocate(len(parts), len(parts))
    return ScriptArray(parts)


def _replace(source: Any, target: Any, replacement: Any, occurrence: Any = 0) -> Any:
    if not all(isinstance(value, str) for value in (source, target, replacement)):
        return None
    if not isinstance(occurrence, int | float) and occurrence is not None:
        return None
    start = -1
    for _ in range(max(0, int(occurrence or 0)) + 1):
        start = source.find(target, start + 1)
        if start < 0:
            return source
    return check_string(source[:start] + replacement + source[start + len(target) :])


# Arrays


def _array_new(initial: Any = None) -> Callable[[Any, Any], Any]:
    def create(size: Any = 0, initial_value: Any = initial) -> Any:
        if not _na(size) and not isinstance(size, int | float):
            raise ScriptRuntimeError("an array's size is a number")
        count = 0 if _na(size) else int(size)
        if count < 0:
            raise ScriptRuntimeError("an array's size can't be negative")
        allocate(count, count)
        return ScriptArray([initial_value] * count)

    return create


def _items(array: Any) -> list[Any]:
    if not isinstance(array, ScriptArray):
        raise ScriptRuntimeError("expected an array, got na")
    return array.items


def _index(array: Any, index: Any) -> int:
    items = _items(array)
    if _na(index) or not isinstance(index, int | float):
        raise ScriptRuntimeError("array index is na")
    position = int(index)
    if position < 0:
        position += len(items)
    if not 0 <= position < len(items):
        raise ScriptRuntimeError(f"array index {int(index)} is out of bounds (size {len(items)})")
    return position


def _grow(items: list[Any], count: int) -> None:
    allocate(count, len(items) + count)


def _push(array: Any, value: Any) -> None:
    items = _items(array)
    _grow(items, 1)
    items.append(value)


def _pop(array: Any) -> Any:
    items = _items(array)
    if not items:
        raise ScriptRuntimeError("pop() on an empty array")
    return items.pop()


def _shift(array: Any) -> Any:
    items = _items(array)
    if not items:
        raise ScriptRuntimeError("shift() on an empty array")
    return items.pop(0)


def _unshift(array: Any, value: Any) -> None:
    items = _items(array)
    _grow(items, 1)
    items.insert(0, value)


def _get(array: Any, index: Any) -> Any:
    return _items(array)[_index(array, index)]


def _set(array: Any, index: Any, value: Any) -> None:
    _items(array)[_index(array, index)] = value


def _insert(array: Any, index: Any, value: Any) -> None:
    items = _items(array)
    if _na(index) or not isinstance(index, int | float) or not 0 <= int(index) <= len(items):
        raise ScriptRuntimeError("array index is out of bounds")
    _grow(items, 1)
    items.insert(int(index), value)


def _remove(array: Any, index: Any) -> Any:
    return _items(array).pop(_index(array, index))


def _numbers(array: Any) -> list[float]:
    return [item for item in _items(array) if not _na(item)]


def _array_sum(array: Any) -> Any:
    values = _numbers(array)
    return ta.js_sum(values) if values else None


def _array_avg(array: Any) -> Any:
    values = _numbers(array)
    return ta.js_sum(values) / len(values) if values else None


def _array_max(array: Any, nth: Any = 0) -> Any:
    values = sorted(_numbers(array), reverse=True)
    return values[int(nth)] if len(values) > int(nth) else None


def _array_min(array: Any, nth: Any = 0) -> Any:
    values = sorted(_numbers(array))
    return values[int(nth)] if len(values) > int(nth) else None


def _array_stdev(array: Any, biased: Any = True) -> Any:
    values = _numbers(array)
    if not values:
        return None
    center = ta.js_sum(values) / len(values)
    divisor = len(values) if biased or len(values) == 1 else len(values) - 1
    return math.sqrt(ta.js_sum([(value - center) * (value - center) for value in values]) / divisor)


def _array_median(array: Any) -> Any:
    values = sorted(_numbers(array))
    if not values:
        return None
    middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


def _array_sort(array: Any, order: Any = "order.ascending") -> None:
    _items(array).sort(key=lambda item: (item is None, item), reverse=order == "order.descending")


def _array_slice(array: Any, start: Any, end: Any) -> Any:
    items = _items(array)
    if any(_na(value) or not isinstance(value, int | float) for value in (start, end)):
        raise ScriptRuntimeError("slice() takes two indexes")
    part = items[int(start) : int(end)]
    allocate(len(part), len(part))
    return ScriptArray(part)


def _array_copy(array: Any) -> Any:
    items = _items(array)
    allocate(len(items), len(items))
    return ScriptArray(list(items))


def _array_concat(array: Any, other: Any) -> Any:
    items, extra = _items(array), _items(other)
    _grow(items, len(extra))
    items.extend(list(extra))
    return array


def _array_join(array: Any, separator: Any = "") -> Any:
    if not isinstance(separator, str):
        separator = ""
    return _bounded_join(separator, (str(_tostring(item)) for item in _items(array)))


def _array_from(*values: Any) -> Any:
    allocate(len(values), len(values))
    return ScriptArray(list(values))


def _array_fill(array: Any, value: Any, start: Any = 0, end: Any = None) -> None:
    items = _items(array)
    first = 0 if _na(start) else max(0, int(start))
    last = len(items) if _na(end) else min(len(items), int(end))
    for index in range(first, last):
        items[index] = value


ARRAY_METHODS: dict[str, Callable[..., Any]] = {
    "push": _push, "pop": _pop, "shift": _shift, "unshift": _unshift, "get": _get, "set": _set,
    "insert": _insert, "remove": _remove, "size": lambda a: len(_items(a)), "clear": lambda a: _items(a).clear(),
    "sum": _array_sum, "avg": _array_avg, "max": _array_max, "min": _array_min, "stdev": _array_stdev,
    "median": _array_median, "includes": lambda a, v: v in _items(a),
    "indexof": lambda a, v: _items(a).index(v) if v in _items(a) else -1,
    "lastindexof": lambda a, v: len(_items(a)) - 1 - _items(a)[::-1].index(v) if v in _items(a) else -1,
    "first": lambda a: _get(a, 0), "last": lambda a: _get(a, -1), "copy": _array_copy,
    "reverse": lambda a: _items(a).reverse(), "sort": _array_sort, "slice": _array_slice, "fill": _array_fill,
    "concat": _array_concat,
    "join": _array_join,
}


def _map_put(target: Any, key: Any, value: Any) -> Any:
    if not isinstance(target, ScriptMap):
        raise ScriptRuntimeError("expected a map, got na")
    if key not in target.items:
        allocate(1, len(target.items) + 1)
    previous = target.items.get(key)
    target.items[key] = value
    return previous


MAP_METHODS: dict[str, Callable[..., Any]] = {
    "put": lambda m, k, v: _map_put(m, k, v),
    "get": lambda m, k: m.items.get(k),
    "contains": lambda m, k: k in m.items,
    "remove": lambda m, k: m.items.pop(k, None),
    "size": lambda m: len(m.items),
    "keys": lambda m: _array_from(*m.items),
    "values": lambda m: _array_from(*m.items.values()),
    "clear": lambda m: m.items.clear(),
}


def _replace_all(source: Any, target: Any, replacement: Any) -> Any:
    if not all(isinstance(value, str) for value in (source, target, replacement)):
        return None
    if target and source.count(target) * max(0, len(replacement) - len(target)) + len(source) > current_limits().max_string_length:
        check_string(" " * (current_limits().max_string_length + 1))
    return source.replace(target, replacement) if target else source


def _repeat(source: Any, count: Any, separator: Any = "") -> Any:
    if not isinstance(source, str) or _na(count) or not isinstance(count, int | float) or not isinstance(separator, str):
        return None
    times = max(0, int(count))
    # Checked before the string is built.
    if times * (len(source) + len(separator)) > current_limits().max_string_length:
        check_string(" " * (current_limits().max_string_length + 1))
    return separator.join([source] * times)


STR_METHODS: dict[str, Callable[..., Any]] = {
    "length": lambda s: len(s) if isinstance(s, str) else None,
    "contains": lambda s, part: isinstance(s, str) and isinstance(part, str) and part in s,
    "startswith": lambda s, part: isinstance(s, str) and isinstance(part, str) and s.startswith(part),
    "endswith": lambda s, part: isinstance(s, str) and isinstance(part, str) and s.endswith(part),
    "pos": lambda s, part: s.find(part) if isinstance(s, str) and s.find(part) >= 0 else None,
    "upper": lambda s: s.upper() if isinstance(s, str) else None,
    "lower": lambda s: s.lower() if isinstance(s, str) else None,
    "trim": lambda s: s.strip() if isinstance(s, str) else None,
    "substring": _substring,
    "replace": _replace,
    "replace_all": lambda s, a, b: _replace_all(s, a, b),
    "split": _split,
    "tonumber": _tonumber,
    "tostring": _tostring,
    "format": _format,
    "repeat": lambda s, count, separator="": _repeat(s, count, separator),
}


# Drawings


DRAWING_FIELDS = {
    "label": "x, y, text=\"\", xloc=xloc.bar_index, yloc=yloc.price, color=na, style=label.style_label_down, textcolor=na, size=size.normal, textalign=text.align_center, tooltip=na, text_font_family=na, force_overlay=false, text_formatting=na",
    "line": "x1, y1, x2, y2, xloc=xloc.bar_index, extend=extend.none, color=na, style=line.style_solid, width=1, force_overlay=false",
    "box": "left, top, right, bottom, border_color=na, border_width=1, border_style=line.style_solid, extend=extend.none, xloc=xloc.bar_index, bgcolor=na, text=\"\", text_size=size.auto, text_color=na, text_halign=text.align_center, text_valign=text.align_center, text_wrap=text.wrap_none, text_font_family=na, force_overlay=false, text_formatting=na",
    "table": "position, columns, rows, bgcolor=na, frame_color=na, frame_width=0, border_color=na, border_width=0, force_overlay=false",
    "linefill": "line1, line2, color",
}


def _drawing_factory(kind: str) -> Factory:
    params, defaults = _spec(DRAWING_FIELDS[kind])
    # Constants given in the spec as names (xloc.bar_index): stored as their name.
    defaults = {key: value for key, value in defaults.items()}

    def factory(c: Any, node: Call) -> Closure:
        c.uses_drawings = True
        closures = _bind(c, node, params, defaults)

        def create(ctx: Context) -> Any:
            fields = {name: closure(ctx) for name, closure in zip(params, closures, strict=True)}
            if kind == "table":
                fields["cells"] = {}
            return ctx.run.add_drawing(kind, fields)

        return create

    return factory


def _drawing_setter(kind: str, *names: str) -> Callable[..., None]:
    def set_fields(ctx: Context, drawing: Any, *values: Any) -> None:
        if isinstance(drawing, Drawing) and not drawing.deleted:
            for name, value in zip(names, values, strict=False):
                drawing.fields[name] = value

    return set_fields


def _drawing_getter(name: str) -> Callable[..., Any]:
    def get_field(ctx: Context, drawing: Any) -> Any:
        return drawing.fields.get(name) if isinstance(drawing, Drawing) else None

    return get_field


def _delete(ctx: Context, drawing: Any) -> None:
    if isinstance(drawing, Drawing):
        drawing.deleted = True


def _line_price(ctx: Context, line: Any, x: Any) -> Any:
    if not isinstance(line, Drawing):
        return None
    f = line.fields
    if f["x2"] == f["x1"]:
        return f["y1"]
    return f["y1"] + (f["y2"] - f["y1"]) * (x - f["x1"]) / (f["x2"] - f["x1"])


def _table_cell(ctx: Context, table: Any, column: Any, row: Any, *values: Any, **options: Any) -> None:
    if isinstance(table, Drawing):
        cell = table.fields["cells"].setdefault((int(column), int(row)), {})
        names = ("text", "width", "height", "text_color", "text_halign", "text_valign", "text_size", "bgcolor", "tooltip")
        cell.update(dict(zip(names, values, strict=False)))
        cell.update(options)


DRAWING_METHODS: dict[str, dict[str, Callable[..., Any]]] = {
    "label": {
        "set_x": _drawing_setter("label", "x"), "set_y": _drawing_setter("label", "y"),
        "set_xy": _drawing_setter("label", "x", "y"), "set_text": _drawing_setter("label", "text"),
        "set_color": _drawing_setter("label", "color"), "set_textcolor": _drawing_setter("label", "textcolor"),
        "set_style": _drawing_setter("label", "style"), "set_size": _drawing_setter("label", "size"),
        "set_tooltip": _drawing_setter("label", "tooltip"), "set_yloc": _drawing_setter("label", "yloc"),
        "set_xloc": _drawing_setter("label", "x", "xloc"), "set_textalign": _drawing_setter("label", "textalign"),
        "get_x": _drawing_getter("x"), "get_y": _drawing_getter("y"), "get_text": _drawing_getter("text"),
        "delete": _delete,
    },
    "line": {
        "set_x1": _drawing_setter("line", "x1"), "set_y1": _drawing_setter("line", "y1"),
        "set_x2": _drawing_setter("line", "x2"), "set_y2": _drawing_setter("line", "y2"),
        "set_xy1": _drawing_setter("line", "x1", "y1"), "set_xy2": _drawing_setter("line", "x2", "y2"),
        "set_color": _drawing_setter("line", "color"), "set_width": _drawing_setter("line", "width"),
        "set_style": _drawing_setter("line", "style"), "set_extend": _drawing_setter("line", "extend"),
        "set_xloc": _drawing_setter("line", "x1", "x2", "xloc"),
        "get_x1": _drawing_getter("x1"), "get_y1": _drawing_getter("y1"), "get_x2": _drawing_getter("x2"),
        "get_y2": _drawing_getter("y2"), "get_price": _line_price, "delete": _delete,
    },
    "box": {
        "set_left": _drawing_setter("box", "left"), "set_top": _drawing_setter("box", "top"),
        "set_right": _drawing_setter("box", "right"), "set_bottom": _drawing_setter("box", "bottom"),
        "set_lefttop": _drawing_setter("box", "left", "top"), "set_rightbottom": _drawing_setter("box", "right", "bottom"),
        "set_bgcolor": _drawing_setter("box", "bgcolor"), "set_border_color": _drawing_setter("box", "border_color"),
        "set_text": _drawing_setter("box", "text"), "set_extend": _drawing_setter("box", "extend"),
        "get_left": _drawing_getter("left"), "get_top": _drawing_getter("top"), "get_right": _drawing_getter("right"),
        "get_bottom": _drawing_getter("bottom"), "delete": _delete,
    },
    "table": {"cell": _table_cell, "delete": _delete, "clear": lambda ctx, t, *a: t.fields["cells"].clear()},
    "linefill": {"delete": _delete},
}


def method(kind: str | None, name: str) -> Callable[..., Any] | None:
    if kind == "array":
        function = ARRAY_METHODS.get(name)
    elif kind == "map":
        function = MAP_METHODS.get(name)
    elif kind == "str":
        function = STR_METHODS.get(name)
    elif kind in DRAWING_METHODS:
        return DRAWING_METHODS[kind].get(name)
    else:
        return None
    if function is None:
        return None
    return lambda ctx, *args, **kwargs: function(*args, **kwargs)


def _namespace_function(kind: str, name: str) -> Factory:
    def factory(c: Any, node: Call) -> Closure:
        closures = [c.expression(arg) for arg in node.args]
        named = {key: c.expression(value) for key, value in node.kwargs.items()}
        function = method(kind, name)
        assert function is not None

        def call(ctx: Context) -> Any:
            return function(ctx, *[closure(ctx) for closure in closures], **{key: value(ctx) for key, value in named.items()})

        return call

    return factory


# Outputs


def _literal(node: Node | None) -> Any:
    """The value of a constant argument (literal, color, -literal, or a named constant such as shape.circle)."""
    if node is None:
        return None
    if isinstance(node, Literal):
        return node.value
    if isinstance(node, ColorLiteral):
        return node.value
    if isinstance(node, Unary) and node.op == "-" and isinstance(node.operand, Literal) and isinstance(node.operand.value, int | float):
        return -node.operand.value
    if isinstance(node, Name):
        return _constant(node.name)
    if isinstance(node, TupleExpr):
        items = [_literal(item) for item in node.items]
        return _MISSING if any(item is _MISSING for item in items) else items
    return _MISSING


_MISSING = object()


_MAIN_ARGUMENTS = {
    "plotcandle": ("open", "high", "low", "close"),
    "plotbar": ("open", "high", "low", "close"),
    "bgcolor": ("color",),
    "barcolor": ("color",),
    "alertcondition": ("condition",),
}


def _store(values: list[Any], t: int, value: Any) -> None:
    if len(values) <= t:
        values.extend([None] * (t - len(values) + 1))
    values[t] = value


def _output(kind: str, spec: str) -> Factory:
    params, _ = _spec(spec)
    main_keys = _MAIN_ARGUMENTS.get(kind, ("series",))

    def factory(c: Any, node: Call) -> Closure:
        if c.scope.parent is not None or c.function_depth:
            raise ScriptSyntaxError(f"{node.callee}() can only be used at the top level of a script", node.line)
        if len(node.args) > len(params):
            raise ScriptSyntaxError(f"{node.callee}() takes at most {len(params)} arguments", node.line)
        arguments: dict[str, Node] = dict(zip(params, node.args, strict=False))
        for key, value in node.kwargs.items():
            if key not in params:
                raise ScriptSyntaxError(f"{node.callee}() has no argument {key!r}", node.line)
            arguments[key] = value
        missing = [key for key in main_keys if key not in arguments]
        if missing:
            raise ScriptSyntaxError(f"{node.callee}() needs a value for {missing[0]!r}", node.line)
        title_value = _literal(arguments.get("title"))
        title = str(title_value) if isinstance(title_value, str) else f"{kind} {len(c.plot_specs) + 1}"
        options: dict[str, Any] = {}
        dynamic: dict[str, Closure] = {}
        for key, arg in arguments.items():
            if key == "title" or key in main_keys:
                continue
            value = _literal(arg)
            if value is _MISSING:
                dynamic[key] = c.expression(arg)
            else:
                options[key] = value
        if len(c.plot_specs) >= 64:
            raise ScriptLimitError("a script has at most 64 plots", node.line)
        index = len(c.plot_specs)
        c.plot_specs.append((kind, title, options))
        main = [c.expression(arguments[key]) for key in main_keys]
        single = main[0] if len(main) == 1 else None

        def emit(ctx: Context) -> Any:
            run = ctx.run
            plot = run.plots[index]
            t = run.t
            value = single(ctx) if single is not None else tuple(closure(ctx) for closure in main)
            _store(plot.values, t, value)
            if dynamic:
                if plot.colors is None:
                    plot.colors = []
                _store(plot.colors, t, {key: closure(ctx) for key, closure in dynamic.items()})
            if kind == "alertcondition" and truthy(value) and t == len(run.close) - 1:
                run.alerts.append({"kind": "alertcondition", "title": plot.title, "bar": t, "message": plot.options.get("message")})
                if len(run.alerts) > run.limits.max_alerts:
                    del run.alerts[0]
            return index

        return emit

    return factory


def _hline(c: Any, node: Call) -> Closure:
    params = ["price", "title", "color", "linestyle", "linewidth", "editable", "display"]
    arguments: dict[str, Node] = dict(zip(params, node.args, strict=False))
    arguments.update(node.kwargs)
    price = c.expression(arguments["price"]) if "price" in arguments else None
    if price is None:
        raise ScriptSyntaxError("hline() needs a price", node.line)
    options = {key: _literal(value) for key, value in arguments.items() if key != "price"}
    options = {key: value for key, value in options.items() if value is not _MISSING}

    def emit(ctx: Context) -> Any:
        # Drawn once: recorded on the first bar (fill() reads the handle there too).
        run = ctx.run
        if run.statics_done:
            return ("hline", None)
        run.hlines.append({"price": price(ctx), **options})
        return ("hline", len(run.hlines) - 1)

    return emit


def _fill(c: Any, node: Call) -> Closure:
    params = ["plot1", "plot2", "color", "title", "editable", "show_last", "fillgaps", "display"]
    arguments: dict[str, Node] = dict(zip(params, node.args, strict=False))
    arguments.update(node.kwargs)
    first, second = c.expression(arguments["plot1"]), c.expression(arguments["plot2"])
    options = {key: _literal(value) for key, value in arguments.items() if key not in ("plot1", "plot2")}
    options = {key: value for key, value in options.items() if value is not _MISSING}

    def emit(ctx: Context) -> Any:
        run = ctx.run
        if not run.statics_done:
            run.fills.append({"from": first(ctx), "to": second(ctx), **options})
        return None

    return emit


def _alert(c: Any, node: Call) -> Closure:
    closures = _bind(c, node, ["message", "freq"], {"freq": "alert.freq_once_per_bar"})

    def emit(ctx: Context) -> Any:
        run = ctx.run
        message = closures[0](ctx)
        run.alerts.append({"kind": "alert", "bar": run.t, "message": message if not isinstance(message, str) else check_string(message), "freq": closures[1](ctx)})
        if len(run.alerts) > run.limits.max_alerts:
            del run.alerts[0]
        return None

    return emit


def _declaration(kind: str) -> Factory:
    params = ["title", "shorttitle", "overlay", "format", "precision", "scale", "max_bars_back", "timeframe", "timeframe_gaps",
              "explicit_plot_zorder", "max_lines_count", "max_labels_count", "max_boxes_count", "calc_bars_count",
              "max_polylines_count", "dynamic_requests", "behind_chart"]

    def factory(c: Any, node: Call) -> Closure:
        if kind != "indicator":
            raise ScriptUnsupportedError(f"{kind}() scripts are not supported yet: Omnix Scripts runs indicators", node.line)
        if c.declaration:
            raise ScriptSyntaxError("a script has one indicator() declaration", node.line)
        arguments: dict[str, Node] = dict(zip(params, node.args, strict=False))
        arguments.update(node.kwargs)
        declaration: dict[str, Any] = {"kind": kind, "overlay": False}
        for key, value in arguments.items():
            literal = _literal(value)
            if literal is _MISSING:
                raise ScriptSyntaxError(f"indicator() takes constant values; {key!r} isn't one", node.line)
            declaration[key] = literal
        if "title" not in declaration:
            raise ScriptSyntaxError("indicator() needs a title", node.line)
        if declaration.get("timeframe"):
            raise ScriptSyntaxError("indicator(timeframe=...) is not supported yet", node.line)
        c.declaration = declaration
        return lambda ctx: None

    return factory


# Inputs


INPUT_SPECS = {
    "input": ("any", "defval, title=na, tooltip=na, inline=na, group=na, display=na"),
    "input.int": ("int", "defval, title=na, minval=na, maxval=na, step=na, tooltip=na, inline=na, group=na, confirm=false, options=na, display=na, active=true"),
    "input.float": ("float", "defval, title=na, minval=na, maxval=na, step=na, tooltip=na, inline=na, group=na, confirm=false, options=na, display=na, active=true"),
    "input.bool": ("bool", "defval, title=na, tooltip=na, inline=na, group=na, confirm=false, display=na, active=true"),
    "input.string": ("string", "defval, title=na, options=na, tooltip=na, inline=na, group=na, confirm=false, display=na, active=true"),
    "input.color": ("color", "defval, title=na, tooltip=na, inline=na, group=na, confirm=false, display=na, active=true"),
    "input.source": ("source", "defval, title=na, tooltip=na, inline=na, group=na, display=na, confirm=false, active=true"),
    "input.timeframe": ("timeframe", "defval, title=na, options=na, tooltip=na, inline=na, group=na, confirm=false, display=na, active=true"),
    "input.symbol": ("symbol", "defval, title=na, tooltip=na, inline=na, group=na, confirm=false, display=na, active=true"),
    "input.session": ("session", "defval, title=na, options=na, tooltip=na, inline=na, group=na, confirm=false, display=na, active=true"),
    "input.price": ("price", "defval, title=na, tooltip=na, inline=na, group=na, confirm=false, display=na, active=true"),
    "input.time": ("time", "defval, title=na, tooltip=na, inline=na, group=na, confirm=false, display=na, active=true"),
    "input.text_area": ("text_area", "defval, title=na, tooltip=na, group=na, confirm=false, display=na, active=true"),
}


def _input(name: str) -> Factory:
    kind, spec = INPUT_SPECS[name]
    params, _ = _spec(spec)

    def factory(c: Any, node: Call) -> Closure:
        arguments: dict[str, Node] = dict(zip(params, node.args, strict=False))
        for key, value in node.kwargs.items():
            if key not in params:
                raise ScriptSyntaxError(f"{name}() has no argument {key!r}", node.line)
            arguments[key] = value
        if "defval" not in arguments:
            raise ScriptSyntaxError(f"{name}() needs a default value", node.line)
        default_node = arguments["defval"]
        options: dict[str, Any] = {}
        for key, value in arguments.items():
            if key in ("defval", "title"):
                continue
            literal = _literal(value)
            if key == "options" and not isinstance(literal, list) and literal is _MISSING:
                literal = [_literal(item) for item in getattr(value, "items", [])]
            if literal is not _MISSING and literal is not None:
                options[key] = literal
        title_value = _literal(arguments.get("title"))
        title = str(title_value) if isinstance(title_value, str) else f"input {len(c.inputs) + 1}"
        source = kind == "source" or (kind == "any" and isinstance(default_node, Name) and default_node.name in SERIES_NAMES)
        if source:
            if not (isinstance(default_node, Name) and default_node.name in SERIES_NAMES):
                raise ScriptSyntaxError(f"{name}() takes a built-in series (close, hl2, ...) as its default", node.line)
            default = default_node.name
            c.inputs.append(ScriptInput(title, "source", default, options))

            def read_source(ctx: Context) -> Any:
                run = ctx.run
                chosen = run.inputs.get(title, default)
                if chosen not in SERIES_NAMES:
                    raise ScriptRuntimeError(f"input {title!r} must be a built-in series, got {chosen!r}", node.line)
                return run.series(chosen, run.t)

            return read_source
        default = _literal(default_node)
        if default is _MISSING:
            raise ScriptSyntaxError(f"{name}() takes a constant default value", node.line)
        if kind == "int" and isinstance(default, float) and default.is_integer():
            default = int(default)
        inferred = {bool: "bool", int: "int", float: "float", str: "string"}.get(type(default), "any")
        c.inputs.append(ScriptInput(title, kind if kind != "any" else inferred, default, options))
        return lambda ctx: ctx.run.inputs.get(title, default)

    return factory


# Variables


def _calendar(field: str) -> Callable[[int], Any]:
    def read(milliseconds: Any) -> Any:
        if _na(milliseconds):
            return None
        moment = datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)
        if field == "dayofweek":
            return (moment.isoweekday() % 7) + 1  # Pine: Sunday = 1
        if field == "weekofyear":
            return moment.isocalendar()[1]
        return getattr(moment, {"dayofmonth": "day"}.get(field, field))

    return read


def _calendar_function(field: str) -> Factory:
    read = _calendar(field)
    return pure("time, timezone=na", lambda value, zone: read(value))


_CALENDAR_FIELDS = ("year", "month", "weekofyear", "dayofmonth", "dayofweek", "hour", "minute", "second")

_CONSTANT_NAMESPACES = (
    "shape.", "location.", "size.", "plot.style_", "line.style_", "label.style_", "extend.", "position.", "display.",
    "format.", "xloc.", "yloc.", "text.align_", "text.wrap_", "text.format_", "hline.style_", "barmerge.", "alert.freq_",
    "order.", "font.", "currency.", "scale.", "adjustment.", "session.", "settlement_as_close.", "backadjustment.",
)

_NAMED_CONSTANTS: dict[str, Any] = {
    "math.pi": math.pi, "math.e": math.e, "math.phi": (1 + math.sqrt(5)) / 2, "math.rphi": 2 / (1 + math.sqrt(5)),
    "dayofweek.sunday": 1, "dayofweek.monday": 2, "dayofweek.tuesday": 3, "dayofweek.wednesday": 4,
    "dayofweek.thursday": 5, "dayofweek.friday": 6, "dayofweek.saturday": 7,
    "na": None,
}


def _constant(name: str) -> Any:
    if name in _NAMED_CONSTANTS:
        return _NAMED_CONSTANTS[name]
    if name.startswith("color.") and name[6:] in COLORS:
        return COLORS[name[6:]]
    if name.startswith(_CONSTANT_NAMESPACES):
        return name
    return _MISSING


def _timeframe_value(name: str, timeframe: str) -> Any:
    unit = timeframe[-1:] if timeframe and not timeframe.isdigit() else ""
    number = timeframe[:-1] if unit else timeframe
    multiplier = int(number) if number.isdigit() else 1
    if name == "timeframe.period":
        return timeframe
    if name == "timeframe.multiplier":
        return multiplier
    if name == "timeframe.isintraday":
        return unit in ("", "S")
    if name == "timeframe.isdaily":
        return unit == "D"
    if name == "timeframe.isweekly":
        return unit == "W"
    if name == "timeframe.ismonthly":
        return unit == "M"
    if name == "timeframe.isdwm":
        return unit in ("D", "W", "M")
    if name == "timeframe.isseconds":
        return unit == "S"
    if name == "timeframe.isminutes":
        return unit == ""
    return _MISSING


def builtin_variable(c: Any, node: Name) -> Closure | None:
    name = node.name
    if name == "close":
        return lambda ctx: ctx.run.close[ctx.run.t]
    if name == "open":
        return lambda ctx: ctx.run.open[ctx.run.t]
    if name == "high":
        return lambda ctx: ctx.run.high[ctx.run.t]
    if name == "low":
        return lambda ctx: ctx.run.low[ctx.run.t]
    if name == "volume":
        return lambda ctx: ctx.run.volume[ctx.run.t]
    if name == "bar_index":
        return lambda ctx: ctx.run.t
    if name in SERIES_NAMES:
        return lambda ctx: ctx.run.series(name, ctx.run.t)
    if name in ("last_bar_index", "last_bar_time", "barstate.islast", "barstate.islastconfirmedhistory", "barstate.isrealtime"):
        c.uses_last_bar = True
    if name == "last_bar_index":
        return lambda ctx: ctx.run.last_bar_index
    if name == "last_bar_time":
        return lambda ctx: ctx.run.time[-1]
    if name.startswith("barstate."):
        state = name[9:]
        if state == "isfirst":
            return lambda ctx: ctx.run.t == 0
        if state in ("islast", "islastconfirmedhistory"):
            return lambda ctx: ctx.run.t == len(ctx.run.close) - 1
        if state in ("isconfirmed", "ishistory", "isnew"):
            return lambda ctx: True
        if state == "isrealtime":
            return lambda ctx: False
        return None
    if name in _CALENDAR_FIELDS:
        read = _calendar(name)
        return lambda ctx: read(ctx.run.time[ctx.run.t])
    if name.startswith("syminfo."):
        field = name[8:]
        if field in ("tickerid", "ticker", "root", "description"):
            return lambda ctx: ctx.run.symbol
        if field == "mintick":
            return lambda ctx: 0.01
        if field == "timezone":
            return lambda ctx: "UTC"
        if field in ("type", "currency", "prefix", "basecurrency", "session"):
            return lambda ctx: None
        return None
    if name.startswith("timeframe."):
        if _timeframe_value(name, "60") is _MISSING:
            return None
        return lambda ctx: _timeframe_value(name, ctx.run.timeframe)
    if name == "ta.tr":
        return _site_closure(node.id, lambda state, h, l, cl: ta.tr(state, h, l, cl, False), [], _hlc)
    if name == "ta.obv":
        return _site_closure(node.id, ta.obv, [], lambda run, t: (run.close[t], run.volume[t]))
    if name == "ta.vwap":
        return _site_closure(node.id, ta.vwap, [], lambda run, t: (run.series("hlc3", t), run.volume[t], run.starts[t]))
    if name == "ta.accdist":
        return _site_closure(node.id, _accdist, [], lambda run, t: (run.high[t], run.low[t], run.close[t], run.volume[t]))
    constant = _constant(name)
    if constant is not _MISSING:
        return lambda ctx: constant
    return None


def _accdist(state: Any, high: Any, low: Any, close: Any, volume: Any) -> tuple[Any, Any]:
    flow = 0.0 if high == low else ((close - low) - (high - close)) / (high - low) * volume
    return ta.cum(state, flow)


def _fixnan(state: Any, value: Any) -> tuple[Any, Any]:
    return (state, state) if _na(value) else (value, value)


def _vwap_function(c: Any, node: Call) -> Closure:
    closures = _bind(c, node, ["source", "anchor", "stdev_mult"], {"anchor": None, "stdev_mult": None})
    source, anchor = closures[0], closures[1]
    has_anchor = len(node.args) > 1 or "anchor" in node.kwargs
    if len(node.args) > 2 or "stdev_mult" in node.kwargs:
        raise ScriptSyntaxError("ta.vwap() bands (stdev_mult) are not supported yet", node.line)

    def step(state: Any, value: Any, volume: Any, start: datetime, reset: Any) -> tuple[Any, Any]:
        if has_anchor:
            # A custom anchor: a new period starts on each bar where it is true.
            period = (state[0] + 1 if state else 0) if truthy(reset) else (state[0] if state else 0)
            inner = (period, state[1], state[2]) if state and state[0] == period else (period, 0.0, 0.0)
            if _na(value) or _na(volume):
                return inner, None
            price_volume = inner[1] + value * volume
            total_volume = inner[2] + volume
            return (period, price_volume, total_volume), value if total_volume == 0 else price_volume / total_volume
        return ta.vwap(state, value, volume, start)

    def call(ctx: Context) -> Any:
        sites = ctx.sites
        state = sites.get(node.id)
        if state is None:
            state = sites[node.id] = ta.Site()
        run = ctx.run
        return state.run(run.t, step, source(ctx), run.volume[run.t], run.starts[run.t], anchor(ctx))

    return call


def _runtime_error(message: Any) -> None:
    raise ScriptRuntimeError(str(message))


def _timeframe_change(c: Any, node: Call) -> Closure:
    closures = _bind(c, node, ["timeframe"], {})
    period = closures[0]

    def key(start: datetime, timeframe: Any) -> Any:
        if timeframe in ("D", "1D"):
            return start.date()
        if timeframe in ("W", "1W"):
            return start.isocalendar()[:2]
        if timeframe in ("M", "1M"):
            return (start.year, start.month)
        raise ScriptRuntimeError(f"timeframe.change() supports D, W and M, not {timeframe!r}", node.line)

    def call(ctx: Context) -> Any:
        run = ctx.run
        t = run.t
        if t == 0:
            return True
        timeframe = period(ctx)
        return key(run.starts[t], timeframe) != key(run.starts[t - 1], timeframe)

    return call


def _log(level: str, message: Any) -> None:
    """log.info/warning/error: kept on the run for the editor's console (TVP-11.2)."""
    run = CURRENT_RUN.get()
    if run is not None:
        run.log(level, message)


FUNCTIONS: dict[str, Factory] = {
    # ta
    "ta.sma": site("source, length", ta.sma),
    "ta.ema": site("source, length", ta.ema),
    "ta.rma": site("source, length", ta.rma),
    "ta.wma": site("source, length", ta.wma),
    "ta.hma": site("source, length", ta.hma),
    "ta.rsi": site("source, length", ta.rsi),
    "ta.atr": site("length", lambda s, h, l, c, n: ta.atr(s, h, l, c, n), _hlc),
    "ta.tr": site("handle_na=false", lambda s, h, l, c, handle: ta.tr(s, h, l, c, truthy(handle)), _hlc),
    "ta.stdev": site("source, length, biased=true", ta.stdev),
    "ta.variance": site("source, length, biased=true", ta.variance),
    "ta.dev": site("source, length", ta.dev),
    "ta.highest": site_with_optional_source("source, length", ta.highest, "high"),
    "ta.lowest": site_with_optional_source("source, length", ta.lowest, "low"),
    "ta.highestbars": site_with_optional_source("source, length", ta.highestbars, "high"),
    "ta.lowestbars": site_with_optional_source("source, length", ta.lowestbars, "low"),
    "ta.pivothigh": site_with_optional_source("source, leftbars, rightbars", ta.pivothigh, "high"),
    "ta.pivotlow": site_with_optional_source("source, leftbars, rightbars", ta.pivotlow, "low"),
    "ta.change": site("source, length=1", ta.change),
    "ta.mom": site("source, length", ta.change),
    "ta.roc": site("source, length", ta.roc),
    "ta.crossover": site("source1, source2", ta.crossover),
    "ta.crossunder": site("source1, source2", ta.crossunder),
    "ta.cross": site("source1, source2", ta.any_cross),
    "ta.stoch": site("source, high, low, length", ta.stoch),
    "ta.cum": site("source", ta.cum),
    "ta.macd": site("source, fastlen, slowlen, siglen", ta.macd),
    "ta.bb": site("series, length, mult", ta.bb),
    "ta.bbw": site("series, length, mult", lambda s, v, n, m: (lambda r: (r[0], None if r[1][0] in (None, 0) or r[1][1] is None else (r[1][1] - r[1][2]) / r[1][0] * 100))(ta.bb(s, v, n, m))),
    "ta.kc": site("series, length, mult, useTrueRange=true", lambda s, h, l, c, v, n, m, u: ta.kc(s, v, h, l, c, n, m, u), _hlc),
    "ta.linreg": site("source, length, offset=0", ta.linreg),
    "ta.correlation": site("source1, source2, length", ta.correlation),
    "ta.median": site("source, length", ta.median),
    "ta.percentrank": site("source, length", ta.percentrank),
    "ta.rising": site("source, length", ta.rising),
    "ta.falling": site("source, length", ta.falling),
    "ta.barssince": site("condition", ta.barssince),
    "ta.valuewhen": site("condition, source, occurrence", ta.valuewhen),
    "ta.cci": site("source, length", ta.cci),
    "ta.mfi": site("series, length", lambda s, vol, v, n: ta.mfi(s, v, vol, n), lambda run, t: (run.volume[t],)),
    "ta.dmi": site("diLength, adxSmoothing", ta.dmi, _hlc),
    "ta.supertrend": site("factor, atrPeriod", ta.supertrend, _hlc),
    "ta.sar": site("start, inc, max", ta.sar, _hlc),
    "ta.vwap": _vwap_function,
    "math.sum": site("source, length", ta.math_sum),
    "fixnan": site("source", _fixnan),
    # math
    "math.abs": pure("number", _number_or_na(abs)),
    "math.sqrt": pure("number", _number_or_na(math.sqrt)),
    "math.log": pure("number", _number_or_na(math.log)),
    "math.log10": pure("number", _number_or_na(math.log10)),
    "math.exp": pure("number", _number_or_na(math.exp)),
    "math.pow": pure("base, exponent", _number_or_na(math.pow)),
    "math.floor": pure("number", _number_or_na(math.floor)),
    "math.ceil": pure("number", _number_or_na(math.ceil)),
    "math.round": pure("number, precision=na", _round),
    "math.round_to_mintick": pure("number", lambda value: None if _na(value) else _round(value / 0.01) * 0.01),
    "math.sign": pure("number", _sign),
    "math.sin": pure("angle", _number_or_na(math.sin)),
    "math.cos": pure("angle", _number_or_na(math.cos)),
    "math.tan": pure("angle", _number_or_na(math.tan)),
    "math.asin": pure("number", _number_or_na(math.asin)),
    "math.acos": pure("number", _number_or_na(math.acos)),
    "math.atan": pure("number", _number_or_na(math.atan)),
    "math.todegrees": pure("radians", _number_or_na(math.degrees)),
    "math.toradians": pure("degrees", _number_or_na(math.radians)),
    "math.max": variadic(_max),
    "math.min": variadic(_min),
    "math.avg": variadic(_avg),
    "nz": pure("source, replacement=0", _nz),
    "na": pure("x", _na),
    "int": pure("x", _int),
    "float": pure("x", _float),
    "bool": pure("x", _bool),
    # color
    "color.new": pure("color, transp", _color_new),
    "color.rgb": pure("red, green, blue, transp=0", _color_rgb),
    "color.from_gradient": pure("value, bottom_value, top_value, bottom_color, top_color", _color_from_gradient),
    "color.r": pure("color", _channel(0)),
    "color.g": pure("color", _channel(1)),
    "color.b": pure("color", _channel(2)),
    "color.t": pure("color", _channel(3)),
    # str
    "str.tostring": pure("value, format=\"\"", _tostring),
    "str.format": variadic(_format),
    "str.length": pure("string", STR_METHODS["length"]),
    "str.contains": pure("source, str", STR_METHODS["contains"]),
    "str.startswith": pure("source, str", STR_METHODS["startswith"]),
    "str.endswith": pure("source, str", STR_METHODS["endswith"]),
    "str.pos": pure("source, str", STR_METHODS["pos"]),
    "str.upper": pure("source", STR_METHODS["upper"]),
    "str.lower": pure("source", STR_METHODS["lower"]),
    "str.trim": pure("source", STR_METHODS["trim"]),
    "str.substring": pure("source, begin_pos, end_pos=na", _substring),
    "str.replace": pure("source, target, replacement, occurrence=0", _replace),
    "str.replace_all": pure("source, target, replacement", STR_METHODS["replace_all"]),
    "str.split": pure("string, separator", _split),
    "str.tonumber": pure("string", _tonumber),
    "str.repeat": pure("source, repeat, separator=\"\"", STR_METHODS["repeat"]),
    # time
    **{name: _calendar_function(name) for name in _CALENDAR_FIELDS},
    "timeframe.change": _timeframe_change,
    # outputs
    "plot": _output("plot", "series, title, color, linewidth, style, trackprice, histbase, offset, join, editable, show_last, display, format, precision, force_overlay, linestyle"),
    "plotshape": _output("plotshape", "series, title, style, location, color, offset, text, textcolor, editable, size, show_last, display, format, precision, force_overlay"),
    "plotchar": _output("plotchar", "series, title, char, location, color, offset, text, textcolor, editable, size, show_last, display, format, precision, force_overlay"),
    "plotarrow": _output("plotarrow", "series, title, colorup, colordown, offset, minheight, maxheight, editable, show_last, display, format, precision, force_overlay"),
    "plotcandle": _output("plotcandle", "open, high, low, close, title, color, wickcolor, editable, show_last, bordercolor, display, format, precision, force_overlay"),
    "plotbar": _output("plotbar", "open, high, low, close, title, color, editable, show_last, display, format, precision, force_overlay"),
    "bgcolor": _output("bgcolor", "color, offset, editable, show_last, title, display, force_overlay"),
    "barcolor": _output("barcolor", "color, offset, editable, show_last, title, display"),
    "alertcondition": _output("alertcondition", "condition, title, message"),
    "hline": _hline,
    "fill": _fill,
    "alert": _alert,
    "indicator": _declaration("indicator"),
    "strategy": _declaration("strategy"),
    "library": _declaration("library"),
    "runtime.error": pure("message", _runtime_error),
    "log.info": pure("message", lambda message: _log("info", message)),
    "log.warning": pure("message", lambda message: _log("warning", message)),
    "log.error": pure("message", lambda message: _log("error", message)),
    # arrays and maps
    "array.from": variadic(_array_from),
    "array.new": pure("size=0, initial_value=na", _array_new()),
    "array.new_float": pure("size=0, initial_value=na", _array_new()),
    "array.new_int": pure("size=0, initial_value=na", _array_new()),
    "array.new_bool": pure("size=0, initial_value=false", _array_new(False)),
    "array.new_string": pure("size=0, initial_value=na", _array_new()),
    "array.new_color": pure("size=0, initial_value=na", _array_new()),
    "array.new_line": pure("size=0, initial_value=na", _array_new()),
    "array.new_label": pure("size=0, initial_value=na", _array_new()),
    "array.new_box": pure("size=0, initial_value=na", _array_new()),
    "array.new_table": pure("size=0, initial_value=na", _array_new()),
    "map.new": variadic(lambda: ScriptMap()),
    "label.new": _drawing_factory("label"),
    "line.new": _drawing_factory("line"),
    "box.new": _drawing_factory("box"),
    "table.new": _drawing_factory("table"),
    "linefill.new": _drawing_factory("linefill"),
}
FUNCTIONS["ta.vwma"] = site("source, length", lambda s, vol, v, n: ta.vwma(s, v, vol, n), lambda run, t: (run.volume[t],))
for _name in INPUT_SPECS:
    FUNCTIONS[_name] = _input(_name)
for _name in ARRAY_METHODS:
    FUNCTIONS.setdefault(f"array.{_name}", _namespace_function("array", _name))
for _name in MAP_METHODS:
    FUNCTIONS.setdefault(f"map.{_name}", _namespace_function("map", _name))
for _kind, _methods in DRAWING_METHODS.items():
    for _name in _methods:
        FUNCTIONS.setdefault(f"{_kind}.{_name}", _namespace_function(_kind, _name))


def builtin_function(name: str) -> Factory | None:
    return FUNCTIONS.get(name)
