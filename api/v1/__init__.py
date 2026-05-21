# -*- coding: utf-8 -*-
"""API v1 package exports."""

from __future__ import annotations

from typing import Any

__all__ = ["api_v1_router"]


def __getattr__(name: str) -> Any:
    """Lazily expose the v1 router to avoid eager endpoint imports."""

    if name == "api_v1_router":
        from api.v1.router import router as api_v1_router

        return api_v1_router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
