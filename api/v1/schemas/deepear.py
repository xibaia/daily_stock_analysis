# -*- coding: utf-8 -*-
"""DeepEar bridge API schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DeepEarUser(BaseModel):
    """Minimal DeepEar user payload returned to the web bridge."""

    id: int = Field(..., description="DeepEar user ID")
    username: str = Field(..., description="DeepEar username")


class DeepEarSessionResponse(BaseModel):
    """Bridge session payload for the embedded DeepEar page."""

    enabled: bool = Field(..., description="Whether DeepEar integration is enabled")
    public_url: Optional[str] = Field(default=None, description="Browser-accessible DeepEar base URL")
    token: Optional[str] = Field(default=None, description="DeepEar bearer token for SSO bridge")
    user: Optional[DeepEarUser] = Field(default=None, description="DeepEar user profile")
    expires_hint_seconds: Optional[int] = Field(default=None, description="Token lifetime hint in seconds")
