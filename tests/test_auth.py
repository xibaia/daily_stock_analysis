# -*- coding: utf-8 -*-
"""Unit tests for src.auth module."""

import hashlib
import os
import secrets
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import src.auth as auth


def _reset_auth_globals() -> None:
    """Reset auth module globals for test isolation."""
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._user_password_hash_salt = None
    auth._user_password_hash_stored = None
    auth._rate_limit = {}


class AuthValidationTestCase(unittest.TestCase):
    """Test password validation."""

    def setUp(self) -> None:
        _reset_auth_globals()

    def test_validate_password_empty(self) -> None:
        self.assertIsNotNone(auth._validate_password(""))
        self.assertIsNotNone(auth._validate_password("   "))

    def test_validate_password_too_short(self) -> None:
        self.assertIsNotNone(auth._validate_password("12345"))

    def test_validate_password_valid(self) -> None:
        self.assertIsNone(auth._validate_password("123456"))
        self.assertIsNone(auth._validate_password("password123"))


class AuthPasswordHashTestCase(unittest.TestCase):
    """Test password hashing and verification."""

    def setUp(self) -> None:
        _reset_auth_globals()

    def test_verify_password_hash_correct(self) -> None:
        salt = secrets.token_bytes(32)
        pwd = "testpass123"
        derived = hashlib.pbkdf2_hmac(
            "sha256", pwd.encode("utf-8"), salt=salt, iterations=auth.PBKDF2_ITERATIONS
        )
        self.assertTrue(auth._verify_password_hash(pwd, salt, derived))

    def test_verify_password_hash_wrong_password(self) -> None:
        salt = secrets.token_bytes(32)
        pwd = "testpass123"
        derived = hashlib.pbkdf2_hmac(
            "sha256", pwd.encode("utf-8"), salt=salt, iterations=auth.PBKDF2_ITERATIONS
        )
        self.assertFalse(auth._verify_password_hash("wrong", salt, derived))

    def test_verify_password_hash_constant_time(self) -> None:
        """Verify compare_digest is used (constant-time)."""
        salt = secrets.token_bytes(32)
        derived = hashlib.pbkdf2_hmac(
            "sha256", b"x", salt=salt, iterations=auth.PBKDF2_ITERATIONS
        )
        self.assertFalse(auth._verify_password_hash("y", salt, derived))


class AuthSessionTestCase(unittest.TestCase):
    """Test session creation and verification."""

    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.addCleanup(self.temp_dir.cleanup)

    def _patch_env_and_run(
        self, auth_enabled: bool = True, test_fn=None
    ):
        with patch.object(auth, "_is_auth_enabled_from_env", return_value=auth_enabled):
            with patch.object(auth, "_get_data_dir", return_value=self.data_dir):
                auth._auth_enabled = auth_enabled
                if test_fn:
                    return test_fn()

    def test_create_session_returns_signed_payload(self) -> None:
        def run():
            tok = auth.create_session()
            self.assertTrue(tok, "session token should be non-empty")
            parts = tok.split(".")
            self.assertEqual(len(parts), 4, "format: nonce.ts.role.signature")
            nonce, ts, role, sig = parts
            self.assertTrue(nonce)
            self.assertTrue(ts.isdigit())
            self.assertEqual(role, "admin")
            self.assertTrue(sig)

            tok_user = auth.create_session("user")
            parts_user = tok_user.split(".")
            self.assertEqual(len(parts_user), 4)
            self.assertEqual(parts_user[2], "user")
            return tok

        self._patch_env_and_run(test_fn=run)

    def test_verify_session_valid_token(self) -> None:
        def run():
            tok = auth.create_session("admin")
            valid, role = auth.verify_session(tok)
            self.assertTrue(valid)
            self.assertEqual(role, "admin")

            tok_user = auth.create_session("user")
            valid_u, role_u = auth.verify_session(tok_user)
            self.assertTrue(valid_u)
            self.assertEqual(role_u, "user")

        self._patch_env_and_run(test_fn=run)

    def test_verify_session_expired(self) -> None:
        def run():
            past = time.time() - 48 * 3600
            with patch.object(auth, "time") as mock_time:
                mock_time.time.return_value = past
                tok = auth.create_session()
            valid, role = auth.verify_session(tok)
            self.assertFalse(valid, "48h-old token should be expired")
            self.assertIsNone(role)

        self._patch_env_and_run(test_fn=run)

    def test_verify_session_invalid_format(self) -> None:
        def run():
            valid, role = auth.verify_session("")
            self.assertFalse(valid)
            self.assertIsNone(role)
            valid, role = auth.verify_session("a.b")
            self.assertFalse(valid)
            self.assertIsNone(role)
            valid, role = auth.verify_session("invalid")
            self.assertFalse(valid)
            self.assertIsNone(role)
            # Old 3-part format should be rejected
            valid, role = auth.verify_session("nonce.ts.sig")
            self.assertFalse(valid)
            self.assertIsNone(role)

        self._patch_env_and_run(test_fn=run)

    def test_rotate_session_secret_overwrites_existing(self) -> None:
        def run():
            secret_path = self.data_dir / ".session_secret"
            secret_path.write_bytes(b"a" * 32)
            secret_path.chmod(0o600)
            old_secret = secret_path.read_bytes()

            auth.rotate_session_secret()

            new_secret = secret_path.read_bytes()
            self.assertNotEqual(old_secret, new_secret)
            self.assertEqual(auth._session_secret, new_secret)

        self._patch_env_and_run(test_fn=run)

    def test_load_session_secret_regenerates_invalid_length(self) -> None:
        def run():
            secret_path = self.data_dir / ".session_secret"
            secret_path.write_bytes(b"x")
            secret_path.chmod(0o600)

            tok = auth.create_session()
            self.assertTrue(tok)

            new_secret = secret_path.read_bytes()
            self.assertEqual(len(new_secret), 32)
            self.assertNotEqual(new_secret, b"x")

        self._patch_env_and_run(test_fn=run)


class AuthRateLimitTestCase(unittest.TestCase):
    """Test rate limiting."""

    def setUp(self) -> None:
        _reset_auth_globals()

    def test_rate_limit_allows_under_limit(self) -> None:
        self.assertTrue(auth.check_rate_limit("192.168.1.1"))

    def test_rate_limit_blocks_after_max_failures(self) -> None:
        ip = "10.0.0.99"
        for _ in range(auth.RATE_LIMIT_MAX_FAILURES):
            auth.record_login_failure(ip)
        self.assertFalse(auth.check_rate_limit(ip))

    def test_clear_rate_limit_resets_ip(self) -> None:
        ip = "10.0.0.100"
        for _ in range(auth.RATE_LIMIT_MAX_FAILURES):
            auth.record_login_failure(ip)
        self.assertFalse(auth.check_rate_limit(ip))
        auth.clear_rate_limit(ip)
        self.assertTrue(auth.check_rate_limit(ip))


class AuthSetPasswordTestCase(unittest.TestCase):
    """Test set_initial_password, change_password, overwrite_password."""

    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.addCleanup(self.temp_dir.cleanup)

    def _run_with_patch(self, fn):
        with patch.object(auth, "_is_auth_enabled_from_env", return_value=True):
            with patch.object(auth, "_get_data_dir", return_value=self.data_dir):
                auth._auth_enabled = True
                return fn()

    def test_set_initial_password_success(self) -> None:
        def run():
            err = auth.set_initial_password("password123")
            self.assertIsNone(err)
            self.assertIsNotNone(auth._password_hash_stored)
            self.assertTrue(auth.is_password_set())
            ok, role = auth.verify_password("password123")
            self.assertTrue(ok)
            self.assertEqual(role, "admin")

        self._run_with_patch(run)

    def test_has_stored_password_remains_true_after_auth_disabled(self) -> None:
        def run():
            err = auth.set_initial_password("password123")
            self.assertIsNone(err)
            self.assertTrue(auth.has_stored_password())

            auth._auth_enabled = False
            self.assertTrue(auth.has_stored_password())
            self.assertFalse(auth.is_password_set())

        self._run_with_patch(run)

    def test_verify_stored_password_when_auth_disabled(self) -> None:
        def run():
            err = auth.set_initial_password("password123")
            self.assertIsNone(err)

            auth._auth_enabled = False
            self.assertTrue(auth.verify_stored_password("password123"))
            self.assertFalse(auth.verify_stored_password("wrongpass"))

        self._run_with_patch(run)

    def test_is_auth_enabled_from_env_respects_env_file(self) -> None:
        custom_env = self.data_dir / "custom.env"
        custom_env.write_text("ADMIN_AUTH_ENABLED=true\n", encoding="utf-8")

        with patch.dict(os.environ, {"ENV_FILE": str(custom_env)}):
            auth._auth_enabled = None
            self.assertTrue(auth._is_auth_enabled_from_env())

    def test_refresh_auth_state_clears_session_secret_cache(self) -> None:
        def run():
            first_secret = auth.create_session()
            self.assertTrue(first_secret)
            self.assertIsNotNone(auth._session_secret)

            auth._session_secret = b"x" * 32
            auth.refresh_auth_state()
            self.assertNotEqual(auth._session_secret, b"x" * 32)

        self._run_with_patch(run)

    def test_set_initial_password_invalid(self) -> None:
        def run():
            self.assertIsNotNone(auth.set_initial_password(""))
            self.assertIsNotNone(auth.set_initial_password("12345"))

        self._run_with_patch(run)

    def test_change_password_success(self) -> None:
        def run():
            auth.set_initial_password("oldpass123")
            err = auth.change_password("oldpass123", "newpass456")
            self.assertIsNone(err)
            ok, role = auth.verify_password("oldpass123")
            self.assertFalse(ok)
            ok, role = auth.verify_password("newpass456")
            self.assertTrue(ok)
            self.assertEqual(role, "admin")

        self._run_with_patch(run)

    def test_change_password_wrong_current(self) -> None:
        def run():
            auth.set_initial_password("correctpass")
            err = auth.change_password("wrongpass", "newpass456")
            self.assertIsNotNone(err)
            ok, role = auth.verify_password("correctpass")
            self.assertTrue(ok)
            self.assertEqual(role, "admin")

        self._run_with_patch(run)

    def test_overwrite_password_cli_style(self) -> None:
        def run():
            auth.set_initial_password("original")
            err = auth.overwrite_password("resetpass")
            self.assertIsNone(err)
            ok, role = auth.verify_password("original")
            self.assertFalse(ok)
            ok, role = auth.verify_password("resetpass")
            self.assertTrue(ok)
            self.assertEqual(role, "admin")

        self._run_with_patch(run)


class AuthUserPasswordTestCase(unittest.TestCase):
    """Test user (guest) password operations."""

    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.addCleanup(self.temp_dir.cleanup)

    def _run_with_patch(self, fn):
        with patch.object(auth, "_is_auth_enabled_from_env", return_value=True):
            with patch.object(auth, "_get_data_dir", return_value=self.data_dir):
                auth._auth_enabled = True
                return fn()

    def test_set_user_password_success(self) -> None:
        def run():
            err = auth.set_user_password("userpass123")
            self.assertIsNone(err)
            self.assertTrue(auth.has_user_password())
            ok, role = auth.verify_password("userpass123")
            self.assertTrue(ok)
            self.assertEqual(role, "user")

        self._run_with_patch(run)

    def test_verify_password_admin_first(self) -> None:
        def run():
            auth.set_initial_password("adminpass")
            auth.set_user_password("userpass")
            ok, role = auth.verify_password("adminpass")
            self.assertTrue(ok)
            self.assertEqual(role, "admin")
            ok, role = auth.verify_password("userpass")
            self.assertTrue(ok)
            self.assertEqual(role, "user")
            ok, role = auth.verify_password("wrongpass")
            self.assertFalse(ok)
            self.assertIsNone(role)

        self._run_with_patch(run)

    def test_change_user_password_success(self) -> None:
        def run():
            auth.set_user_password("olduserpass")
            err = auth.change_user_password("olduserpass", "newuserpass")
            self.assertIsNone(err)
            ok, role = auth.verify_password("olduserpass")
            self.assertFalse(ok)
            ok, role = auth.verify_password("newuserpass")
            self.assertTrue(ok)
            self.assertEqual(role, "user")

        self._run_with_patch(run)

    def test_change_user_password_wrong_current(self) -> None:
        def run():
            auth.set_user_password("correctuser")
            err = auth.change_user_password("wronguser", "newpass")
            self.assertIsNotNone(err)
            ok, role = auth.verify_password("correctuser")
            self.assertTrue(ok)
            self.assertEqual(role, "user")

        self._run_with_patch(run)

    def test_user_password_not_required(self) -> None:
        """When no user password is set, only admin password works."""
        def run():
            auth.set_initial_password("adminpass")
            self.assertFalse(auth.has_user_password())
            ok, role = auth.verify_password("adminpass")
            self.assertTrue(ok)
            self.assertEqual(role, "admin")
            ok, role = auth.verify_password("randompass")
            self.assertFalse(ok)

        self._run_with_patch(run)


if __name__ == "__main__":
    unittest.main()
