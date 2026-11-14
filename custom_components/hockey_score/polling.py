"""Pure polling-cadence decisions (no Home Assistant imports).

Rules (MARKETPLACE_PLAN.md §4):
* /team      — every 2 s while live, every 60 s while idle
* /team/static — every 15 min, plus an immediate refetch when any of the
  three fixtures rolls over (replaces the badge-refresh automation)
"""

from __future__ import annotations

from .flatten import fixture_identity

LIVE_POLL_SECONDS = 2
IDLE_POLL_SECONDS = 60
STATIC_TTL_SECONDS = 900
STANDINGS_TTL_SECONDS = 3600

_BADGE_SOURCE_KEYS = ("last_game", "current_game", "next_game")


def next_interval_seconds(is_live: bool) -> int:
    """The /team poll interval to use after a successful fetch."""
    return LIVE_POLL_SECONDS if is_live else IDLE_POLL_SECONDS


def should_fetch_standings(
    last_fetch_ts: float | None,
    now: float,
    ttl_seconds: float = STANDINGS_TTL_SECONDS,
) -> bool:
    """Standings change at most daily; a 1 h TTL keeps the sensor fresh
    without a per-poll refetch."""
    if last_fetch_ts is None:
        return True
    return (now - last_fetch_ts) >= ttl_seconds


def badge_key(team_data: dict) -> tuple:
    """Stable key over the identities of all three games (badge cache key)."""
    data = team_data if isinstance(team_data, dict) else {}
    return tuple(fixture_identity(data.get(key) or {}) for key in _BADGE_SOURCE_KEYS)


def should_fetch_static(
    prev_key: tuple | None,
    cur_key: tuple,
    last_fetch_ts: float | None,
    now: float,
    ttl_seconds: float = STATIC_TTL_SECONDS,
) -> bool:
    """True when /team/static must be (re)fetched on this update."""
    if last_fetch_ts is None:
        return True
    if prev_key is not None and cur_key != prev_key:
        return True  # fixture rollover — badges must follow immediately
    return (now - last_fetch_ts) >= ttl_seconds
