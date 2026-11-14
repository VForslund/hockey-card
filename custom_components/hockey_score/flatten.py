"""Pure flattening: /team + /team/static JSON → HA sensor attributes.

Zero Home Assistant imports — imported by sensor.py inside HA and directly
by the pure unit tests.

Naming law (MARKETPLACE_PLAN.md §4 / §8.8): flat attributes mirror the
three API objects 1:1 under the prefixes current_* / last_* / next_*,
with the deliberate, documented exceptions:

* ``last_result``          ← the API's ``team_result``
* ``last_opponent``, ``last_team_score``, ``last_opponent_score``
                             ← tracked-team perspective on ``last_game``
* ``*_game_date`` / ``*_game_date``-style fields ← the API's ``date``/``time``

``is_live`` is the one and only discriminator (idle → current_* is the
upcoming game, live → it's this game). Objects pass through under their
API names, always agreeing with their flat twins.
"""

from __future__ import annotations


def _as_dict(value):
    """Defensive: garbage values (None, scalars, strings) read as empty."""
    return value if isinstance(value, dict) else {}


def fixture_identity(game: dict | None):
    """Stable identity of a game dict; None for empty/missing games."""
    if not isinstance(game, dict) or not game.get("date"):
        return None
    return (
        game.get("date", ""),
        game.get("time", ""),
        game.get("home_team", ""),
        game.get("away_team", ""),
    )


def find_fixture(data: dict, ident):
    """Locate a fixture by identity in current_game/last_game/next_game."""
    if ident is None:
        return None
    for key in ("current_game", "last_game", "next_game"):
        game = data.get(key) if isinstance(data, dict) else None
        if fixture_identity(game) == ident:
            return game
    return None


def tracked_side(team_name: str, game: dict | None):
    """'home' / 'away' for the tracked team in this game, else None."""
    if not isinstance(game, dict) or not team_name:
        return None
    if team_name == game.get("home_team"):
        return "home"
    if team_name == game.get("away_team"):
        return "away"
    return None


def perspective(team_name: str, game: dict | None) -> dict:
    """Tracked-team view of a game; blanked values when the side is unknown."""
    side = tracked_side(team_name, game)
    if side is None or not isinstance(game, dict):
        return {
            "team_score": None,
            "opponent_score": None,
            "opponent_name": "",
            "team_home": None,
            "home_score": None,
            "away_score": None,
        }
    opp = "away" if side == "home" else "home"
    return {
        "team_score": game.get(f"{side}_score"),
        "opponent_score": game.get(f"{opp}_score"),
        "opponent_name": game.get(f"{opp}_team", ""),
        "team_home": side == "home",
        "home_score": game.get("home_score"),
        "away_score": game.get("away_score"),
    }


def flatten_team(data: dict) -> dict:
    """Attributes for sensor.hockey_team (state is Live/Idle elsewhere)."""
    if not isinstance(data, dict):
        data = {}
    cur = _as_dict(data.get("current_game"))
    last = _as_dict(data.get("last_game"))
    nxt = _as_dict(data.get("next_game"))
    team_name = data.get("team_name", "")
    p_cur = perspective(team_name, cur)
    p_last = perspective(team_name, last)
    return {
        # The one and only discriminator.
        "is_live": bool(data.get("is_live")),
        # current_* mirrors current_game (live game while live, upcoming idle).
        "current_home_team": cur.get("home_team", ""),
        "current_away_team": cur.get("away_team", ""),
        "current_home_score": cur.get("home_score"),
        "current_away_score": cur.get("away_score"),
        "current_game_date": cur.get("date", ""),
        "current_game_time": cur.get("time", ""),
        "current_period": cur.get("period", ""),
        # last_* mirrors last_game (team_result renamed, + perspective fields).
        "last_result": last.get("team_result", ""),
        "last_opponent": p_last["opponent_name"],
        "last_home_team": last.get("home_team", ""),
        "last_away_team": last.get("away_team", ""),
        "last_home_score": last.get("home_score"),
        "last_away_score": last.get("away_score"),
        "last_team_score": p_last["team_score"],
        "last_opponent_score": p_last["opponent_score"],
        "last_overtime": last.get("overtime", False),
        "last_shootout": last.get("shootout", False),
        "last_score_detail": last.get("score_detail", ""),
        "last_game_date": last.get("date", ""),
        "last_game_time": last.get("time", ""),
        # next_* mirrors next_game (the game after the current/live one).
        "next_home_team": nxt.get("home_team", ""),
        "next_away_team": nxt.get("away_team", ""),
        "next_game_date": nxt.get("date", ""),
        "next_game_time": nxt.get("time", ""),
        # Tracked-team shortcuts on current_game, for one-line templates.
        "team_score": p_cur["team_score"],
        "opponent_score": p_cur["opponent_score"],
        "opponent_name": p_cur["opponent_name"],
        "team_home": p_cur["team_home"],
        # Objects pass through under their API names.
        "current_game": cur,
        "last_game": last,
        "next_game": nxt,
    }


def flatten_standings(data) -> dict:
    """Attributes for sensor.hockey_team_standings.

    Mirrors /team/standings as delivered: the table rows pass through under
    their API name, plus the tracked-team meta. Garbage tolerant.
    """
    if not isinstance(data, dict):
        data = {}
    rows = data.get("standings")
    if not isinstance(rows, list):
        rows = []
    return {
        "team_tag": data.get("team_tag", ""),
        "team_name": data.get("team_name", ""),
        "source_url": data.get("source_url", ""),
        "standings_updated": data.get("standings_updated", ""),
        "tracked_position": data.get("tracked_position"),
        "standings": rows,
    }

def flatten_static(data: dict) -> dict:
    """Attributes for sensor.hockey_team_badges."""
    if not isinstance(data, dict):
        data = {}
    cur = _as_dict(data.get("current_game_badges"))
    last = _as_dict(data.get("last_game_badges"))
    nxt = _as_dict(data.get("next_game_badges"))
    return {
        "team_tag": data.get("team_tag", ""),
        "team_name": data.get("team_name", ""),
        "team_badge": data.get("team_badge", ""),
        "current_home_badge": cur.get("home_badge", ""),
        "current_away_badge": cur.get("away_badge", ""),
        "last_home_badge": last.get("home_badge", ""),
        "last_away_badge": last.get("away_badge", ""),
        "next_home_badge": nxt.get("home_badge", ""),
        "next_away_badge": nxt.get("away_badge", ""),
        # Objects pass through under their API names.
        "current_game_badges": cur,
        "last_game_badges": last,
        "next_game_badges": nxt,
    }
