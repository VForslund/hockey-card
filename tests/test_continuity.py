"""The continuity engine: no phantom celebrations, by construction.

Every rule from MARKETPLACE_PLAN.md §4 is pinned here: baseline-init,
consecutive-poll rises only, gap ⇒ silent re-baseline, once per fixture,
result-less end defers until the schedule publishes, opponent goals never
fire the goal event.
"""

from conftest import load_fixture, replay, types_of

from hockey_score import continuity

GOAL = continuity.EVENT_GOAL
START = continuity.EVENT_GAME_START
END = continuity.EVENT_GAME_END

NYBRO_FIXTURE = {
    "date": "2026-11-18",
    "time": "19:00",
    "home_team": "Nybro Vikings IF",
    "away_team": "Leksands IF",
}


def test_first_poll_is_a_silent_baseline():
    # Boot straight into a live game with goals already scored: no replay.
    events = replay(["live_p2_1_0"])
    assert events == []


def test_goal_fires_on_tracked_rise_with_exact_payload():
    events = replay(["live_p1_0_0", "live_p1_0_0", "live_p2_1_0"])
    assert types_of(events) == [GOAL]
    assert events[0][1] == {
        "team": "Leksands IF",
        "opponent": "Nybro Vikings IF",
        "tracked_team_home": False,
        "home_score": 0,
        "away_score": 1,
        "rise": 1,
        "period": "P2",
        "score_detail": "(0-0, 1-0)",
        "fixture": NYBRO_FIXTURE,
    }


def test_two_goals_in_one_poll_window_are_one_event_with_rise_2():
    later = load_fixture("live_p2_1_0")
    later["current_game"]["away_score"] = 2
    later["current_game"]["period"] = "P3"
    events = replay(["live_p1_0_0", later])
    assert types_of(events) == [GOAL]
    assert events[0][1]["rise"] == 2


def test_outage_goal_is_never_replayed_on_recovery():
    # 1-0 ... [poll fails] ... recovery shows 2-2: silent re-baseline. The
    # out-of-band goal must not celebrate on recovery.
    events = replay(["live_p2_1_0", "live_ot_2_2", "live_ot_2_2"], failures={2})
    assert events == []


def test_after_recovery_only_newly_watched_rises_fire():
    # Continuing from the outage: 2-2 → 3-2 is two consecutive polls we
    # made ourselves, so the OT winner DOES celebrate — once, plus the end.
    events = replay(
        ["live_p2_1_0", "live_ot_2_2", "live_ot_2_2", "finished_ot_win"],
        failures={2},
    )
    assert types_of(events) == [GOAL, END]
    assert events[0][1]["rise"] == 1
    assert events[1][1]["team_result"] == "win"


def test_opponent_goal_fires_nothing():
    events = replay(["live_p2_1_0", "live_p2_1_1"])  # Nybro equalizes
    assert events == []


def test_score_correction_downward_fires_nothing():
    corrected = load_fixture("live_p2_1_1")
    corrected["current_game"]["away_score"] = 0  # LIF's goal corrected away
    events = replay(["live_p2_1_1", corrected])
    assert events == []


def test_game_start_fires_once_per_fixture():
    events = replay(["idle_vik_ot", "live_p1_0_0"])
    assert types_of(events) == [START]
    assert events[0][1] == {
        "team": "Leksands IF",
        "opponent": "Nybro Vikings IF",
        "tracked_team_home": False,
        "home_score": 0,
        "away_score": 0,
        "period": "P1",
        "score_detail": "",
        "fixture": NYBRO_FIXTURE,
    }


def test_kickoff_flapping_fires_a_single_start():
    # live → flap off → live again at puck drop (a known API behavior):
    # one start. The goal after re-live is a legitimately watched pair.
    events = replay(
        ["idle_vik_ot", "live_p1_0_0", "idle_vik_ot", "live_p1_0_0", "live_p2_1_0"]
    )
    assert types_of(events).count(START) == 1
    assert types_of(events).count(GOAL) == 1


def test_midgame_join_never_fires_start():
    # Coordinator boots with the game already running: silent baseline.
    events = replay(["live_p2_1_0", "live_p2_1_0", "live_ot_2_2", "finished_ot_win"])
    assert types_of(events) == [GOAL, GOAL, END]
    assert START not in types_of(events)


def test_ot_winner_delivers_goal_and_end_in_one_poll():
    # Boots mid-game (joiner: silent baseline), watches the equalizer and
    # then the same poll delivering the OT-winning goal AND game_end.
    events = replay(["live_p2_1_0", "live_ot_2_2", "live_ot_2_2", "finished_ot_win"])
    assert types_of(events) == [GOAL, GOAL, END]
    winner, end = events[1][1], events[2][1]
    # The winning goal carries the final score; last_game has no period
    # key, so the OT period is derived from score_detail (4 segments).
    assert winner["away_score"] == 3
    assert winner["rise"] == 1
    assert winner["period"] == "OT"
    assert end == {
        "team": "Leksands IF",
        "opponent": "Nybro Vikings IF",
        "team_result": "win",
        "team_score": 3,
        "opponent_score": 2,
        "overtime": True,
        "shootout": False,
        "score_detail": "(0-0, 1-1, 1-1, 1-1)",
        "fixture": NYBRO_FIXTURE,
    }


def test_resultless_finish_defers_end_until_schedule_publishes():
    # 4.5 h hard cap / level promoted score: the finish has no real result
    # yet, so game_end waits for the same-fixture schedule override and
    # fires exactly once, when the result lands. Joined mid-game (silent
    # baseline), watched the whole cap-exit — no goal, no early end.
    events = replay(
        [
            "live_ot_2_2",
            "finished_resultless",
            "finished_resultless",
            "finished_ot_win",
            "finished_ot_win",
        ]
    )
    assert types_of(events) == [END]
    assert events[0][1]["team_result"] == "win"
    assert events[0][1]["team_score"] == 3


def test_end_never_refires_for_a_repeated_result():
    events = replay(
        [
            "idle_vik_ot",
            "live_ot_2_2",
            "finished_ot_win",
            "finished_ot_win",
            "finished_ot_win",
        ]
    )
    assert types_of(events).count(END) == 1


def test_restart_swallows_goals_that_happened_while_down():
    # HA was down while LIF equalized to 2-2; on boot the score is already
    # there. The baseline poll and its successor must stay silent.
    events = replay(["live_ot_2_2", "live_ot_2_2"])
    assert events == []


def test_idle_fixture_rollover_fires_nothing():
    events = replay(
        [
            "idle_vik_ot",
            "idle_vik_ot",
            "idle_after_rollover",
            "idle_after_rollover",
        ]
    )
    assert events == []


def test_malformed_payload_mid_game_fires_nothing():
    garbage = load_fixture("live_p2_1_0")
    garbage["current_game"] = "nonsense"
    events = replay(["live_p1_0_0", garbage])
    assert events == []
    # And the engine keeps working afterwards:
    events = replay(["live_p1_0_0", garbage, "live_p2_1_1"])
    assert events == []
