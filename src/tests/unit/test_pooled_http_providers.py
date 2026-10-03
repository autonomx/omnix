"""Every HTTP model provider talks through the pooled client (WP-7.2 acceptance)."""
from __future__ import annotations

import ast
import inspect

import pytest

from app.providers.base import BaseProvider
from app.providers.catalog import specs
from app.runtime.http_client import PooledHttpClient

_DIRECT_CALLS = {"Client", "AsyncClient", "get", "post", "put", "delete", "request", "stream"}


@pytest.mark.parametrize("spec", specs("llm"), ids=lambda spec: spec.id)
def test_the_provider_uses_the_pooled_http_client(spec) -> None:
    provider_class = spec.load()
    assert issubclass(provider_class, BaseProvider)
    assert isinstance(inspect.getattr_static(BaseProvider, "http"), property)
    assert inspect.signature(BaseProvider.http.fget).return_annotation in {PooledHttpClient, "PooledHttpClient"}

    tree = ast.parse(inspect.getsource(inspect.getmodule(provider_class)))
    direct = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in {"httpx", "requests"}
        and node.func.attr in _DIRECT_CALLS
    ]
    assert direct == [], f"{spec.module} calls httpx/requests directly at lines {direct}"
