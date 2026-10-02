"""Alert rules and the dashboard read metrics the catalog documents (WP-10.6)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
ALERTS = ROOT / "deploy" / "observability" / "alerts.yml"
DASHBOARD = ROOT / "deploy" / "observability" / "dashboards" / "omnix-overview.json"
CATALOG = ROOT / "docs" / "operations" / "METRICS.md"
_DURATION = re.compile(r"\d+[smhd]")
_METRIC = re.compile(r"\bomnix_[a-z0-9_]+")


def _catalog_names() -> set[str]:
    names = set(re.findall(r"`(omnix_[a-z0-9_]+)`", CATALOG.read_text(encoding="utf-8")))
    planned = CATALOG.read_text(encoding="utf-8").split("## Planned", 1)[0]
    return {name for name in names if f"`{name}`" in planned}


def _metric_family(name: str) -> str:
    for suffix in ("_bucket", "_sum", "_count"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _balanced(expr: str) -> bool:
    depth = {"(": 0, "{": 0, "[": 0}
    closing = {")": "(", "}": "{", "]": "["}
    for char in re.sub(r'"[^"]*"', '""', expr):
        if char in depth:
            depth[char] += 1
        elif char in closing:
            depth[closing[char]] -= 1
            if depth[closing[char]] < 0:
                return False
    return not any(depth.values())


def _alert_rules() -> list[dict]:
    document = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))
    return [rule for group in document["groups"] for rule in group["rules"]]


def test_alert_rules_are_well_formed() -> None:
    document = yaml.safe_load(ALERTS.read_text(encoding="utf-8"))
    names = [rule["alert"] for rule in _alert_rules()]

    assert document["groups"] and all(group["name"] and group["rules"] for group in document["groups"])
    assert len(names) == len(set(names))
    for rule in _alert_rules():
        assert set(rule) <= {"alert", "expr", "for", "labels", "annotations"}, rule["alert"]
        assert rule["labels"]["severity"] in {"page", "ticket"}, rule["alert"]
        assert rule["annotations"]["summary"], rule["alert"]
        assert _DURATION.fullmatch(rule["for"]), rule["alert"]
        assert _balanced(rule["expr"]), rule["alert"]


def test_alerts_and_dashboard_use_cataloged_metrics_only() -> None:
    catalog = _catalog_names()
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    expressions = [rule["expr"] for rule in _alert_rules()]
    expressions += [target["expr"] for panel in dashboard["panels"] for target in panel.get("targets", [])]

    used = {_metric_family(name) for expr in expressions for name in _METRIC.findall(expr)}
    assert used and used <= catalog, sorted(used - catalog)
    assert all(_balanced(expr) for expr in expressions)


def test_the_dashboard_is_importable() -> None:
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))

    assert dashboard["uid"] == "omnix-overview"
    assert dashboard["__inputs"][0]["name"] == "DS_PROMETHEUS"
    ids = [panel["id"] for panel in dashboard["panels"]]
    assert len(ids) == len(set(ids))
    for panel in dashboard["panels"]:
        assert {"h", "w", "x", "y"} <= set(panel["gridPos"])
        assert panel["gridPos"]["x"] + panel["gridPos"]["w"] <= 24
