"""The continuity event engine — pure, no Home Assistant imports.

The whole point of this module (MARKETPLACE_PLAN.md §4): an event can only
exist when the integration itself watched the transition happen between two
consecutive successful /team polls. Outages, restarts and gaps re-baseline
silently; nothing is ever replayed; start/end fire at most once per fixture.

Event rules
-----------
* ``hockey_score_goal``        — the tracked team's score rises between two
  consecutive successful polls (opponent goals fire nothing, by design);
  ``rise`` = how many goals this single event carries. A finish poll can
  carry both the last goal and game_end (OT winner: goal rise 1 + end).
* ``hockey_score_game_start``  — is_live flips false→true, once per fixture
  (kickoff flapping cannot double-fire). A coordinator that boots mid-game
  baselines silently: no start event.
* ``hockey_score_game_end``    — the watched live fixture is confirmed
  finished with a real team_result, once per fixture. A result-less finish
  (4.5 h hard cap / level promoted score the API refuses to fabricate)
  defers the event until the schedule publishes the same fixture's final —
  the one sanctioned late fire, still once per fixture.

The state is deliberately in-memory only: a restart = a fresh
``initial_state()`` = a silent re-baseline. That is the restart rule.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .flatten import find_fixture, fixture_identity, perspective, tracked_side

EVENT_GOAL = "hockey_score_goal"
EVENT_GAME_START = "hockey_score_game_start"
EVENT_GAME_END = "hockey_score_game_end"


def period_from_detail(score_detail, fallback: str = "") -> str:
    """Best-effort period for an event composed from a finished game dict.

    last_game has no `period` key in real responses; the segment count of
    score_detail carries the same information (4 → OT, 5+ → SO), matching
    the API's own derivation.
    """
    detail = score_detail or ""
    segments = [s for s in detail.strip("()").split(",") if s.strip()]
    if len(segments) >= 5:
        return "SO"
    if len(segments) == 4:
        return "OT"
    return fallback


@dataclass(frozen=True)
class ContinuityState:
    """Everything the engine remembers between polls (memory only)."""

    prev_team: dict | None = None  # last successful /team raw (the baseline)
    live_fixture: tuple | None = None  # fixture we have observed live
    fired_start_for: tuple | None = None
    fired_end_for: tuple | None = None
    awaiting_result: tuple | None = None  # result-less finish, not yet ended


def initial_state() -> ContinuityState:
    return ContinuityState()


def on_poll_failure(state: ContinuityState) -> ContinuityState:
    """A failed poll breaks the consecutive-pair chain for events.

    Fixture bookkeeping (what we saw live / what we await a result for)
    survives, so a finish or a published result still lands later — but no
    score transition spanning the gap can ever produce an event.
    """
    return replace(state, prev_team=None)


def _fixture_of(game: dict) -> dict:
    return {k: game.get(k, "") for k in ("date", "time", "home_team", "away_team")}


def _game_payload(team_name: str, game: dict, period: str) -> dict:
    p = perspective(team_name, game)
    return {
        "team": team_name,
        "opponent": p["opponent_name"],
        "tracked_team_home": bool(p["team_home"]),
        "home_score": game.get("home_score"),
        "away_score": game.get("away_score"),
        "period": period,
        "score_detail": game.get("score_detail", ""),
        "fixture": _fixture_of(game),
    }


def _end_payload(team_name: str, last_game: dict) -> dict:
    p = perspective(team_name, last_game)
    return {
        "team": team_name,
        "opponent": p["opponent_name"],
        "team_result": last_game.get("team_result", ""),
        "team_score": p["team_score"],
        "opponent_score": p["opponent_score"],
        "overtime": last_game.get("overtime", False),
        "shootout": last_game.get("shootout", False),
        "score_detail": last_game.get("score_detail", ""),
        "fixture": _fixture_of(last_game),
    }


def on_poll_success(state: ContinuityState, team_data: dict):
    """Process one successful /team poll.

    Returns ``(events, new_state)`` where events is an ordered list of
    ``(event_type, payload_dict)``.
    """
    if not isinstance(team_data, dict):
        # Malformed payload: treat like a failed poll (re-baseline).
        return [], on_poll_failure(state)

    cur_live = bool(team_data.get("is_live"))
    cur_current = team_data.get("current_game") or {}
    cur_ident = fixture_identity(cur_current)
    team_name = team_data.get("team_name", "")

    # ---- Baseline poll (boot, first success after a gap, after restart):
    # never fires anything; swallows any rise that happened unseen.
    if state.prev_team is None:
        return [], replace(
            state,
            prev_team=team_data,
            live_fixture=cur_ident if cur_live else None,
        )

    prev = state.prev_team
    prev_live = bool(prev.get("is_live"))
    events: list[tuple[str, dict]] = []

    # ---- game_start: idle → live, once per fixture. The fired_start_for
    # guard is what makes kickoff flapping (true→false→true) fire at most
    # one start per game.
    fired_start = False
    if (
        not prev_live
        and cur_live
        and cur_ident is not None
        and state.fired_start_for != cur_ident
    ):
        events.append(
            (EVENT_GAME_START, _game_payload(team_name, cur_current, cur_current.get("period", "")))
        )
        fired_start = True

    # ---- goal: tracked-team score rise on the watched fixture, between
    # two consecutive successful polls. The watch identity still works on
    # the kickoff poll (prev current_game == the fixture that went live)
    # because upcoming scores are always 0 until the game starts.
    watch = state.live_fixture or fixture_identity(prev.get("current_game") or {})
    if watch is not None:
        prev_game = find_fixture(prev, watch)
        cur_game = find_fixture(team_data, watch)
        side = tracked_side(team_name, cur_game if cur_game is not None else prev_game)
        if prev_game is not None and cur_game is not None and side is not None:
            prev_score = prev_game.get(f"{side}_score")
            cur_score = cur_game.get(f"{side}_score")
            if (
                isinstance(prev_score, (int, float))
                and not isinstance(prev_score, bool)
                and isinstance(cur_score, (int, float))
                and not isinstance(cur_score, bool)
                and cur_score > prev_score
            ):
                period = cur_game.get("period") or period_from_detail(
                    cur_game.get("score_detail", "")
                )
                payload = _game_payload(team_name, cur_game, period)
                payload["rise"] = cur_score - prev_score
                events.append((EVENT_GOAL, payload))

    # ---- game_end: the observed-live fixture is confirmed finished.
    fired_end = False
    ended_fixture = None
    awaiting = state.awaiting_result
    if prev_live and not cur_live and state.live_fixture is not None:
        watched = state.live_fixture
        cur_last = team_data.get("last_game") or {}
        result = cur_last.get("team_result", "")
        if fixture_identity(cur_last) == watched and state.fired_end_for != watched:
            if result:
                # Watched finish with a real result. Includes the OT winner:
                # the same poll already delivered the winning goal above.
                events.append((EVENT_GAME_END, _end_payload(team_name, cur_last)))
                fired_end = True
                ended_fixture = watched
                awaiting = None
            else:
                # Result-less finish (hard cap / level promoted score).
                # Defers game_end until the schedule publishes this
                # fixture's final — the one sanctioned late fire.
                awaiting = watched

    # ---- resolution of a deferred (result-less) end.
    if awaiting is not None and not fired_end and state.fired_end_for != awaiting:
        cur_last = team_data.get("last_game") or {}
        if fixture_identity(cur_last) == awaiting and cur_last.get("team_result"):
            events.append((EVENT_GAME_END, _end_payload(team_name, cur_last)))
            fired_end = True
            ended_fixture = awaiting
            awaiting = None

    new_state = replace(
        state,
        prev_team=team_data,
        live_fixture=cur_ident if cur_live else None,
        fired_start_for=cur_ident if fired_start else state.fired_start_for,
        fired_end_for=ended_fixture if fired_end else state.fired_end_for,
        awaiting_result=awaiting,
    )
    return events, new_state
