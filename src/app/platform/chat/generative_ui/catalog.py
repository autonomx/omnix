"""The V1 block catalog: shapes, limits, normalization and text/speech projections.

The Pydantic models are the source of truth for what a stored block looks like;
the web app mirrors them in zod (``generative-ui/schema.ts``) and both are checked
against the shared golden fixtures in ``resources/chat/generative_ui/fixtures``.

Model output is normalized leniently: unknown props are dropped, over-long strings
are truncated and invalid list items are removed, each with a diagnostic. A block
whose required parts are unusable is rejected and the compiler shows its text
fallback instead (``BlockRejected``).
"""
from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

# --- Limits (roadmap §7.3) -------------------------------------------------

MAX_BLOCKS = 8
MAX_BLOCK_BYTES = 32 * 1024
MAX_PAYLOAD_BYTES = 128 * 1024
MAX_SERIES = 6
MAX_POINTS = 2_000
MAX_STATS_ITEMS = 6
MAX_CHOICE_OPTIONS = 6
MIN_CHOICE_OPTIONS = 2
MAX_CHOICE_LABEL = 160
MAX_FORM_FIELDS = 8
MAX_FORM_TEMPLATE = 500
MAX_SELECT_OPTIONS = 20
MAX_TEXT_FIELD = 200
MAX_SOURCES = 12
MAX_STRING = 2_000
MAX_LABEL = 120

Severity = Literal["info", "dropped", "degraded"]
Trend = Literal["up", "down", "flat"]
Tone = Literal["neutral", "positive", "negative", "warning", "info"]
Size = Literal["sm", "md", "lg"]
Provenance = Literal["model", "bound", "market_data"]
ChartKind = Literal["line", "area", "bar"]
AxisType = Literal["time", "category"]
NumberFormat = Literal["number", "percent", "currency", "compact"]
PriceInterval = Literal["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]
PriceRange = Literal["1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "5Y", "MAX"]
FieldKind = Literal["select", "slider", "text", "toggle"]

BLOCK_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
FIELD_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
SYMBOL = re.compile(r"^[A-Z0-9^][A-Z0-9.\-:/^=]{0,31}$")
TEMPLATE_PLACEHOLDER = re.compile(r"\{([A-Za-z][A-Za-z0-9_]{0,31})\}")
BINDING_REF = re.compile(r"^(source|context):([A-Za-z0-9_.:-]{1,80}?)(?:\.(title|url|citation))?$")
# Keys a choices option may not carry: the label is the message (GUI-5.1).
SEPARATE_MESSAGE_KEYS = frozenset({"message", "value", "send", "text", "prompt", "payload", "action", "content"})

_STRICT = ConfigDict(extra="forbid", frozen=True)


# --- Stored shape ------------------------------------------------------------

class Binding(BaseModel):
    """A value frozen from turn data at compile time (GUI-4.1)."""

    model_config = _STRICT
    path: str
    ref: str
    title: str
    url: str | None = None


class StatItem(BaseModel):
    model_config = _STRICT
    label: str = Field(min_length=1, max_length=MAX_LABEL)
    value: str = Field(min_length=1, max_length=MAX_LABEL)
    delta: str | None = Field(default=None, max_length=MAX_LABEL)
    trend: Trend | None = None
    tone: Tone | None = None
    hint: str | None = Field(default=None, max_length=MAX_STRING)


class StatsBlock(BaseModel):
    model_config = _STRICT
    type: Literal["stats"]
    id: str
    v: Literal[1] = 1
    title: str | None = Field(default=None, max_length=MAX_LABEL)
    items: list[StatItem] = Field(min_length=1, max_length=MAX_STATS_ITEMS)
    provenance: Provenance
    bindings: list[Binding] = Field(default_factory=list)


class ChartAxisX(BaseModel):
    model_config = _STRICT
    type: AxisType
    label: str | None = Field(default=None, max_length=MAX_LABEL)


class ChartAxisY(BaseModel):
    model_config = _STRICT
    label: str | None = Field(default=None, max_length=MAX_LABEL)
    format: NumberFormat = "number"


class ChartSeries(BaseModel):
    model_config = _STRICT
    name: str = Field(min_length=1, max_length=MAX_LABEL)
    # Time axes hold UTC epoch seconds; category axes hold labels.
    points: list[tuple[int | str, float]] = Field(min_length=1, max_length=MAX_POINTS)


class ChartBlock(BaseModel):
    model_config = _STRICT
    type: Literal["chart"]
    id: str
    v: Literal[1] = 1
    kind: ChartKind
    title: str | None = Field(default=None, max_length=MAX_LABEL)
    size: Size = "md"
    x: ChartAxisX
    y: ChartAxisY
    series: list[ChartSeries] = Field(min_length=1, max_length=MAX_SERIES)
    provenance: Provenance
    bindings: list[Binding] = Field(default_factory=list)


class PriceChartBlock(BaseModel):
    model_config = _STRICT
    type: Literal["price_chart"]
    id: str
    v: Literal[1] = 1
    symbol: str = Field(pattern=SYMBOL.pattern)
    # The trading catalog's instrument, as the read-only bars endpoint names it.
    instrument_id: str = Field(min_length=3, max_length=200)
    interval: PriceInterval
    range: PriceRange
    title: str | None = Field(default=None, max_length=MAX_LABEL)
    as_of: str
    provenance: Literal["market_data"] = "market_data"
    bindings: list[Binding] = Field(default_factory=list)


class SourceRef(BaseModel):
    model_config = _STRICT
    ref: str
    citation: str | None = None
    title: str = Field(min_length=1, max_length=MAX_STRING)
    url: str | None = None


class SourcesBlock(BaseModel):
    model_config = _STRICT
    type: Literal["sources"]
    id: str
    v: Literal[1] = 1
    title: str | None = Field(default=None, max_length=MAX_LABEL)
    refs: list[SourceRef] = Field(min_length=1, max_length=MAX_SOURCES)
    provenance: Literal["bound"] = "bound"
    bindings: list[Binding] = Field(default_factory=list)


class ChoiceOption(BaseModel):
    model_config = _STRICT
    label: str = Field(min_length=1, max_length=MAX_CHOICE_LABEL)


class ChoicesBlock(BaseModel):
    model_config = _STRICT
    type: Literal["choices"]
    id: str
    v: Literal[1] = 1
    prompt: str | None = Field(default=None, max_length=MAX_STRING)
    options: list[ChoiceOption] = Field(min_length=MIN_CHOICE_OPTIONS, max_length=MAX_CHOICE_OPTIONS)
    provenance: Literal["model"] = "model"
    bindings: list[Binding] = Field(default_factory=list)


class FormField(BaseModel):
    model_config = _STRICT
    name: str = Field(pattern=FIELD_NAME.pattern)
    label: str = Field(min_length=1, max_length=MAX_LABEL)
    kind: FieldKind
    required: bool = False
    options: list[str] | None = Field(default=None, max_length=MAX_SELECT_OPTIONS)
    min: float | None = None
    max: float | None = None
    step: float | None = None
    unit: str | None = Field(default=None, max_length=16)
    max_length: int | None = Field(default=None, ge=1, le=MAX_TEXT_FIELD)
    placeholder: str | None = Field(default=None, max_length=MAX_LABEL)
    default: str | float | bool | None = None


class FormBlock(BaseModel):
    model_config = _STRICT
    type: Literal["form"]
    id: str
    v: Literal[1] = 1
    title: str | None = Field(default=None, max_length=MAX_LABEL)
    fields: list[FormField] = Field(min_length=1, max_length=MAX_FORM_FIELDS)
    template: str = Field(min_length=1, max_length=MAX_FORM_TEMPLATE)
    submit_label: str | None = Field(default=None, max_length=MAX_LABEL)
    provenance: Literal["model"] = "model"
    bindings: list[Binding] = Field(default_factory=list)


ChatUiBlock = Annotated[
    StatsBlock | ChartBlock | PriceChartBlock | SourcesBlock | ChoicesBlock | FormBlock,
    Field(discriminator="type"),
]


class ChatUiSegment(BaseModel):
    """One piece of a reply: a Markdown span of ``content``, a block, or fallback text."""

    model_config = _STRICT
    kind: Literal["markdown", "block", "text"]
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    id: str | None = None
    text: str | None = None


class ChatUiDiagnostic(BaseModel):
    model_config = _STRICT
    block: str | None = None
    code: str
    path: str | None = None
    severity: Severity
    detail: str | None = None


class ChatUiPayload(BaseModel):
    """``metadata.ui`` on an assistant message (roadmap §6.3)."""

    model_config = _STRICT
    version: Literal[1] = 1
    compiler_version: str
    compiled_at: str
    segments: list[ChatUiSegment]
    blocks: dict[str, ChatUiBlock]
    text: str
    speech: str
    diagnostics: list[ChatUiDiagnostic] = Field(default_factory=list)


# --- Normalization -------------------------------------------------------------

class BlockRejected(Exception):
    """A block cannot be shown; the compiler substitutes its text fallback."""

    def __init__(self, code: str, path: str | None = None, detail: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.path = path
        self.detail = detail


@dataclass(frozen=True)
class BoundSource:
    """Turn data a ``{"bind": ...}`` reference can name (GUI-4.1)."""

    ref: str
    title: str
    url: str | None = None
    citation: str | None = None


@dataclass
class NormalizeContext:
    block_id: str
    compiled_at: str
    sources: Mapping[str, BoundSource]
    # Symbol -> instrument id for symbols the market-data catalog knows; None
    # when no validation ran (price charts are then not shown).
    market_symbols: Mapping[str, str] | None
    diagnostics: list[ChatUiDiagnostic] = field(default_factory=list)
    bindings: list[Binding] = field(default_factory=list)

    def note(self, code: str, path: str | None, severity: Severity = "dropped", detail: str | None = None) -> None:
        self.diagnostics.append(
            ChatUiDiagnostic(block=self.block_id, code=code, path=path, severity=severity, detail=detail)
        )


def _join(path: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]"
    return f"{path}.{key}" if path else key


def _drop_unknown(ctx: NormalizeContext, spec: Mapping[str, Any], allowed: Iterable[str], path: str) -> None:
    known = set(allowed)
    for key in spec:
        if key not in known:
            ctx.note("unknown_prop", _join(path, str(key)))


def _resolve_binding(ctx: NormalizeContext, value: Mapping[str, Any], path: str, *, whole: bool) -> Any:
    """Resolve ``{"bind": "source:2.title"}``; ``whole`` asks for the reference itself."""
    raw = value.get("bind")
    match = BINDING_REF.match(raw.strip()) if isinstance(raw, str) else None
    if match is None or set(value) != {"bind"}:
        ctx.note("unresolved_binding", path, detail="malformed binding")
        return None
    ref = f"{match.group(1)}:{match.group(2)}"
    source = ctx.sources.get(ref)
    if source is None:
        ctx.note("unresolved_binding", path, detail=f"{ref} is not part of this turn")
        return None
    attribute = match.group(3)
    if whole != (attribute is None):
        ctx.note("binding_type_mismatch", path, detail=raw)
        return None
    if whole:
        return source
    resolved = getattr(source, attribute)
    if not resolved:
        ctx.note("unresolved_binding", path, detail=f"{raw} has no value")
        return None
    ctx.bindings.append(Binding(path=path, ref=ref, title=source.title, url=source.url))
    return str(resolved)


def _string(
    ctx: NormalizeContext,
    value: Any,
    path: str,
    *,
    limit: int = MAX_STRING,
    single_line: bool = False,
) -> str | None:
    """A trimmed string (numbers are accepted and formatted); None when absent or unusable."""
    if value is None:
        return None
    if isinstance(value, Mapping) and "bind" in value:
        value = _resolve_binding(ctx, value, path, whole=False)
        if value is None:
            return None
    if isinstance(value, bool):
        ctx.note("invalid_prop", path, detail="expected text")
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            ctx.note("invalid_prop", path, detail="expected a finite number")
            return None
        value = format_number(value)
    if not isinstance(value, str):
        ctx.note("invalid_prop", path, detail="expected text")
        return None
    text = " ".join(value.split()) if single_line else value.strip()
    if not text:
        return None
    if len(text) > limit:
        ctx.note("truncated", path, "info", detail=f"{len(text)} > {limit} characters")
        text = text[: limit - 1].rstrip() + "…"
    return text


def _literal(ctx: NormalizeContext, value: Any, allowed: tuple[str, ...], path: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in allowed:
        return value.strip().lower()
    ctx.note("invalid_prop", path, detail=f"expected one of {', '.join(allowed)}")
    return None


def _number(ctx: NormalizeContext, value: Any, path: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        ctx.note("invalid_prop", path, detail="expected a number")
        return None
    if isinstance(value, str):
        try:
            value = float(value.replace(",", "").strip())
        except ValueError:
            ctx.note("invalid_prop", path, detail="expected a number")
            return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    ctx.note("invalid_prop", path, detail="expected a finite number")
    return None


def _list(ctx: NormalizeContext, value: Any, path: str, *, required: bool) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is not None:
        ctx.note("invalid_prop", path, detail="expected a list")
    if required:
        raise BlockRejected("missing_prop", path)
    return []


def _capped(ctx: NormalizeContext, items: list[Any], limit: int, path: str) -> list[Any]:
    if len(items) > limit:
        ctx.note("too_many_items", path, detail=f"kept {limit} of {len(items)}")
        return items[:limit]
    return items


def _title(ctx: NormalizeContext, spec: Mapping[str, Any]) -> str | None:
    return _string(ctx, spec.get("title"), "title", limit=MAX_LABEL, single_line=True)


def _normalize_stats(spec: Mapping[str, Any], ctx: NormalizeContext) -> dict[str, Any]:
    _drop_unknown(ctx, spec, {"type", "id", "v", "title", "items"}, "")
    raw_items = _capped(ctx, _list(ctx, spec.get("items"), "items", required=True), MAX_STATS_ITEMS, "items")
    items: list[dict[str, Any]] = []
    bound_values = 0
    for index, raw in enumerate(raw_items):
        path = _join("items", index)
        if not isinstance(raw, Mapping):
            ctx.note("invalid_item", path)
            continue
        _drop_unknown(ctx, raw, {"label", "value", "delta", "trend", "tone", "hint"}, path)
        bindings_before = len(ctx.bindings)
        label = _string(ctx, raw.get("label"), _join(path, "label"), limit=MAX_LABEL, single_line=True)
        value = _string(ctx, raw.get("value"), _join(path, "value"), limit=MAX_LABEL, single_line=True)
        if label is None or value is None:
            del ctx.bindings[bindings_before:]
            ctx.note("invalid_item", path, detail="label and value are required")
            continue
        if any(binding.path == _join(path, "value") for binding in ctx.bindings[bindings_before:]):
            bound_values += 1
        item: dict[str, Any] = {"label": label, "value": value}
        delta = _string(ctx, raw.get("delta"), _join(path, "delta"), limit=MAX_LABEL, single_line=True)
        trend = _literal(ctx, raw.get("trend"), ("up", "down", "flat"), _join(path, "trend"))
        tone = _literal(ctx, raw.get("tone"), ("neutral", "positive", "negative", "warning", "info"), _join(path, "tone"))
        hint = _string(ctx, raw.get("hint"), _join(path, "hint"))
        for key, optional in (("delta", delta), ("trend", trend), ("tone", tone), ("hint", hint)):
            if optional is not None:
                item[key] = optional
        items.append(item)
    if not items:
        raise BlockRejected("no_valid_items", "items")
    block: dict[str, Any] = {"items": items, "provenance": "bound" if bound_values == len(items) else "model"}
    title = _title(ctx, spec)
    if title is not None:
        block["title"] = title
    return block


_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _time_value(value: Any) -> int | None:
    """UTC epoch seconds from an ISO date/datetime or an epoch number (seconds or milliseconds)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        seconds = value / 1000 if abs(value) >= 1e11 else value
        return int(seconds)
    if isinstance(value, str):
        text = value.strip()
        try:
            if _DATE_ONLY.match(text):
                parsed = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            else:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        return int(parsed.timestamp())
    return None


def _point(raw: Any) -> tuple[Any, Any] | None:
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        return raw[0], raw[1]
    if isinstance(raw, Mapping) and "x" in raw and "y" in raw:
        return raw["x"], raw["y"]
    return None


def _infer_axis(series: list[Any]) -> str:
    for raw_series in series:
        points = raw_series.get("points") if isinstance(raw_series, Mapping) else None
        for raw in points if isinstance(points, list) else []:
            pair = _point(raw)
            if pair is None:
                continue
            x = pair[0]
            if isinstance(x, (int, float)) and not isinstance(x, bool):
                # Epoch seconds or milliseconds; a small number such as a year is a category.
                return "time" if abs(x) >= 1e9 else "category"
            if isinstance(x, str) and _time_value(x) is not None and re.match(r"^\d{4}-\d{2}", x.strip()):
                return "time"
            return "category"
    return "category"


def lttb(points: list[tuple[int, float]], threshold: int) -> list[tuple[int, float]]:
    """Largest-Triangle-Three-Buckets downsampling of a time series (keeps first and last points)."""
    if threshold >= len(points) or threshold < 3:
        return list(points)
    sampled = [points[0]]
    bucket = (len(points) - 2) / (threshold - 2)
    anchor = 0
    for index in range(threshold - 2):
        start = int(math.floor(index * bucket)) + 1
        end = int(math.floor((index + 1) * bucket)) + 1
        next_start = end
        next_end = min(int(math.floor((index + 2) * bucket)) + 1, len(points))
        if next_start >= next_end:
            next_start, next_end = len(points) - 1, len(points)
        average_x = sum(point[0] for point in points[next_start:next_end]) / (next_end - next_start)
        average_y = sum(point[1] for point in points[next_start:next_end]) / (next_end - next_start)
        ax, ay = points[anchor]
        best, best_area = start, -1.0
        for candidate in range(start, min(end, len(points) - 1)):
            cx, cy = points[candidate]
            area = abs((ax - average_x) * (cy - ay) - (ax - cx) * (average_y - ay))
            if area > best_area:
                best, best_area = candidate, area
        sampled.append(points[best])
        anchor = best
    sampled.append(points[-1])
    return sampled


def fit_chart(block: dict[str, Any], max_bytes: int, size: Callable[[Any], int]) -> int | None:
    """Downsample a time chart's series (LTTB) until the block fits ``max_bytes``.

    Returns the per-series point cap that fit, or None when the chart cannot
    fit (a category chart, or fewer than 50 points per series would be left).
    Six series of 2,000 points do not fit the 32 KB block limit, so the byte
    limit is what bounds a large chart in practice.
    """
    if block["x"]["type"] != "time":
        return None
    longest = max(len(series["points"]) for series in block["series"])
    cap = longest
    while size(block) > max_bytes:
        cap = int(cap * 0.75)
        if cap < 50:
            return None
        for series in block["series"]:
            if len(series["points"]) > cap:
                timed = [(int(x), float(y)) for x, y in series["points"]]
                series["points"] = [[x, y] for x, y in lttb(timed, cap)]
    return cap


def _normalize_chart(spec: Mapping[str, Any], ctx: NormalizeContext) -> dict[str, Any]:
    _drop_unknown(ctx, spec, {"type", "id", "v", "kind", "title", "size", "x", "y", "series"}, "")
    kind = _literal(ctx, spec.get("kind", "line"), ("line", "area", "bar"), "kind")
    if kind is None:
        raise BlockRejected("invalid_prop", "kind")
    raw_series = _capped(ctx, _list(ctx, spec.get("series"), "series", required=True), MAX_SERIES, "series")
    raw_x: Mapping[str, Any] = spec["x"] if isinstance(spec.get("x"), Mapping) else {}
    if spec.get("x") is not None and not isinstance(spec.get("x"), Mapping):
        ctx.note("invalid_prop", "x", detail="expected an object")
    _drop_unknown(ctx, raw_x, {"type", "label"}, "x")
    axis_type = _literal(ctx, raw_x.get("type"), ("time", "category"), "x.type") or _infer_axis(raw_series)
    x_axis: dict[str, Any] = {"type": axis_type}
    x_label = _string(ctx, raw_x.get("label"), "x.label", limit=MAX_LABEL, single_line=True)
    if x_label is not None:
        x_axis["label"] = x_label
    raw_y: Mapping[str, Any] = spec["y"] if isinstance(spec.get("y"), Mapping) else {}
    if spec.get("y") is not None and not isinstance(spec.get("y"), Mapping):
        ctx.note("invalid_prop", "y", detail="expected an object")
    _drop_unknown(ctx, raw_y, {"label", "format"}, "y")
    y_axis: dict[str, Any] = {
        "format": _literal(ctx, raw_y.get("format"), ("number", "percent", "currency", "compact"), "y.format") or "number",
    }
    y_label = _string(ctx, raw_y.get("label"), "y.label", limit=MAX_LABEL, single_line=True)
    if y_label is not None:
        y_axis["label"] = y_label

    series: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_series):
        path = _join("series", index)
        if not isinstance(raw, Mapping):
            ctx.note("invalid_item", path)
            continue
        _drop_unknown(ctx, raw, {"name", "points"}, path)
        name = _string(ctx, raw.get("name"), _join(path, "name"), limit=MAX_LABEL, single_line=True) or f"Series {index + 1}"
        raw_points: list[Any] = raw["points"] if isinstance(raw.get("points"), list) else []
        invalid = 0
        if axis_type == "time":
            by_time: dict[int, float] = {}
            for raw_point in raw_points:
                pair = _point(raw_point)
                x = _time_value(pair[0]) if pair is not None else None
                y = _finite(pair[1]) if pair is not None else None
                if x is None or y is None:
                    invalid += 1
                    continue
                by_time[x] = y
            timed = sorted(by_time.items())
            if len(timed) > MAX_POINTS:
                ctx.note("downsampled", _join(path, "points"), "info", detail=f"{len(timed)} -> {MAX_POINTS} points")
                timed = lttb(timed, MAX_POINTS)
            points: list[list[Any]] = [[x, y] for x, y in timed]
        else:
            points = []
            for raw_point in raw_points:
                pair = _point(raw_point)
                label = _category(pair[0]) if pair is not None else None
                y = _finite(pair[1]) if pair is not None else None
                if label is None or y is None:
                    invalid += 1
                    continue
                points.append([label, y])
            if len(points) > MAX_POINTS:
                ctx.note("truncated", _join(path, "points"), "info", detail=f"kept {MAX_POINTS} of {len(points)} points")
                points = points[:MAX_POINTS]
        if invalid:
            ctx.note("invalid_point", _join(path, "points"), detail=f"{invalid} point(s) dropped")
        if not points:
            ctx.note("invalid_item", path, detail="no valid points")
            continue
        series.append({"name": name, "points": points})
    if not series:
        raise BlockRejected("no_valid_series", "series")
    block: dict[str, Any] = {
        "kind": kind,
        "size": _literal(ctx, spec.get("size"), ("sm", "md", "lg"), "size") or "md",
        "x": x_axis,
        "y": y_axis,
        "series": series,
        "provenance": "model",
    }
    title = _title(ctx, spec)
    if title is not None:
        block["title"] = title
    return block


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.replace(",", "").strip())
        except ValueError:
            return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _category(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            return None
        # A label keeps the number as written: a year is "2021", not "2,021".
        return str(int(value)) if float(value).is_integer() else repr(float(value))
    if isinstance(value, str):
        text = " ".join(value.split())
        return text[:MAX_LABEL] if text else None
    return None


def _normalize_price_chart(spec: Mapping[str, Any], ctx: NormalizeContext) -> dict[str, Any]:
    _drop_unknown(ctx, spec, {"type", "id", "v", "symbol", "interval", "range", "title"}, "")
    raw_symbol = spec.get("symbol")
    symbol = raw_symbol.strip().upper() if isinstance(raw_symbol, str) else ""
    if not SYMBOL.match(symbol):
        raise BlockRejected("invalid_prop", "symbol")
    interval = _literal_exact(spec.get("interval", "1d"), ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"), lower=True)
    if interval is None:
        raise BlockRejected("invalid_prop", "interval")
    range_ = _literal_exact(spec.get("range", "6M"), ("1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "5Y", "MAX"), lower=False)
    if range_ is None:
        raise BlockRejected("invalid_prop", "range")
    if ctx.market_symbols is None:
        raise BlockRejected("unverified_symbol", "symbol", detail="market data could not be checked")
    canonical = ctx.market_symbols.get(symbol)
    if canonical is None:
        raise BlockRejected("unknown_symbol", "symbol", detail=symbol)
    block: dict[str, Any] = {
        "symbol": symbol,
        "instrument_id": canonical,
        "interval": interval,
        "range": range_,
        "as_of": ctx.compiled_at,
        "provenance": "market_data",
    }
    title = _title(ctx, spec)
    if title is not None:
        block["title"] = title
    return block


def _literal_exact(value: Any, allowed: tuple[str, ...], *, lower: bool) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower() if lower else value.strip().upper()
    return text if text in allowed else None


def _normalize_sources(spec: Mapping[str, Any], ctx: NormalizeContext) -> dict[str, Any]:
    _drop_unknown(ctx, spec, {"type", "id", "v", "title", "refs"}, "")
    raw_refs = _capped(ctx, _list(ctx, spec.get("refs"), "refs", required=True), MAX_SOURCES, "refs")
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_refs):
        path = _join("refs", index)
        if isinstance(raw, str):
            raw = {"bind": raw}
        if not isinstance(raw, Mapping) or "bind" not in raw:
            ctx.note("invalid_ref", path, detail="sources must name turn data with bind")
            continue
        source = _resolve_binding(ctx, raw, path, whole=True)
        if not isinstance(source, BoundSource) or source.ref in seen:
            continue
        seen.add(source.ref)
        ref: dict[str, Any] = {"ref": source.ref, "title": source.title}
        if source.citation:
            ref["citation"] = source.citation
        if source.url and safe_url(source.url):
            ref["url"] = source.url
        refs.append(ref)
    if not refs:
        raise BlockRejected("no_valid_refs", "refs")
    block: dict[str, Any] = {"refs": refs, "provenance": "bound"}
    title = _title(ctx, spec)
    if title is not None:
        block["title"] = title
    return block


def _normalize_choices(spec: Mapping[str, Any], ctx: NormalizeContext) -> dict[str, Any]:
    _drop_unknown(ctx, spec, {"type", "id", "v", "prompt", "options"}, "")
    raw_options = _list(ctx, spec.get("options"), "options", required=True)
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_options):
        path = _join("options", index)
        if isinstance(raw, str):
            raw = {"label": raw}
        if not isinstance(raw, Mapping):
            ctx.note("option_dropped", path)
            continue
        hidden = sorted(SEPARATE_MESSAGE_KEYS.intersection(raw))
        if hidden:
            # The label is exactly what is sent; a separate message is refused (GUI-5.1).
            raise BlockRejected("separate_message_field", _join(path, hidden[0]))
        _drop_unknown(ctx, raw, {"label"}, path)
        label = raw.get("label")
        text = " ".join(label.split()) if isinstance(label, str) else ""
        if not text or len(text) > MAX_CHOICE_LABEL:
            ctx.note("option_dropped", _join(path, "label"), detail="labels are 1-160 characters")
            continue
        if text in seen:
            ctx.note("option_dropped", _join(path, "label"), detail="duplicate label")
            continue
        seen.add(text)
        options.append({"label": text})
    options = _capped(ctx, options, MAX_CHOICE_OPTIONS, "options")
    if len(options) < MIN_CHOICE_OPTIONS:
        raise BlockRejected("too_few_options", "options")
    block: dict[str, Any] = {"options": options, "provenance": "model"}
    prompt = _string(ctx, spec.get("prompt"), "prompt", single_line=True)
    if prompt is not None:
        block["prompt"] = prompt
    return block


def _normalize_field(raw: Mapping[str, Any], ctx: NormalizeContext, path: str) -> dict[str, Any] | None:
    _drop_unknown(
        ctx, raw,
        {"name", "label", "kind", "required", "options", "min", "max", "step", "unit", "max_length", "placeholder", "default"},
        path,
    )
    name = raw.get("name")
    if not isinstance(name, str) or not FIELD_NAME.match(name.strip()):
        ctx.note("invalid_field", _join(path, "name"))
        return None
    name = name.strip()
    kind = _literal(ctx, raw.get("kind"), ("select", "slider", "text", "toggle"), _join(path, "kind"))
    if kind is None:
        ctx.note("invalid_field", _join(path, "kind"))
        return None
    field_spec: dict[str, Any] = {
        "name": name,
        "label": _string(ctx, raw.get("label"), _join(path, "label"), limit=MAX_LABEL, single_line=True) or name,
        "kind": kind,
        "required": raw.get("required") is True,
    }
    default = raw.get("default")
    if kind == "select":
        raw_options: list[Any] = raw["options"] if isinstance(raw.get("options"), list) else []
        options = [
            text for text in (
                _string(ctx, option, _join(_join(path, "options"), index), limit=MAX_LABEL, single_line=True)
                for index, option in enumerate(raw_options)
            ) if text is not None
        ]
        options = list(dict.fromkeys(options))
        options = _capped(ctx, options, MAX_SELECT_OPTIONS, _join(path, "options"))
        if not options:
            ctx.note("invalid_field", _join(path, "options"), detail="a select needs options")
            return None
        field_spec["options"] = options
        if isinstance(default, str) and default in options:
            field_spec["default"] = default
    elif kind == "slider":
        minimum = _number(ctx, raw.get("min"), _join(path, "min"))
        maximum = _number(ctx, raw.get("max"), _join(path, "max"))
        if minimum is None or maximum is None or minimum >= maximum:
            ctx.note("invalid_field", path, detail="a slider needs min < max")
            return None
        step = _number(ctx, raw.get("step"), _join(path, "step"))
        field_spec.update({"min": minimum, "max": maximum, "step": step if step and step > 0 else 1.0})
        unit = _string(ctx, raw.get("unit"), _join(path, "unit"), limit=16, single_line=True)
        if unit is not None:
            field_spec["unit"] = unit
        number = _finite(default)
        if number is not None and minimum <= number <= maximum:
            field_spec["default"] = number
    elif kind == "text":
        length = raw.get("max_length")
        limit = length if isinstance(length, int) and not isinstance(length, bool) and 1 <= length <= MAX_TEXT_FIELD else MAX_TEXT_FIELD
        field_spec["max_length"] = limit
        placeholder = _string(ctx, raw.get("placeholder"), _join(path, "placeholder"), limit=MAX_LABEL, single_line=True)
        if placeholder is not None:
            field_spec["placeholder"] = placeholder
        if isinstance(default, str) and default.strip() and len(default.strip()) <= limit:
            field_spec["default"] = default.strip()
    elif isinstance(default, bool):
        field_spec["default"] = default
    return field_spec


def _normalize_form(spec: Mapping[str, Any], ctx: NormalizeContext) -> dict[str, Any]:
    _drop_unknown(ctx, spec, {"type", "id", "v", "title", "fields", "template", "submit_label"}, "")
    template = spec.get("template")
    if not isinstance(template, str) or not template.strip():
        raise BlockRejected("missing_prop", "template")
    template = template.strip()
    if len(template) > MAX_FORM_TEMPLATE:
        raise BlockRejected("template_too_long", "template", detail=f"{len(template)} > {MAX_FORM_TEMPLATE} characters")
    raw_fields = _capped(ctx, _list(ctx, spec.get("fields"), "fields", required=True), MAX_FORM_FIELDS, "fields")
    fields: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_fields):
        path = _join("fields", index)
        normalized = _normalize_field(raw, ctx, path) if isinstance(raw, Mapping) else None
        if normalized is None:
            if not isinstance(raw, Mapping):
                ctx.note("invalid_field", path)
            continue
        if any(existing["name"] == normalized["name"] for existing in fields):
            ctx.note("invalid_field", _join(path, "name"), detail="duplicate field name")
            continue
        fields.append(normalized)
    if not fields:
        raise BlockRejected("no_valid_fields", "fields")
    names = {item["name"] for item in fields}
    unknown = sorted(set(TEMPLATE_PLACEHOLDER.findall(template)) - names)
    if unknown:
        raise BlockRejected("invalid_template", "template", detail=f"unknown field(s): {', '.join(unknown)}")
    block: dict[str, Any] = {"fields": fields, "template": template, "provenance": "model"}
    title = _title(ctx, spec)
    if title is not None:
        block["title"] = title
    submit = _string(ctx, spec.get("submit_label"), "submit_label", limit=MAX_LABEL, single_line=True)
    if submit is not None:
        block["submit_label"] = submit
    return block


# --- Projections ------------------------------------------------------------------

def format_number(value: float) -> str:
    if float(value).is_integer() and abs(value) < 1e15:
        return f"{int(value):,}"
    return f"{value:,.6g}" if abs(value) >= 1e-4 else f"{value:.3g}"


_COUNT_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve")


def _count(value: int, noun: str) -> str:
    word = _COUNT_WORDS[value] if 0 <= value < len(_COUNT_WORDS) else str(value)
    return f"{word} {noun}{'' if value == 1 else 's'}"


def _spoken_delta(item: Mapping[str, Any]) -> str:
    delta = str(item.get("delta") or "").strip()
    if not delta:
        return ""
    trend = item.get("trend")
    magnitude = delta.lstrip("+-−").strip()
    if trend == "up" or (trend is None and delta.startswith("+")):
        return f", up {magnitude}"
    if trend == "down" or (trend is None and delta[:1] in {"-", "−"}):
        return f", down {magnitude}"
    return f", {delta}"


def _stats_text(block: Mapping[str, Any]) -> str:
    lines = [
        f"{item['label']}: {item['value']}"
        + (f" ({item['delta']})" if item.get("delta") else "")
        + "."
        + (f" {item['hint']}" if item.get("hint") else "")
        for item in block["items"]
    ]
    body = " ".join(lines)
    return f"{block['title']}: {body}" if block.get("title") else body


def _stats_speech(block: Mapping[str, Any]) -> str:
    items = block["items"]
    spoken = [f"{item['label']} {item['value']}{_spoken_delta(item)}" for item in items[:2]]
    if len(items) == 1:
        return f"{spoken[0]}."
    lead = _count(len(items), "headline figure")
    lead = lead[0].upper() + lead[1:]
    joined = f"{spoken[0]}; and {spoken[1]}" if len(items) == 2 else f"including {spoken[0]}; and {spoken[1]}"
    return f"{lead}: {joined}."


def _axis_label(block: Mapping[str, Any], x: Any) -> str:
    if block["x"]["type"] == "time" and isinstance(x, int):
        return datetime.fromtimestamp(x, tz=timezone.utc).strftime("%Y-%m-%d")
    return str(x)


def _formatted(block: Mapping[str, Any], value: float) -> str:
    text = format_number(value)
    fmt = block["y"].get("format")
    if fmt == "percent":
        return f"{text}%"
    if fmt == "currency":
        return f"${text}" if value >= 0 else f"-${format_number(-value)}"
    return text


def _chart_text(block: Mapping[str, Any]) -> str:
    title = block.get("title") or f"{block['kind'].capitalize()} chart"
    lines = [title]
    for series in block["series"]:
        values = [point[1] for point in series["points"]]
        last_x, last_y = series["points"][-1]
        lines.append(
            f"{series['name']}: min {_formatted(block, min(values))}, max {_formatted(block, max(values))}, "
            f"last {_formatted(block, last_y)} ({_axis_label(block, last_x)})"
        )
    return "\n".join(lines)


def _chart_speech(block: Mapping[str, Any]) -> str:
    kind = {"line": "A line chart", "area": "An area chart", "bar": "A bar chart"}[block["kind"]]
    subject = f" of {block['title']}" if block.get("title") else ""
    main = block["series"][0]
    last_x, last_y = main["points"][-1]
    if block["kind"] == "bar" and block["x"]["type"] == "category":
        return f"{kind}{subject}, {_count(len(main['points']), 'bar')}."
    return f"{kind}{subject}, ending at {_formatted(block, last_y)}."


_INTERVAL_WORDS = {
    "1m": "1-minute", "5m": "5-minute", "15m": "15-minute", "30m": "30-minute",
    "1h": "hourly", "4h": "4-hour", "1d": "daily", "1w": "weekly",
}
_RANGE_WORDS = {
    "1D": "one day", "5D": "five days", "1M": "one month", "3M": "three months", "6M": "six months",
    "YTD": "the year to date", "1Y": "one year", "5Y": "five years", "MAX": "all available history",
}


def _as_of_date(block: Mapping[str, Any]) -> str:
    return str(block["as_of"])[:10]


def _price_chart_text(block: Mapping[str, Any]) -> str:
    title = f"{block['title']}: " if block.get("title") else ""
    return f"{title}{block['symbol']} {_INTERVAL_WORDS[block['interval']]}, {block['range']} to {_as_of_date(block)}"


def _price_chart_speech(block: Mapping[str, Any]) -> str:
    return (
        f"A {_INTERVAL_WORDS[block['interval']]} price chart of {block['symbol']} "
        f"over {_RANGE_WORDS[block['range']]}, as of {_as_of_date(block)}."
    )


def _sources_text(block: Mapping[str, Any]) -> str:
    lines = [block.get("title") or "Sources:"]
    for ref in block["refs"]:
        label = f"[{ref['citation']}] " if ref.get("citation") else ""
        lines.append(f"{label}{ref['title']}" + (f" — {ref['url']}" if ref.get("url") else ""))
    return "\n".join(lines)


def _sources_speech(block: Mapping[str, Any]) -> str:
    return f"{_count(len(block['refs']), 'source')[0].upper()}{_count(len(block['refs']), 'source')[1:]}."


def _choices_text(block: Mapping[str, Any]) -> str:
    options = "; ".join(option["label"] for option in block["options"])
    return f"{block['prompt']} Options: {options}" if block.get("prompt") else f"Options: {options}"


def _field_summary(item: Mapping[str, Any]) -> str:
    kind = item["kind"]
    if kind == "select":
        detail = f"select: {', '.join(item['options'])}"
    elif kind == "slider":
        unit = f" {item['unit']}" if item.get("unit") else ""
        detail = f"slider {format_number(item['min'])}–{format_number(item['max'])}{unit}"
    elif kind == "text":
        detail = "text"
    else:
        detail = "yes/no"
    return f"{item['label']} ({detail})"


def _form_text(block: Mapping[str, Any]) -> str:
    title = f"Form ({block['title']})" if block.get("title") else "Form"
    return f"{title}: " + ", ".join(_field_summary(item) for item in block["fields"])


def _form_speech(block: Mapping[str, Any]) -> str:
    return f"A form with {_count(len(block['fields']), 'field')}."


@dataclass(frozen=True)
class BlockSpec:
    """One catalog entry: how to normalize a block and project it to text and speech."""

    name: str
    model: type[BaseModel]
    normalize: Callable[[Mapping[str, Any], NormalizeContext], dict[str, Any]]
    to_text: Callable[[Mapping[str, Any]], str]
    to_speech: Callable[[Mapping[str, Any]], str]
    summary: str
    example: dict[str, Any]


CATALOG: dict[str, BlockSpec] = {
    spec.name: spec
    for spec in (
        BlockSpec(
            "stats", StatsBlock, _normalize_stats, _stats_text, _stats_speech,
            "1-6 headline numbers: items[{label, value, delta?, trend?: up|down|flat, hint?}], title?",
            {"type": "stats", "items": [{"label": "Revenue", "value": "$6,930", "delta": "+4.1%", "trend": "up"}]},
        ),
        BlockSpec(
            "chart", ChartBlock, _normalize_chart, _chart_text, _chart_speech,
            "kind: line|area|bar, x: {type: time|category, label?}, y: {label?, format?: number|percent|currency|compact},"
            " series[{name, points[[x, y]]}] (max 6 series), title?",
            {"type": "chart", "kind": "line", "x": {"type": "time"}, "series": [{"name": "Close", "points": [["2026-10-01", 228.4], ["2026-10-02", 231.0]]}]},
        ),
        BlockSpec(
            "price_chart", PriceChartBlock, _normalize_price_chart, _price_chart_text, _price_chart_speech,
            "pinned market data: symbol, interval: 1m|5m|15m|30m|1h|4h|1d|1w, range: 1D|5D|1M|3M|6M|YTD|1Y|5Y|MAX",
            {"type": "price_chart", "symbol": "AAPL", "interval": "1d", "range": "6M"},
        ),
        BlockSpec(
            "sources", SourcesBlock, _normalize_sources, _sources_text, _sources_speech,
            'citation chips: refs[{"bind": "source:1"}] naming this turn\'s sources',
            {"type": "sources", "refs": [{"bind": "source:1"}, {"bind": "source:2"}]},
        ),
        BlockSpec(
            "choices", ChoicesBlock, _normalize_choices, _choices_text, _choices_text,
            "2-6 suggested next messages: options[{label}] (the label is sent as the user's message), prompt?",
            {"type": "choices", "options": [{"label": "Compare with MSFT"}, {"label": "Show the 1-year trend"}]},
        ),
        BlockSpec(
            "form", FormBlock, _normalize_form, _form_text, _form_speech,
            "fields[{name, label?, kind: select (options[]) | slider (min, max, step?, unit?) | text | toggle, required?}],"
            " template with {name} placeholders that fills the user's composer",
            {
                "type": "form",
                "fields": [{"name": "symbol", "kind": "select", "options": ["AAPL", "MSFT"]}],
                "template": "Backtest {symbol} over one year",
            },
        ),
    )
}


def to_text(block: Mapping[str, Any]) -> str:
    return CATALOG[str(block["type"])].to_text(block)


def to_speech(block: Mapping[str, Any]) -> str:
    return CATALOG[str(block["type"])].to_speech(block)


def best_effort_text(spec: Any, block_type: str | None) -> str:
    """Readable text from a block that could not be shown: its own strings, never JSON."""
    pieces: list[str] = []

    def collect(value: Any, key: str | None) -> None:
        if len(pieces) >= 24:
            return
        if isinstance(value, Mapping):
            label, val = value.get("label"), value.get("value")
            if isinstance(label, str) and isinstance(val, (str, int, float)) and not isinstance(val, bool):
                pieces.append(f"{label.strip()}: {val if isinstance(val, str) else format_number(val)}")
                return
            for child_key, child in value.items():
                collect(child, str(child_key))
        elif isinstance(value, list):
            for child in value:
                collect(child, key)
        elif isinstance(value, str) and key in {"title", "label", "prompt", "name", "text"}:
            text = " ".join(value.split())
            if text:
                pieces.append(text[:MAX_LABEL])

    if isinstance(spec, Mapping):
        collect(spec, None)
    if pieces and block_type == "choices":
        return "Options: " + "; ".join(dict.fromkeys(pieces))
    if pieces:
        return "; ".join(dict.fromkeys(pieces))
    kind = block_type.replace("_", " ") if block_type else "content"
    article = "An" if kind[:1] in "aeiou" else "A"
    return f"[{article} {kind} block could not be shown.]"


def safe_url(value: str) -> bool:
    return bool(re.match(r"^(?:https?:|mailto:)", value.strip(), re.I)) and not re.search(r"[\s\"'<>]", value)


def validate_block(block: Mapping[str, Any]) -> dict[str, Any]:
    """Check a normalized block against its catalog model; returns it unchanged."""
    spec = CATALOG[str(block["type"])]
    spec.model.model_validate(block)
    return cast(dict[str, Any], dict(block))
