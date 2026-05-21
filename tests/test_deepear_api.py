# -*- coding: utf-8 -*-
"""Integration tests for the DeepEar bridge API."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.auth as auth
from api.middlewares.auth import add_auth_middleware
from api.v1.endpoints import deepear
from src.services.deepear_auth_service import DeepEarAuthService, DeepEarServiceError


class _DisabledService:
    def build_session_payload(self):
        return DeepEarAuthService(enabled=False).build_session_payload()


class _SuccessService:
    def build_session_payload(self):
        return DeepEarAuthService(enabled=False).build_session_payload().__class__(
            enabled=True,
            public_url="http://127.0.0.1:8765",
            token="bridge-token",
            user={"id": 1, "username": "deepear-bot"},
            expires_hint_seconds=604800,
        )


class _FailureService:
    def build_session_payload(self):
        raise DeepEarServiceError(
            status_code=503,
            error="deepear_unreachable",
            message="无法连接 DeepEar 服务。",
        )


class DeepEarApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        auth._auth_enabled = True
        auth._session_secret = None
        auth._password_hash_salt = None
        auth._password_hash_stored = None
        auth._user_password_hash_salt = None
        auth._user_password_hash_stored = None
        auth._rate_limit = {}

        self.verify_session_patcher = patch("api.middlewares.auth.verify_session", return_value=(True, "admin"))
        self.is_auth_enabled_patcher = patch("api.middlewares.auth.is_auth_enabled", return_value=True)
        self.verify_session_patcher.start()
        self.is_auth_enabled_patcher.start()

    def tearDown(self) -> None:
        self.verify_session_patcher.stop()
        self.is_auth_enabled_patcher.stop()

    def _build_client(self, service) -> TestClient:
        app = FastAPI()
        app.include_router(deepear.router, prefix="/api/v1/deepear")
        add_auth_middleware(app)
        app.dependency_overrides[deepear.get_deepear_auth_service] = lambda: service
        return TestClient(app)

    def test_requires_dsa_login_cookie(self) -> None:
        client = self._build_client(_DisabledService())

        response = client.get("/api/v1/deepear/session")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "unauthorized")

    def test_returns_disabled_payload_when_feature_is_off(self) -> None:
        client = self._build_client(_DisabledService())

        response = client.get("/api/v1/deepear/session", cookies={"dsa_session": "valid-session-token"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"enabled": False, "public_url": None, "token": None, "user": None, "expires_hint_seconds": None})

    def test_returns_session_payload_when_bridge_succeeds(self) -> None:
        client = self._build_client(_SuccessService())

        response = client.get("/api/v1/deepear/session", cookies={"dsa_session": "valid-session-token"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["enabled"])
        self.assertEqual(data["public_url"], "http://127.0.0.1:8765")
        self.assertEqual(data["token"], "bridge-token")
        self.assertEqual(data["user"]["username"], "deepear-bot")

    def test_surfaces_bridge_errors(self) -> None:
        client = self._build_client(_FailureService())

        response = client.get("/api/v1/deepear/session", cookies={"dsa_session": "valid-session-token"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["error"], "deepear_unreachable")


if __name__ == "__main__":
    unittest.main()
