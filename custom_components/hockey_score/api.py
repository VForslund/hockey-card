"""HTTP client for the hockey-api service.

Kept separate from the pure logic modules (flatten/continuity/polling):
this file imports aiohttp and only runs inside Home Assistant.
"""

from __future__ import annotations

import aiohttp


class HockeyApiError(Exception):
    """Base error for all hockey-api failures."""


class HockeyApiAuthError(HockeyApiError):
    """401/403 — the API key or URL is wrong."""


class HockeyApiConnectionError(HockeyApiError):
    """Timeout, DNS, refused connection, TLS — the API was unreachable."""


def normalize_url(url: str) -> str:
    """Strip whitespace and trailing slashes; require http(s).

    Raises ValueError on anything else (surfaced as 'invalid_url' in the
    config flow).
    """
    cleaned = (url or "").strip().rstrip("/")
    if not cleaned.startswith(("http://", "https://")):
        raise ValueError(f"not an http(s) URL: {url!r}")
    return cleaned


class HockeyApiClient:
    """Minimal authenticated GET client for /team and /team/static."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str, api_key: str) -> None:
        self._session = session
        self._base_url = normalize_url(base_url)
        self._api_key = api_key

    @property
    def base_url(self) -> str:
        return self._base_url

    async def _get(self, path: str) -> dict:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with self._session.get(
                f"{self._base_url}{path}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (401, 403):
                    raise HockeyApiAuthError(f"{path}: {resp.status}")
                if resp.status >= 400:
                    raise HockeyApiError(f"{path}: HTTP {resp.status}")
                try:
                    data = await resp.json(content_type=None)
                except ValueError as err:
                    raise HockeyApiError(f"{path}: invalid JSON") from err
        except HockeyApiError:
            raise
        except (TimeoutError, aiohttp.ClientError) as err:
            # type name included: bare timeouts stringify to "", HA logs
            # must be able to tell timeout / refused / DNS from each other
            raise HockeyApiConnectionError(
                f"{path}: {type(err).__name__}: {err}"
            ) from err
        if not isinstance(data, dict):
            raise HockeyApiError(f"{path}: unexpected payload")
        return data

    async def async_get_team(self) -> dict:
        """GET /team — game data (last / current / next)."""
        return await self._get("/team")

    async def async_get_static(self) -> dict:
        """GET /team/static — badges for the last/current/next opponents."""
        return await self._get("/team/static")

    async def async_get_standings(self) -> dict:
        """GET /team/standings — the tracked team's league table."""
        return await self._get("/team/standings")

    async def async_validate_credentials(self) -> dict:
        """Live validation for the config flow: any successful /team read."""
        return await self._get("/team")
