"""Build, check and query the Omnix system map (docs/architecture/omnix-system-map.{json,html}).

Agents: ask this script instead of reading the JSON (about 100 KB). Each answer is a few hundred tokens.

  python scripts/system_map.py owner src/app/platform/chat/admission.py   which node owns a file
  python scripts/system_map.py node live_voice      a node: paths, invariants, tests, docs, edges, flows
  python scripts/system_map.py flow live_call_turn  a request path, step by step, with files
  python scripts/system_map.py flows                every flow, one line each
  python scripts/system_map.py nodes                every node, by layer
  python scripts/system_map.py search portrait      nodes and flows that mention a word

  python scripts/system_map.py build                rewrite the JSON and HTML after changing system_map_data.py
  python scripts/system_map.py check                exit 1 when the committed map is stale or cites a missing path

The content is written by hand in system_map_data.py. Feature mount and dependency edges are read from the
feature catalog and each feature.py, so they always match the code.
"""
from __future__ import annotations

import argparse
import ast
import copy
import difflib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import system_map_data as data  # noqa: E402

JSON_PATH = ROOT / "docs/architecture/omnix-system-map.json"
HTML_PATH = ROOT / "docs/architecture/omnix-system-map.html"
TEMPLATE_PATH = ROOT / "scripts/system_map_template.html"
CATALOG_PATH = ROOT / "src/app/runtime/feature_catalog.py"

# A flow hop prefers runtime traffic over a declaration when both connect the same two nodes.
_HOP_RANK = {"http": 0, "websocket": 0, "sse": 0, "sql": 0, "calls": 1, "spawns": 1, "loads": 1, "hosts": 1,
             "reads": 1, "writes": 1, "depends_on": 2, "uses": 3, "mounts": 4}


# ---------------------------------------------------------------- feature catalog (read statically)

def catalog_features(root: Path = ROOT) -> dict[str, dict]:
    """Feature id -> its feature.py file and declared depends_on/uses."""
    tree = ast.parse((root / CATALOG_PATH.relative_to(ROOT)).read_text(encoding="utf-8"))
    targets: dict[str, str] = {}
    for stmt in tree.body:
        name = getattr(getattr(stmt, "target", None), "id", None)
        if name is None and isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
            name = stmt.targets[0].id
        if name == "FEATURE_CATALOG":
            mapping = next(n for n in ast.walk(stmt.value) if isinstance(n, ast.Dict))
            targets = ast.literal_eval(mapping)
    features = {}
    for feature_id, target in targets.items():
        module = target.split(":", 1)[0]
        rel = "src/" + module.replace(".", "/") + ".py"
        declared = {"depends_on": (), "uses": ()}
        for call in ast.walk(ast.parse((root / rel).read_text(encoding="utf-8"))):
            if isinstance(call, ast.Call) and getattr(call.func, "id", None) == "FeatureModule":
                for keyword in call.keywords:
                    if keyword.arg in declared:
                        declared[keyword.arg] = tuple(ast.literal_eval(keyword.value))
        features[feature_id] = {"file": rel, **declared}
    return features


# ---------------------------------------------------------------- build

def build(root: Path = ROOT) -> tuple[dict, list[str]]:
    """The map, and every problem found (an empty list means the map is sound)."""
    problems: list[str] = []
    nodes = copy.deepcopy(data.NODES)
    flows = copy.deepcopy(data.FLOWS)
    ids = [n["id"] for n in nodes]
    if len(set(ids)) != len(ids):
        problems.append("duplicate node ids")
    layer_ids = {layer["id"] for layer in data.LAYERS}
    for n in nodes:
        if n["layer"] not in layer_ids:
            problems.append(f"{n['id']}: unknown layer {n['layer']}")
        for p in n["paths"] + n.get("key_files", []) + n.get("tests", []) + n.get("docs", []):
            if not (root / p).exists():
                problems.append(f"{n['id']}: missing path {p}")

    rows = list(data.EDGE_ROWS)
    by_feature = {n["feature_id"]: n["id"] for n in nodes if n.get("feature_id")}
    features = catalog_features(root)
    for feature_id in sorted(set(by_feature) - set(features)):
        problems.append(f"node {by_feature[feature_id]} names feature {feature_id}, which the catalog does not have")
    for feature_id, feature in features.items():
        if feature_id not in by_feature:
            problems.append(f"catalog feature {feature_id} has no node (add one with feature={feature_id!r})")
        else:
            rows.append(("gateway", by_feature[feature_id], "mounts", "mounts feature routers"))
    for feature_id, feature in features.items():
        for kind in ("depends_on", "uses"):
            for other in feature[kind]:
                if feature_id in by_feature and other in by_feature:
                    rows.append((by_feature[feature_id], by_feature[other], kind, f"{kind} in {feature['file']}"))
                else:
                    problems.append(f"{feature['file']}: {kind} {other} has no node")

    node_ids = set(ids)
    edges, seen = [], set()
    for frm, to, kind, label in rows:
        if frm not in node_ids or to not in node_ids:
            problems.append(f"edge {frm}->{to}: unknown node")
        if kind not in data.EDGE_KINDS:
            problems.append(f"edge {frm}->{to}: unknown kind {kind}")
        eid = f"{frm}->{to}:{kind}"
        if eid in seen:
            problems.append(f"duplicate edge {eid}")
        seen.add(eid)
        edges.append({"id": eid, "from": frm, "to": to, "kind": kind, "label": label})

    for flow in flows:
        prev = None
        for i, step in enumerate(flow["steps"], 1):
            step["n"] = i
            if step["node"] not in node_ids:
                problems.append(f"{flow['id']} step {i}: unknown node {step['node']}")
            for p in step.get("files", []):
                if not (root / p).exists():
                    problems.append(f"{flow['id']} step {i}: missing file {p}")
            src = step.pop("from", None) or prev
            via = step.pop("via", None)  # names the edge kind when two edges join the same nodes
            if src:
                candidates = [e for e in edges if {e["from"], e["to"]} == {src, step["node"]}
                              and (via is None or e["kind"] == via)]
                if candidates:
                    best = min(candidates, key=lambda e: (_HOP_RANK[e["kind"]], e["from"] != src))
                    step["from"], step["edge"] = src, best["id"]
                elif src != step["node"] or via:
                    kind = f"{via} " if via else ""
                    problems.append(f"{flow['id']} step {i}: no {kind}edge between {src} and {step['node']}")
            prev = step["node"]

    path_index: dict[str, str] = {}
    for n in nodes:
        for p in n["paths"]:
            path_index.setdefault(p, n["id"])
    meta = dict(data.META)
    meta_tail = {k: meta.pop(k) for k in ("global_invariants", "validation", "key_docs")}
    meta.update(layers=data.LAYERS, edge_kinds=data.EDGE_KINDS, **meta_tail,
                counts={"nodes": len(nodes), "edges": len(edges), "flows": len(flows)})
    return {"meta": meta, "nodes": nodes, "edges": edges, "flows": flows,
            "path_index": dict(sorted(path_index.items()))}, problems


def render(the_map: dict) -> dict[Path, str]:
    embedded = json.dumps(the_map, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE_PATH.read_text(encoding="utf-8").replace("__OMNIX_MAP_DATA__", embedded)
    return {JSON_PATH: json.dumps(the_map, indent=2, ensure_ascii=False) + "\n", HTML_PATH: html}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n") if path.exists() else ""


def stale_files() -> list[str]:
    """Committed map files that differ from a fresh build (line endings ignored)."""
    the_map, _ = build()
    return [str(p.relative_to(ROOT).as_posix()) for p, text in render(the_map).items()
            if _read(p) != text.replace("\r\n", "\n")]


# ---------------------------------------------------------------- queries (read the committed JSON)

def load() -> dict:
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def find_node(the_map: dict, key: str) -> dict | None:
    k = key.strip().lower()
    for n in the_map["nodes"]:
        if k in (n["id"].lower(), n.get("feature_id", "").lower(), n["label"].lower()):
            return n
    return None


def owner_of(path: str, the_map: dict | None = None) -> str | None:
    """The node that owns a file: the longest cited path or key file that contains it."""
    the_map = the_map or load()
    p = Path(path)
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(ROOT)
        except ValueError:
            return None
    target = p.as_posix().lstrip("./")
    best, best_len = None, -1
    for n in the_map["nodes"]:
        for cited in n["paths"] + n.get("key_files", []):
            hit = target == cited.rstrip("/") or (cited.endswith("/") and target.startswith(cited))
            if hit and len(cited) > best_len:
                best, best_len = n["id"], len(cited)
    return best


def node_text(the_map: dict, n: dict) -> str:
    layers = {layer["id"]: layer["label"] for layer in the_map["meta"]["layers"]}
    head = f"{n['id']} — {n['label']} [{layers[n['layer']]}]"
    head += "".join(f" {k} {n[key]}" for k, key in (("feature", "feature_id"), ("port", "port")) if n.get(key))
    lines = [head, n["summary"], "paths: " + ", ".join(n["paths"])]
    for title, key in (("key files", "key_files"), ("tests", "tests"), ("docs", "docs")):
        if n.get(key):
            lines.append(f"{title}: " + ", ".join(n[key]))
    if n.get("invariants"):
        lines.append("invariants:")
        lines += [f"  - {x}" for x in n["invariants"]]

    def edge_list(edges: list[dict], end: str) -> str:
        return "; ".join(f"{e[end]} ({e['kind']}{'' if e['kind'] in ('depends_on', 'uses', 'mounts') else ': ' + e['label']})"
                         for e in edges)

    out = [e for e in the_map["edges"] if e["from"] == n["id"]]
    inc = [e for e in the_map["edges"] if e["to"] == n["id"]]
    if out:
        lines.append("out: " + edge_list(out, "to"))
    if inc:
        lines.append("in: " + edge_list(inc, "from"))
    flows = []
    for f in the_map["flows"]:
        steps = [str(s["n"]) for s in f["steps"] if s["node"] == n["id"]]
        if steps:
            flows.append(f"{f['id']} (step {','.join(steps)})")
    if flows:
        lines.append("flows: " + "; ".join(flows))
    return "\n".join(lines)


def flow_text(the_map: dict, flow_id: str) -> str | None:
    f = next((x for x in the_map["flows"] if x["id"] == flow_id), None)
    if f is None:
        return None
    edges = {e["id"]: e for e in the_map["edges"]}
    lines = [f"{f['id']} — {f['name']}. Trigger: {f['trigger']}", f["summary"]]
    for s in f["steps"]:
        via = ""
        if s.get("edge"):
            e = edges[s["edge"]]
            # a step can travel an edge backwards: the reply to a call, a result coming home
            via = f"  ({e['kind']} from {s['from']})" if e["from"] == s["from"] else f"  (returns from {s['from']} over {e['from']} {e['kind']} {e['to']})"
        lines.append(f"{s['n']:>2}. {s['node']}: {s['action']}{via}")
        if s.get("files"):
            lines.append("    " + ", ".join(s["files"]))
    return "\n".join(lines)


def flows_text(the_map: dict) -> str:
    return "\n".join(f"{f['id']} — {f['name']} ({len(f['steps'])} steps): {f['trigger']}" for f in the_map["flows"])


def nodes_text(the_map: dict) -> str:
    lines = []
    for layer in the_map["meta"]["layers"]:
        members = [n for n in the_map["nodes"] if n["layer"] == layer["id"]]
        lines.append(f"{layer['label']}: " + ", ".join(f"{n['id']} ({n['label']})" for n in members))
    return "\n".join(lines)


def search_text(the_map: dict, word: str) -> str:
    w = word.lower()
    hits = []
    for n in the_map["nodes"]:
        hay = " ".join([n["id"], n["label"], n["summary"], *n["paths"], *n.get("key_files", []), *n.get("invariants", [])])
        if w in hay.lower():
            hits.append(f"node {n['id']} — {n['label']}: {n['summary'][:110]}")
    for f in the_map["flows"]:
        steps = [str(s["n"]) for s in f["steps"] if w in (s["action"] + " " + " ".join(s.get("files", []))).lower()]
        if steps or w in (f["name"] + " " + f["summary"]).lower():
            hits.append(f"flow {f['id']} — {f['name']}" + (f" (step {','.join(steps)})" if steps else ""))
    return "\n".join(hits) or f"nothing mentions {word!r}"


def _suggest(key: str, pool: list[str]) -> str:
    close = difflib.get_close_matches(key, pool, n=5, cutoff=0.4)
    return f"no match for {key!r}" + (f"; did you mean: {', '.join(close)}" if close else "")


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "check", "flows", "nodes"):
        sub.add_parser(name)
    for name, arg in (("owner", "path"), ("node", "id"), ("flow", "id"), ("search", "text")):
        sub.add_parser(name).add_argument(arg)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    if args.command in ("build", "check"):
        the_map, problems = build()
        for problem in problems:
            print("problem:", problem)
        if args.command == "build":
            if problems:
                return 1
            for path, text in render(the_map).items():
                path.write_bytes(text.encode("utf-8"))
            counts = the_map["meta"]["counts"]
            print(f"wrote {counts['nodes']} nodes, {counts['edges']} edges, {counts['flows']} flows")
            return 0
        stale = stale_files()
        for path in stale:
            print(f"stale: {path} (run python scripts/system_map.py build)")
        return 1 if problems or stale else 0

    the_map = load()
    if args.command == "flows":
        print(flows_text(the_map))
    elif args.command == "nodes":
        print(nodes_text(the_map))
    elif args.command == "search":
        print(search_text(the_map, args.text))
    elif args.command == "flow":
        text = flow_text(the_map, args.id)
        print(text or _suggest(args.id, [f["id"] for f in the_map["flows"]]))
        return 0 if text else 1
    elif args.command == "node":
        n = find_node(the_map, args.id)
        print(node_text(the_map, n) if n else _suggest(args.id, [x["id"] for x in the_map["nodes"]]))
        return 0 if n else 1
    elif args.command == "owner":
        owner = owner_of(args.path, the_map)
        if owner is None:
            print(f"no node cites {args.path}; try: python scripts/system_map.py search <word>")
            return 1
        print(node_text(the_map, find_node(the_map, owner)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
