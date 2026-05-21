# -*- coding: utf-8 -*-
"""DeepEar bridge authentication service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


def _trim_env(name: str, default: str = "") -> str:
    """Read and trim one environment variable."""

    return (os.getenv(name, default) or default).strip()


@dataclass(frozen=True)
class DeepEarSessionPayload:
    """Normalized DeepEar bridge payload."""

    enabled: bool
    public_url: Optional[str] = None
    token: Optional[str] = None
    user: Optional[Dict[str, Any]] = None
    expires_hint_seconds: Optional[int] = None


class DeepEarServiceError(RuntimeError):
    """Raised when the DeepEar bridge cannot produce a usable session."""

    def __init__(self, *, status_code: int, error: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.message = message


class DeepEarAuthService:
    """Bridge DSA web sessions to a shared DeepEar service account."""

    def __init__(
        self,
        *,
        enabled: Optional[bool] = None,
        internal_url: Optional[str] = None,
        public_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        invitation_code: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        deepear_port = _trim_env("DEEPEAR_PORT", "8765")
        default_browser_url = f"http://127.0.0.1:{deepear_port}"

        if enabled is None:
            enabled = _trim_env("DEEPEAR_ENABLED", "false").lower() in {"1", "true", "yes", "on"}

        self.enabled = enabled
        self.internal_url = (internal_url or _trim_env("DEEPEAR_INTERNAL_URL", default_browser_url)).rstrip("/")
        self.public_url = (public_url or _trim_env("DEEPEAR_PUBLIC_URL", default_browser_url)).rstrip("/")
        self.username = username or _trim_env("DEEPEAR_SERVICE_USERNAME")
        self.password = password or _trim_env("DEEPEAR_SERVICE_PASSWORD")
        self.invitation_code = invitation_code or _trim_env("DEEPEAR_INVITATION_CODE")
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else float(_trim_env("DEEPEAR_REQUEST_TIMEOUT", "15"))
        self._session = session or requests.Session()

    def build_session_payload(self) -> DeepEarSessionPayload:
        """Return a DeepEar login session for the DSA bridge page."""

        if not self.enabled:
            return DeepEarSessionPayload(enabled=False)

        self._validate_required_config()

        token = self._login()
        if not token:
            token = self._register_then_login()

        if not token:
            raise DeepEarServiceError(
                status_code=502,
                error="deepear_login_failed",
                message="无法获取 DeepEar 登录令牌，请检查服务账号配置。",
            )

        user = self._fetch_current_user(token)

        return DeepEarSessionPayload(
            enabled=True,
            public_url=self.public_url,
            token=token,
            user=user,
            expires_hint_seconds=60 * 60 * 24 * 7,
        )

    def _validate_required_config(self) -> None:
        if not self.public_url:
            raise DeepEarServiceError(
                status_code=500,
                error="deepear_public_url_missing",
                message="缺少 DEEPEAR_PUBLIC_URL 配置。",
            )
        if not self.internal_url:
            raise DeepEarServiceError(
                status_code=500,
                error="deepear_internal_url_missing",
                message="缺少 DEEPEAR_INTERNAL_URL 配置。",
            )
        if not self.username or not self.password:
            raise DeepEarServiceError(
                status_code=500,
                error="deepear_service_credentials_missing",
                message="缺少 DeepEar 服务账号或密码配置。",
            )

    def _login(self) -> Optional[str]:
        response = self._safe_request(
            "post",
            "/api/auth/login",
            json={
                "username": self.username,
                "password": self.password,
            },
            allow_statuses={401},
        )
        if response.status_code != 200:
            return None
        payload = self._decode_json(response)
        token = payload.get("access_token")
        return token if isinstance(token, str) and token.strip() else None

    def _register_then_login(self) -> Optional[str]:
        if not self.invitation_code:
            raise DeepEarServiceError(
                status_code=500,
                error="deepear_invitation_code_missing",
                message="登录 DeepEar 失败，且未配置邀请码用于自动注册服务账号。",
            )

        response = self._safe_request(
            "post",
            "/api/auth/register",
            json={
                "username": self.username,
                "password": self.password,
                "invitation_code": self.invitation_code,
            },
            allow_statuses={400},
        )

        if response.status_code == 400:
            payload = self._decode_json(response)
            detail = str(payload.get("detail") or "")
            if "already registered" in detail.lower():
                raise DeepEarServiceError(
                    status_code=500,
                    error="deepear_service_credentials_invalid",
                    message="DeepEar 服务账号已存在，但当前密码无法登录，请检查 DEEPEAR_SERVICE_PASSWORD。",
                )
            raise DeepEarServiceError(
                status_code=500,
                error="deepear_registration_failed",
                message=f"DeepEar 自动注册失败：{detail or '未知错误'}",
            )

        return self._login()

    def _fetch_current_user(self, token: str) -> Dict[str, Any]:
        response = self._safe_request(
            "get",
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        payload = self._decode_json(response)

        try:
            user_id = int(payload["id"])
            username = str(payload["username"]).strip()
        except (KeyError, TypeError, ValueError) as exc:
            raise DeepEarServiceError(
                status_code=502,
                error="deepear_user_payload_invalid",
                message=f"DeepEar 用户信息格式异常：{exc}",
            ) from exc

        if not username:
            raise DeepEarServiceError(
                status_code=502,
                error="deepear_user_payload_invalid",
                message="DeepEar 返回了空用户名。",
            )

        return {"id": user_id, "username": username}

    def _safe_request(
        self,
        method: str,
        path: str,
        *,
        allow_statuses: Optional[set[int]] = None,
        **kwargs: Any,
    ) -> requests.Response:
        allow_statuses = allow_statuses or set()
        url = f"{self.internal_url}{path}"

        try:
            response = getattr(self._session, method)(url, timeout=self.timeout_seconds, **kwargs)
        except requests.RequestException as exc:
            raise DeepEarServiceError(
                status_code=503,
                error="deepear_unreachable",
                message=f"无法连接 DeepEar 服务：{exc}",
            ) from exc

        if response.status_code >= 400 and response.status_code not in allow_statuses:
            payload = self._decode_json(response)
            detail = payload.get("detail")
            if isinstance(detail, dict):
                detail_message = str(detail.get("message") or detail.get("error") or "").strip()
            else:
                detail_message = str(detail or payload.get("message") or payload.get("error") or "").strip()
            raise DeepEarServiceError(
                status_code=502,
                error="deepear_upstream_error",
                message=detail_message or f"DeepEar 上游接口返回异常状态码 {response.status_code}。",
            )

        return response

    @staticmethod
    def _decode_json(response: requests.Response) -> Dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        return payload if isinstance(payload, dict) else {}
