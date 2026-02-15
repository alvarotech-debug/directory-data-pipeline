"""Tests for HTTP session manager."""

from datetime import datetime, timedelta

import pytest

from src.utils.session_manager import SessionManager, SessionState


class TestSessionState:
    """Tests for SessionState dataclass."""

    def test_token_validity_check(self):
        """Expired token returns False."""
        state = SessionState(
            auth_token="test_token",
            token_expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        assert not state.is_token_valid

    def test_valid_token(self):
        """Non-expired token returns True."""
        state = SessionState(
            auth_token="test_token",
            token_expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        assert state.is_token_valid

    def test_no_token(self):
        """No token returns False."""
        state = SessionState()
        assert not state.is_token_valid


class TestSessionManager:
    """Tests for SessionManager."""

    def test_headers_include_user_agent(self):
        """get_headers returns User-Agent."""
        manager = SessionManager()
        headers = manager.get_headers()

        assert "User-Agent" in headers
        assert len(headers["User-Agent"]) > 0
        assert "Mozilla" in headers["User-Agent"]

    def test_user_agent_rotation(self):
        """Multiple instances may return different UAs."""
        agents = set()
        for _ in range(20):
            manager = SessionManager()
            agents.add(manager.state.user_agent)

        # With 7 UAs and 20 trials, we should see at least 2
        assert len(agents) >= 2

    def test_cookie_persistence(self):
        """Cookies stored and included in headers."""
        manager = SessionManager()
        manager.update_cookies({"session": "abc123"})

        assert manager.state.cookies["session"] == "abc123"

    def test_create_client_configured(self):
        """Client has headers and cookies."""
        manager = SessionManager()
        manager.update_cookies({"test": "value"})

        client = manager.create_client()
        assert client is not None
        # Client should have follow_redirects enabled
        assert client.follow_redirects is True

    def test_auth_header_when_token_set(self):
        """Authorization header included when token is set."""
        manager = SessionManager()
        manager.state.auth_token = "my_secret_token"

        headers = manager.get_headers()
        assert headers["Authorization"] == "Bearer my_secret_token"

    def test_no_auth_header_by_default(self):
        """No Authorization header when no token."""
        manager = SessionManager()
        headers = manager.get_headers()
        assert "Authorization" not in headers
