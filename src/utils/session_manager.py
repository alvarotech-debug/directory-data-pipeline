"""
HTTP session management with cookie and token persistence.

In production scraping of professional registries, many sites
require session cookies or authentication tokens. This manager
handles:
- Session cookie persistence across requests
- Token refresh for authenticated APIs
- Header management (User-Agent rotation, Accept headers)
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime

import httpx


@dataclass
class SessionState:
    """Current session state."""

    cookies: dict = field(default_factory=dict)
    auth_token: str | None = None
    token_expires_at: datetime | None = None
    user_agent: str = ""
    request_count: int = 0

    @property
    def is_token_valid(self) -> bool:
        """Check if auth token is still valid."""
        if not self.auth_token or not self.token_expires_at:
            return False
        return datetime.utcnow() < self.token_expires_at


class SessionManager:
    """
    Manages HTTP session state for scraping operations.

    Features:
    - User-Agent rotation from realistic browser strings
    - Cookie jar persistence across requests
    - Auth token refresh when expired
    - Request counting for rate limit awareness
    """

    USER_AGENTS = [
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
            "Gecko/20100101 Firefox/121.0"
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.2 Safari/605.1.15"
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        ),
        (
            "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) "
            "Gecko/20100101 Firefox/121.0"
        ),
    ]

    def __init__(self) -> None:
        self.state = SessionState()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._rotate_user_agent()

    def get_headers(self) -> dict:
        """Build request headers with current session state."""
        headers = {
            "User-Agent": self.state.user_agent,
            "Accept": "application/json, text/html;q=0.9",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
        if self.state.auth_token:
            headers["Authorization"] = (
                f"Bearer {self.state.auth_token}"
            )
        return headers

    def _rotate_user_agent(self) -> None:
        """Select a random User-Agent string."""
        self.state.user_agent = random.choice(self.USER_AGENTS)

    async def refresh_token(
        self, auth_url: str, credentials: dict
    ) -> None:
        """
        Refresh authentication token.

        In production, this would POST to the auth endpoint
        with credentials and store the returned token.
        Placeholder for registry-specific auth flows.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                auth_url, json=credentials, timeout=15
            )
            response.raise_for_status()
            data = response.json()
            self.state.auth_token = data.get("access_token")
            self.logger.info("Auth token refreshed")

    def update_cookies(self, response_cookies: dict) -> None:
        """Merge response cookies into session state."""
        self.state.cookies.update(response_cookies)

    def create_client(self) -> httpx.AsyncClient:
        """Create a configured httpx client with session state."""
        return httpx.AsyncClient(
            headers=self.get_headers(),
            cookies=self.state.cookies,
            follow_redirects=True,
            timeout=30,
        )
