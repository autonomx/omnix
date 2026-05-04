from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
import sys
from typing import Any, Callable, Dict, Iterable, List, Tuple


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _looks_like_fastapi_app(value: Any) -> bool:
    return (
        value is not None
        and hasattr(value, "routes")
        and hasattr(value, "router")
        and callable(getattr(value, "include_router", None))
    )


def _iter_app_module_names() -> Iterable[str]:
    explicit = [
        "app.main",
        "app.server",
        "app.api",
        "app.fastapi_app",
        "app.web",
        "app.application",
        "app",
        "main",
        "server",
    ]
    seen = set()
    for name in explicit:
        if name not in seen:
            seen.add(name)
            yield name

    # Scan already-imported modules first. This is cheap and often finds the
    # actual app after provider/shared imports.
    for name in list(sys.modules):
        if (
            name == "app"
            or name.startswith("app.")
            or name in {"main", "server"}
        ) and name not in seen:
            seen.add(name)
            yield name

    # Controlled package walk. Do not import the whole world; only app.*.
    try:
        app_pkg = importlib.import_module("app")
        for module_info in pkgutil.walk_packages(app_pkg.__path__, prefix="app."):
            name = module_info.name
            lower = name.lower()
            if not any(token in lower for token in ("main", "server", "api", "route", "session", "fastapi")):
                continue
            if name not in seen:
                seen.add(name)
                yield name
    except Exception:
        return


def _app_objects_from_module(module_name: str) -> List[Tuple[str, Any]]:
    out: List[Tuple[str, Any]] = []
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return out

    attr_names = [
        "app",
        "application",
        "fastapi_app",
        "api",
    ]
    factory_names = [
        "create_app",
        "get_app",
        "build_app",
        "make_app",
        "get_application",
    ]

    for attr_name in attr_names:
        app_obj = getattr(module, attr_name, None)
        if _looks_like_fastapi_app(app_obj):
            out.append((f"{module_name}.{attr_name}", app_obj))

    for factory_name in factory_names:
        factory = getattr(module, factory_name, None)
        if not callable(factory):
            continue
        try:
            app_obj = factory()
        except TypeError:
            try:
                app_obj = factory(testing=True)
            except Exception:
                continue
        except Exception:
            continue
        if _looks_like_fastapi_app(app_obj):
            out.append((f"{module_name}.{factory_name}()", app_obj))

    # Last pass: inspect module globals for FastAPI-like objects.
    for attr_name, value in vars(module).items():
        if attr_name.startswith("_"):
            continue
        if _looks_like_fastapi_app(value):
            key = f"{module_name}.{attr_name}"
            if key not in {existing[0] for existing in out}:
                out.append((key, value))

    return out


def _discover_fastapi_apps() -> List[Tuple[str, Any]]:
    """Discover likely FastAPI app objects without starting a server."""
    candidates: List[Tuple[str, Any]] = []
    seen = set()
    for module_name in _iter_app_module_names():
        for app_name, app_obj in _app_objects_from_module(module_name):
            if app_name in seen:
                continue
            seen.add(app_name)
            candidates.append((app_name, app_obj))
    return candidates


def describe_fastapi_turn_routes() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for app_name, app_obj in _discover_fastapi_apps():
        for route in getattr(app_obj, "routes", []) or []:
            path = getattr(route, "path", "")
            methods = sorted(list(getattr(route, "methods", []) or []))
            if "/api/rpg/session" not in str(path):
                continue
            rows.append(
                {
                    "app": app_name,
                    "path": str(path),
                    "methods": methods,
                    "name": str(getattr(route, "name", "")),
                }
            )
    return rows


def describe_fastapi_app_discovery() -> Dict[str, Any]:
    apps = _discover_fastapi_apps()
    return {
        "app_count": len(apps),
        "apps": [
            {
                "name": name,
                "route_count": len(getattr(app_obj, "routes", []) or []),
                "session_routes": [
                    {
                        "path": str(getattr(route, "path", "")),
                        "methods": sorted(list(getattr(route, "methods", []) or [])),
                        "name": str(getattr(route, "name", "")),
                    }
                    for route in getattr(app_obj, "routes", []) or []
                    if "/api/rpg/session" in str(getattr(route, "path", ""))
                ],
            }
            for name, app_obj in apps
        ],
        "module_probe_count": len(list(_iter_app_module_names())),
    }


def _candidate_callables() -> List[Tuple[str, Callable[..., Any]]]:
    """Discover in-process RPG turn callables.

    Keep this as a narrow compatibility ladder. The preferred target is the
    same implementation behind /api/rpg/session/turn, but project modules have
    moved across phases, so discovery is centralized here instead of buried in
    autoplay_llm_campaign.py.
    """
    candidates: List[Tuple[str, Callable[..., Any]]] = []

    module_specs = [
        ("app.rpg.session_runtime", ["run_player_turn", "apply_player_turn", "process_player_turn"]),
        ("app.rpg.session", ["run_player_turn", "apply_player_turn", "process_player_turn"]),
        ("app.rpg.runtime", ["run_player_turn", "apply_player_turn", "process_player_turn"]),
        ("app.rpg.api.session", ["run_session_turn", "session_turn", "turn"]),
        ("app.rpg.api.session_routes", ["run_session_turn", "session_turn", "turn"]),
        ("app.rpg.routes.session", ["run_session_turn", "session_turn", "turn"]),
        ("app.rpg.routes.session_routes", ["run_session_turn", "session_turn", "turn"]),
        ("app.rpg.session_routes", ["run_session_turn", "session_turn", "turn"]),
        ("app.rpg.session_api", ["run_session_turn", "session_turn", "turn"]),
        ("app.rpg.api.rpg_session", ["run_session_turn", "session_turn", "turn"]),
        ("app.rpg.rpg_session", ["run_session_turn", "session_turn", "turn"]),
        ("app.rpg.session_api", ["run_session_turn", "session_turn", "turn"]),
    ]

    for module_name, names in module_specs:
        try:
            module = __import__(module_name, fromlist=names)
        except Exception:
            continue
        for name in names:
            value = getattr(module, name, None)
            if callable(value):
                candidates.append((f"{module_name}.{name}", value))

    return candidates


def describe_turn_runtime_candidates() -> List[Dict[str, str]]:
    rows = []
    for name, fn in _candidate_callables():
        try:
            signature = str(inspect.signature(fn))
        except Exception:
            signature = "<uninspectable>"
        rows.append({"name": name, "signature": signature})
    for route in describe_fastapi_turn_routes():
        rows.append(
            {
                "name": f"{route.get('app')} {','.join(route.get('methods') or [])} {route.get('path')}",
                "signature": f"fastapi_route:{route.get('name')}",
            }
        )
    if not rows:
        discovery = describe_fastapi_app_discovery()
        rows.append(
            {
                "name": "fastapi_app_discovery",
                "signature": f"apps={discovery.get('app_count')} modules={discovery.get('module_probe_count')}",
            }
        )
    return rows


def _call_with_supported_kwargs(fn: Callable[..., Any], **kwargs: Any) -> Any:
    try:
        signature = inspect.signature(fn)
        supported = {
            key: value
            for key, value in kwargs.items()
            if key in signature.parameters
        }
        if supported:
            return fn(**supported)
    except Exception:
        pass

    # Common positional fallbacks.
    positional_shapes = [
        (
            kwargs.get("simulation_state"),
            kwargs.get("player_input"),
            kwargs.get("turn_index"),
        ),
        (
            kwargs.get("session"),
            kwargs.get("player_input"),
        ),
        (
            kwargs.get("session_id"),
            kwargs.get("player_input"),
        ),
    ]
    last_error: Exception | None = None
    for shape in positional_shapes:
        try:
            return fn(*shape)
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise RuntimeError("turn_runtime_call_failed")


def _build_session_payload(
    *,
    session_id: str,
    simulation_state: Dict[str, Any],
    player_input: str,
    turn_index: int,
) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "simulation_state": simulation_state,
        "player_input": player_input,
        "input": player_input,
        "message": player_input,
        "turn_index": turn_index,
        "metadata": {
            "source": "autoplay_llm_campaign",
            "turn_index": turn_index,
        },
    }


def _install_autoplay_session(
    *,
    session_id: str,
    simulation_state: Dict[str, Any],
) -> List[str]:
    """Best-effort session_store seeding for route-based turn calls."""
    notes: List[str] = []
    session_payload = {
        "session_id": session_id,
        "id": session_id,
        "simulation_state": simulation_state,
        "metadata": {"source": "autoplay_llm_campaign"},
    }
    store_module_names = [
        "app.rpg.session_store",
        "app.rpg.sessions",
        "app.rpg.session",
        "app.rpg.session_manager",
        "app.rpg.session_state",
        "app.rpg.runtime.session_store",
        "app.rpg.api.session",
        "app.rpg.api.session_routes",
        "app.rpg.routes.session",
        "app.rpg.routes.session_routes",
    ]
    stores = []
    import_errors = []
    for module_name in store_module_names:
        try:
            stores.append((module_name, importlib.import_module(module_name)))
        except Exception as exc:
            import_errors.append(f"{module_name}:{type(exc).__name__}:{exc}")

    if not stores:
        return ["session_store_import_failed:" + " | ".join(import_errors[-10:])]

    for module_name, store in stores:
        for name in (
            "save_session",
            "set_session",
            "put_session",
            "update_session",
            "create_session",
            "upsert_session",
        ):
            fn = getattr(store, name, None)
            if callable(fn):
                try:
                    fn(session_id, session_payload)
                    notes.append(f"{module_name}.{name}(session_id, session_payload)")
                    return notes
                except Exception as exc:
                    notes.append(f"{module_name}.{name}:failed:{type(exc).__name__}:{exc}")
                try:
                    fn(session_payload)
                    notes.append(f"{module_name}.{name}(session_payload)")
                    return notes
                except Exception as exc:
                    notes.append(f"{module_name}.{name}:single_arg_failed:{type(exc).__name__}:{exc}")

        # Common module-level dict stores.
        for attr in ("SESSIONS", "_SESSIONS", "sessions", "_sessions", "SESSION_STORE", "session_store"):
            value = getattr(store, attr, None)
            if isinstance(value, dict):
                value[session_id] = session_payload
                notes.append(f"{module_name}.{attr}[session_id]=session_payload")
                return notes

    # Some stores expose get_session() backed by an internal dict not exposed.
    notes.append("no_supported_session_store_writer_found")
    return notes


def _turn_payload_variants(
    *,
    session_id: str,
    player_input: str,
    turn_index: int,
    simulation_state: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    simulation_state = simulation_state or {}
    variants = [
        {
            "session_id": session_id,
            "input": player_input,
            "turn_index": turn_index,
        },
        {
            "session_id": session_id,
            "player_input": player_input,
            "turn_index": turn_index,
        },
        {
            "session_id": session_id,
            "message": player_input,
            "turn_index": turn_index,
        },
        {
            "session_id": session_id,
            "command": player_input,
            "turn_index": turn_index,
        },
        {
            "session_id": session_id,
            "text": player_input,
            "turn_index": turn_index,
        },
    ]
    variants.extend(
        [
            {
                "session_id": session_id,
                "input": player_input,
                "turn_index": turn_index,
                "simulation_state": simulation_state,
            },
            {
                "session_id": session_id,
                "player_input": player_input,
                "turn_index": turn_index,
                "simulation_state": simulation_state,
            },
            {
                "session": {
                    "session_id": session_id,
                    "id": session_id,
                    "simulation_state": simulation_state,
                },
                "input": player_input,
                "turn_index": turn_index,
            },
            {
                "session_id": session_id,
                "action": {
                    "text": player_input,
                    "input": player_input,
                },
                "turn_index": turn_index,
                "simulation_state": simulation_state,
            },
        ]
    )
    return variants


def _run_turn_via_fastapi_route(
    *,
    simulation_state: Dict[str, Any],
    session_id: str,
    player_input: str,
    turn_index: int,
) -> Dict[str, Any]:
    try:
        from fastapi.testclient import TestClient
    except Exception as exc:
        return {
            "ok": False,
            "reason": "fastapi_testclient_unavailable",
            "error": f"{type(exc).__name__}: {exc}",
        }

    session_notes = _install_autoplay_session(
        session_id=session_id,
        simulation_state=simulation_state,
    )
    attempted: List[Dict[str, Any]] = []
    route_paths = [
        "/api/rpg/session/turn",
        "/api/rpg/session/turn/",
    ]

    for app_name, app_obj in _discover_fastapi_apps():
        client = TestClient(app_obj)
        for path in route_paths:
            for payload in _turn_payload_variants(
                session_id=session_id,
                player_input=player_input,
                turn_index=turn_index,
                simulation_state=simulation_state,
            ):
                try:
                    response = client.post(path, json=payload)
                    text = response.text[:1000]
                    attempted.append(
                        {
                            "app": app_name,
                            "path": path,
                            "status_code": response.status_code,
                            "payload_keys": sorted(payload.keys()),
                            "text": text,
                        }
                    )
                    if response.status_code < 200 or response.status_code >= 300:
                        continue
                    data = response.json()
                    normalized = normalize_turn_result(
                        data,
                        fallback_state=simulation_state,
                        runtime_name=f"{app_name} POST {path}",
                    )
                    normalized["ok"] = True
                    normalized["runtime_name"] = f"{app_name} POST {path}"
                    normalized["fastapi_route"] = {
                        "app": app_name,
                        "path": path,
                        "payload_keys": sorted(payload.keys()),
                        "session_notes": session_notes,
                    }
                    return normalized
                except Exception as exc:
                    attempted.append(
                        {
                            "app": app_name,
                            "path": path,
                            "payload_keys": sorted(payload.keys()),
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )

    return {
        "ok": False,
        "reason": "fastapi_turn_route_unavailable",
        "attempted": attempted[-30:],
    }


def probe_live_http_health(base_url: str = "") -> Dict[str, Any]:
    base_url = (
        base_url
        or os.environ.get("RPG_AUTOPLAY_BASE_URL")
        or "http://127.0.0.1:5000"
    ).rstrip("/")
    try:
        import requests
    except Exception as exc:
        return {
            "ok": False,
            "reason": "requests_unavailable",
            "error": f"{type(exc).__name__}: {exc}",
            "base_url": base_url,
        }

    attempted = []
    for path in ("/api/health", "/health", "/api/providers/status"):
        url = f"{base_url}{path}"
        try:
            response = requests.get(url, timeout=10)
            attempted.append(
                {
                    "url": url,
                    "status_code": response.status_code,
                    "text": response.text[:500],
                }
            )
            if 200 <= response.status_code < 300:
                return {
                    "ok": True,
                    "base_url": base_url,
                    "url": url,
                    "status_code": response.status_code,
                    "text": response.text[:500],
                    "attempted": attempted,
                }
        except Exception as exc:
            attempted.append(
                {
                    "url": url,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return {
        "ok": False,
        "reason": "live_http_server_unavailable",
        "base_url": base_url,
        "attempted": attempted,
    }


def bootstrap_live_http_session(
    *,
    session_id: str,
    simulation_state: Dict[str, Any],
    base_url: str = "",
) -> Dict[str, Any]:
    base_url = (
        base_url
        or os.environ.get("RPG_AUTOPLAY_BASE_URL")
        or "http://127.0.0.1:5000"
    ).rstrip("/")
    try:
        import requests
    except Exception as exc:
        return {
            "ok": False,
            "reason": "requests_unavailable",
            "error": f"{type(exc).__name__}: {exc}",
            "base_url": base_url,
        }

    payloads = [
        {
            "session_id": session_id,
            "simulation_state": simulation_state,
            "metadata": {"source": "autoplay_llm_campaign"},
        },
        {
            "id": session_id,
            "session_id": session_id,
            "state": simulation_state,
            "simulation_state": simulation_state,
        },
        {
            "session": {
                "session_id": session_id,
                "id": session_id,
                "simulation_state": simulation_state,
            }
        },
    ]
    paths = [
        "/api/rpg/session/create",
        "/api/rpg/session/start",
        "/api/rpg/session/new",
        "/api/rpg/session/load",
        "/api/rpg/session/save",
        "/api/rpg/session/set",
        "/api/rpg/session/get",
    ]

    attempted = []
    for path in paths:
        url = f"{base_url}{path}"
        for payload in payloads:
            try:
                response = requests.post(url, json=payload, timeout=30)
                text = response.text[:1000]
                attempted.append(
                    {
                        "url": url,
                        "status_code": response.status_code,
                        "payload_keys": sorted(payload.keys()),
                        "text": text,
                    }
                )
                if 200 <= response.status_code < 300:
                    return {
                        "ok": True,
                        "base_url": base_url,
                        "url": url,
                        "status_code": response.status_code,
                        "payload_keys": sorted(payload.keys()),
                        "text": text,
                        "attempted": attempted,
                    }
            except Exception as exc:
                attempted.append(
                    {
                        "url": url,
                        "payload_keys": sorted(payload.keys()),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    return {
        "ok": False,
        "reason": "live_http_session_bootstrap_unavailable",
        "base_url": base_url,
        "attempted": attempted[-50:],
    }


def _run_turn_via_live_http_route(
    *,
    simulation_state: Dict[str, Any],
    session_id: str,
    player_input: str,
    turn_index: int,
    base_url: str = "",
) -> Dict[str, Any]:
    resolved_base_url = (
        base_url
        or os.environ.get("RPG_AUTOPLAY_BASE_URL")
        or "http://127.0.0.1:5000"
    ).rstrip("/")
    attempted: List[Dict[str, Any]] = []
    try:
        import requests
    except Exception as exc:
        return {
            "ok": False,
            "reason": "requests_unavailable",
            "error": f"{type(exc).__name__}: {exc}",
        }

    health = probe_live_http_health(resolved_base_url)
    if not health.get("ok"):
        return {
            "ok": False,
            "reason": "live_http_server_unavailable",
            "base_url": resolved_base_url,
            "health": health,
        }

    bootstrap = bootstrap_live_http_session(
        session_id=session_id,
        simulation_state=simulation_state,
        base_url=resolved_base_url,
    )

    for payload in _turn_payload_variants(
        session_id=session_id,
        player_input=player_input,
        turn_index=turn_index,
        simulation_state=simulation_state,
    ):
        url = f"{resolved_base_url}/api/rpg/session/turn"
        try:
            response = requests.post(url, json=payload, timeout=60)
            attempted.append(
                {
                    "url": url,
                    "status_code": response.status_code,
                    "payload_keys": sorted(payload.keys()),
                    "text": response.text[:1000],
                }
            )
            if response.status_code < 200 or response.status_code >= 300:
                continue
            data = response.json()
            normalized = normalize_turn_result(
                data,
                fallback_state=simulation_state,
                runtime_name=f"HTTP POST {url}",
            )
            normalized["ok"] = True
            normalized["runtime_name"] = f"HTTP POST {url}"
            normalized["http_route"] = {
                "url": url,
                "payload_keys": sorted(payload.keys()),
                "health": health,
                "bootstrap": bootstrap,
            }
            return normalized
        except Exception as exc:
            attempted.append(
                {
                    "url": url,
                    "payload_keys": sorted(payload.keys()),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    return {
        "ok": False,
        "reason": "live_http_turn_route_unavailable",
        "base_url": resolved_base_url,
        "health": health,
        "bootstrap": bootstrap,
        "attempted": attempted[-30:],
    }


def run_real_rpg_turn(
    *,
    simulation_state: Dict[str, Any],
    session_id: str,
    player_input: str,
    turn_index: int,
    base_url: str = "",
) -> Dict[str, Any]:
    """Run one real RPG turn in-process.

    Returns a normalized envelope:
      {
        ok,
        runtime_name,
        raw_result,
        simulation_state,
        turn_contract,
        narration,
      }
    """
    resolved_base_url = (
        str(base_url or "")
        or os.environ.get("RPG_AUTOPLAY_BASE_URL")
        or "http://127.0.0.1:5000"
    ).rstrip("/")

    session = _build_session_payload(
        session_id=session_id,
        simulation_state=simulation_state,
        player_input=player_input,
        turn_index=turn_index,
    )

    errors: List[str] = []
    for runtime_name, fn in _candidate_callables():
        try:
            result = _call_with_supported_kwargs(
                fn,
                simulation_state=simulation_state,
                state=simulation_state,
                session=session,
                session_dict=session,
                session_id=session_id,
                player_input=player_input,
                input_text=player_input,
                message=player_input,
                command=player_input,
                turn_index=turn_index,
            )
            normalized = normalize_turn_result(
                result,
                fallback_state=simulation_state,
                runtime_name=runtime_name,
            )
            normalized["runtime_name"] = runtime_name
            return normalized
        except Exception as exc:
            errors.append(f"{runtime_name}:{type(exc).__name__}:{exc}")

    route_result = _run_turn_via_fastapi_route(
        simulation_state=simulation_state,
        session_id=session_id,
        player_input=player_input,
        turn_index=turn_index,
    )
    if route_result.get("ok"):
        return route_result

    http_result = _run_turn_via_live_http_route(
        simulation_state=simulation_state,
        session_id=session_id,
        player_input=player_input,
        turn_index=turn_index,
        base_url=resolved_base_url,
    )
    if http_result.get("ok"):
        return http_result

    return {
        "ok": False,
        "reason": "real_turn_runtime_unavailable",
        "errors": errors[-20:],
        "fastapi_route_error": route_result,
        "live_http_route_error": http_result,
        "runtime_candidates": describe_turn_runtime_candidates(),
        "simulation_state": simulation_state,
        "turn_contract": {},
        "narration": "",
    }


def extract_turn_contract(result: Any) -> Dict[str, Any]:
    result = _safe_dict(result)
    candidates = [
        result.get("turn_contract"),
        _safe_dict(result.get("result")).get("turn_contract"),
        _safe_dict(result.get("contract")),
        _safe_dict(_safe_dict(result.get("result")).get("contract")),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def extract_simulation_state(result: Any, fallback_state: Dict[str, Any]) -> Dict[str, Any]:
    result = _safe_dict(result)
    candidates = [
        result.get("simulation_state"),
        _safe_dict(result.get("session")).get("simulation_state"),
        _safe_dict(result.get("result")).get("simulation_state"),
        _safe_dict(_safe_dict(result.get("result")).get("session")).get("simulation_state"),
        _safe_dict(result.get("state")),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
    return fallback_state


def extract_narration(result: Any) -> str:
    result = _safe_dict(result)
    contract = extract_turn_contract(result)
    candidates = [
        result.get("narration"),
        _safe_dict(result.get("result")).get("narration"),
        contract.get("narration"),
        _safe_dict(contract.get("narration")).get("text"),
        _safe_dict(result.get("llm")).get("narration"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return ""


def normalize_turn_result(
    result: Any,
    *,
    fallback_state: Dict[str, Any],
    runtime_name: str = "",
) -> Dict[str, Any]:
    raw = result if isinstance(result, dict) else {"value": result}
    turn_contract = extract_turn_contract(raw)
    state = extract_simulation_state(raw, fallback_state)
    narration = extract_narration(raw)
    return {
        "ok": bool(_safe_dict(raw).get("ok", True)),
        "runtime_name": runtime_name,
        "raw_result": raw,
        "simulation_state": state,
        "turn_contract": turn_contract,
        "narration": narration,
    }