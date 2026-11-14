"""flatten: the flat surface IS the API mirror (the §4 naming law).

The Gold fixture is the real /team capture from 2026-11-14 (idle, one day
after the VIK 0-1 LIF overtime win). These tests lock down every attribute
name and value the card and friend templates depend on.
"""

from conftest import load_fixture

from hockey_score import flatten

FLAT_TEAM_KEYS = {
    "is_live",
    "current_home_team", "current_away_team",
    "current_home_score", "current_away_score",
    "current_game_date", "current_game_time", "current_period",
    "last_result", "last_opponent",
    "last_home_team", "last_away_team",
    "last_home_score", "last_away_score",
    "last_team_score", "last_opponent_score",
    "last_overtime", "last_shootout", "last_score_detail",
    "last_game_date", "last_game_time",
    "next_home_team", "next_away_team",
    "next_game_date", "next_game_time",
    "team_score", "opponent_score", "opponent_name", "team_home",
    "current_game", "last_game", "next_game",
}


def test_idle_gold_contract():
    data = load_fixture("idle_vik_ot")
    attrs = flatten.flatten_team(data)
    assert set(attrs) == FLAT_TEAM_KEYS
    assert attrs["is_live"] is False
    # current_* = the upcoming Nybro fixture (the idle face of current_game).
    assert attrs["current_home_team"] == "Nybro Vikings IF"
    assert attrs["current_away_team"] == "Leksands IF"
    assert attrs["current_home_score"] == 0
    assert attrs["current_away_score"] == 0
    assert attrs["current_game_date"] == "2026-11-18"
    assert attrs["current_game_time"] == "19:00"
    assert attrs["current_period"] == ""
    # last_* = the VIK overtime win, tracked-team perspective.
    assert attrs["last_result"] == "win"
    assert attrs["last_opponent"] == "Västerås IK"
    assert attrs["last_home_team"] == "Västerås IK"
    assert attrs["last_away_team"] == "Leksands IF"
    assert attrs["last_team_score"] == 1
    assert attrs["last_opponent_score"] == 0
    assert attrs["last_overtime"] is True
    assert attrs["last_shootout"] is False
    assert attrs["last_score_detail"] == "(0-0, 0-0, 0-0, 0-1)"
    assert attrs["last_game_date"] == "2026-11-13"
    assert attrs["last_game_time"] == "19:00"
    # next_* = the fixture after the current one (the API's next_game).
    assert attrs["next_home_team"] == "Leksands IF"
    assert attrs["next_away_team"] == "Visby/Roma HK"
    assert attrs["next_game_date"] == "2026-11-20"
    assert attrs["next_game_time"] == "19:00"
    # tracked-team shortcuts: perspective of current_game (upcoming scores 0).
    assert attrs["team_score"] == 0
    assert attrs["opponent_score"] == 0
    assert attrs["opponent_name"] == "Nybro Vikings IF"
    assert attrs["team_home"] is False
    # Objects pass through under API names and agree with their flat twins.
    assert attrs["current_game"] == data["current_game"]
    assert attrs["last_game"] == data["last_game"]
    assert attrs["next_game"] == data["next_game"]


def test_live_contract():
    attrs = flatten.flatten_team(load_fixture("live_p2_1_0"))
    assert attrs["is_live"] is True
    assert attrs["current_period"] == "P2"
    assert attrs["current_home_score"] == 0
    assert attrs["current_away_score"] == 1
    assert attrs["team_score"] == 1
    assert attrs["opponent_score"] == 0
    assert attrs["opponent_name"] == "Nybro Vikings IF"
    assert attrs["team_home"] is False


def test_offseason_blank_contract():
    # last_* blanks when last_game is older than 31 days; friends must
    # guard templates with {% if last_result %} — these are the blanks.
    attrs = flatten.flatten_team(load_fixture("offseason"))
    assert attrs["last_result"] == ""
    assert attrs["last_game_date"] == ""
    assert attrs["last_home_score"] is None
    assert attrs["last_team_score"] is None
    assert attrs["current_game_date"] == ""
    assert attrs["next_game_date"] == ""
    assert attrs["team_home"] is None
    assert attrs["opponent_name"] == ""


def test_static_contract():
    data = load_fixture("static_badges")
    attrs = flatten.flatten_static(data)
    assert attrs["team_tag"] == data["team_tag"]
    assert attrs["team_name"] == data["team_name"]
    assert attrs["team_badge"] == data["team_badge"]
    assert attrs["current_home_badge"] == data["current_game_badges"]["home_badge"]
    assert attrs["current_away_badge"] == data["current_game_badges"]["away_badge"]
    assert attrs["last_home_badge"] == data["last_game_badges"]["home_badge"]
    assert attrs["last_away_badge"] == data["last_game_badges"]["away_badge"]
    assert attrs["next_home_badge"] == data["next_game_badges"]["home_badge"]
    assert attrs["next_away_badge"] == data["next_game_badges"]["away_badge"]
    assert attrs["current_game_badges"] == data["current_game_badges"]


def test_standings_contract():
    # Real HockeyAllsvenskan table captured 2026-11-14 (scrubbed timestamp).
    data = load_fixture("standings")
    attrs = flatten.flatten_standings(data)
    assert attrs["team_tag"] == "leksands if"
    assert attrs["team_name"] == "Leksands IF"
    assert attrs["tracked_position"] == 2
    assert attrs["source_url"].endswith("/ScheduleAndResults/Standings/20962")
    rows = attrs["standings"]
    assert len(rows) == 14
    assert rows[0]["team"] == "AIK"
    assert (rows[0]["gp"], rows[0]["w"], rows[0]["t"], rows[0]["l"]) == (19, 12, 5, 2)
    assert (rows[0]["gf"], rows[0]["ga"], rows[0]["gd"], rows[0]["tp"]) == (72, 51, 21, 44)
    lif = rows[1]
    assert lif["team"] == "Leksands IF"
    assert lif["tracked"] is True
    assert rows[0]["tracked"] is False
    assert (lif["w"], lif["t"], lif["l"], lif["tp"]) == (12, 3, 4, 41)
    assert (lif["otw"], lif["otl"], lif["gwsw"], lif["gwsl"]) == (2, 0, 0, 1)


def test_standings_garbage_never_raises():
    flatten.flatten_standings(None)
    flatten.flatten_standings({"standings": "junk"})
    flatten.flatten_standings({"standings": [1, 2, {"team": "x"}]})
    attrs = flatten.flatten_standings({"team_name": "Leksands IF"})
    assert attrs["standings"] == []
    assert attrs["tracked_position"] is None


def test_garbage_input_never_raises():
    flatten.flatten_team({})
    flatten.flatten_team(None)
    flatten.flatten_team({"current_game": None, "last_game": 3})
    flatten.flatten_static(None)
    flatten.flatten_static({"current_game_badges": None})
