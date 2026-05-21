# -*- coding: utf-8 -*-
"""API v1 endpoint package exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "health",
    "analysis",
    "history",
    "stocks",
    "backtest",
    "system_config",
    "auth",
    "agent",
    "usage",
    "portfolio",
    "alerts",
    "deepear",
]


def __getattr__(name: str) -> Any:
    """Lazily import endpoint modules on first access."""

    if name in __all__:
        return import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
