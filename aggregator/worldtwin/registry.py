"""Layer registry — auto-discovers source modules at import time.

Each module in worldtwin.sources must export:
    LAYER: LayerMeta
    async fetch(client) -> data (list | dict)

This registry loads them all and makes them available to the scheduler,
server, and discovery endpoint. Adding a new layer = dropping one file
in worldtwin/sources/.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import Callable, Awaitable, Any

import httpx

from .models import LayerMeta

FetchFn = Callable[[httpx.AsyncClient], Awaitable[Any]]


@dataclass
class RegisteredLayer:
    meta: LayerMeta
    fetch: FetchFn
    legacy_writer: Callable[[Any], Any] | None = None
    # optional custom function that converts v1 data → legacy cache shape
    # if None, the legacy file gets the same data as the v1 envelope


_registry: dict[str, RegisteredLayer] = {}


def register(meta: LayerMeta, fetch: FetchFn, legacy: Callable[[Any], Any] | None = None) -> None:
    if meta.id in _registry:
        raise ValueError(f"Layer {meta.id} already registered")
    _registry[meta.id] = RegisteredLayer(meta=meta, fetch=fetch, legacy_writer=legacy)


def get(layer_id: str) -> RegisteredLayer | None:
    return _registry.get(layer_id)


def all_layers() -> list[RegisteredLayer]:
    return list(_registry.values())


def all_metas() -> list[LayerMeta]:
    return [r.meta for r in _registry.values() if r.meta.enabled]


def categories() -> dict[str, list[LayerMeta]]:
    out: dict[str, list[LayerMeta]] = {}
    for r in _registry.values():
        if not r.meta.enabled:
            continue
        out.setdefault(r.meta.category, []).append(r.meta)
    return out


def autodiscover() -> None:
    """Import every module in worldtwin.sources so they can self-register.

    Each source module calls `register(...)` at import time.
    """
    from . import sources

    for mod_info in pkgutil.iter_modules(sources.__path__):
        if mod_info.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"worldtwin.sources.{mod_info.name}")
        except Exception as e:
            import traceback
            print(f"[registry] Failed to load source '{mod_info.name}': {e}")
            traceback.print_exc()
