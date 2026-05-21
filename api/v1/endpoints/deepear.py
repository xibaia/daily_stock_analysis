# -*- coding: utf-8 -*-
"""DeepEar bridge endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_deepear_auth_service
from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.deepear import DeepEarSessionResponse
from src.services.deepear_auth_service import DeepEarAuthService, DeepEarServiceError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/session",
    response_model=DeepEarSessionResponse,
    responses={
        200: {"description": "DeepEar bridge session loaded"},
        500: {"description": "DeepEar bridge config invalid", "model": ErrorResponse},
        502: {"description": "DeepEar upstream error", "model": ErrorResponse},
        503: {"description": "DeepEar service unavailable", "model": ErrorResponse},
    },
    summary="Get DeepEar embedded session",
    description="Returns a DeepEar bearer token for the embedded bridge page after DSA auth succeeds.",
)
def get_deepear_session(
    service: DeepEarAuthService = Depends(get_deepear_auth_service),
) -> DeepEarSessionResponse:
    """Return a DeepEar bridge session payload."""

    try:
        payload = service.build_session_payload()
        return DeepEarSessionResponse(
            enabled=payload.enabled,
            public_url=payload.public_url,
            token=payload.token,
            user=payload.user,
            expires_hint_seconds=payload.expires_hint_seconds,
        )
    except DeepEarServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "error": exc.error,
                "message": exc.message,
            },
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive branch
        logger.error("Failed to create DeepEar bridge session: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "deepear_internal_error",
                "message": "创建 DeepEar 会话失败。",
            },
        ) from exc
