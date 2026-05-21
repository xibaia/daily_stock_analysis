# -*- coding: utf-8 -*-
"""Unit tests for the DeepEar bridge auth service."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.services.deepear_auth_service import DeepEarAuthService, DeepEarServiceError


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class DeepEarAuthServiceTestCase(unittest.TestCase):
    def test_returns_disabled_payload_when_feature_off(self) -> None:
        service = DeepEarAuthService(enabled=False)

        payload = service.build_session_payload()

        self.assertFalse(payload.enabled)
        self.assertIsNone(payload.public_url)
        self.assertIsNone(payload.token)

    def test_returns_existing_login_session(self) -> None:
        session = MagicMock()
        session.post.return_value = _FakeResponse(200, {"access_token": "token-1", "token_type": "bearer"})
        session.get.return_value = _FakeResponse(200, {"id": 7, "username": "deepear-bot"})

        service = DeepEarAuthService(
            enabled=True,
            internal_url="http://deepear:8765",
            public_url="http://127.0.0.1:8765",
            username="deepear-bot",
            password="secret",
            invitation_code="DEEP-EAR-ADMIN",
            session=session,
        )

        payload = service.build_session_payload()

        self.assertTrue(payload.enabled)
        self.assertEqual(payload.public_url, "http://127.0.0.1:8765")
        self.assertEqual(payload.token, "token-1")
        self.assertEqual(payload.user, {"id": 7, "username": "deepear-bot"})
        self.assertEqual(session.post.call_count, 1)

    def test_registers_service_account_when_login_initially_fails(self) -> None:
        session = MagicMock()
        session.post.side_effect = [
            _FakeResponse(401, {"detail": "Incorrect username or password"}),
            _FakeResponse(200, {"message": "User registered successfully"}),
            _FakeResponse(200, {"access_token": "token-2", "token_type": "bearer"}),
        ]
        session.get.return_value = _FakeResponse(200, {"id": 9, "username": "bridge-user"})

        service = DeepEarAuthService(
            enabled=True,
            internal_url="http://deepear:8765",
            public_url="http://127.0.0.1:8765",
            username="bridge-user",
            password="secret",
            invitation_code="DEEP-EAR-ADMIN",
            session=session,
        )

        payload = service.build_session_payload()

        self.assertEqual(payload.token, "token-2")
        self.assertEqual(session.post.call_count, 3)

    def test_raises_config_error_when_password_is_wrong_for_existing_account(self) -> None:
        session = MagicMock()
        session.post.side_effect = [
            _FakeResponse(401, {"detail": "Incorrect username or password"}),
            _FakeResponse(400, {"detail": "Username already registered"}),
        ]

        service = DeepEarAuthService(
            enabled=True,
            internal_url="http://deepear:8765",
            public_url="http://127.0.0.1:8765",
            username="bridge-user",
            password="wrong-secret",
            invitation_code="DEEP-EAR-ADMIN",
            session=session,
        )

        with self.assertRaises(DeepEarServiceError) as context:
            service.build_session_payload()

        self.assertEqual(context.exception.error, "deepear_service_credentials_invalid")


if __name__ == "__main__":
    unittest.main()
