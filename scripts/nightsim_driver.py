#!/usr/bin/env python3
"""Night-sim driver: onboards the scratch HA, collects hockey_score events
over websocket, asserts sensors, event sequence, payloads and the real
polling cadence read from the director's request log.

Talks ONLY to the quarantine container (via its container IP — it has no
published ports). No secrets anywhere: the seeded config entry uses the
fake key. Fails with a non-zero exit and prints everything it saw.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import websocket

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
CLIENT_ID = "http://nightsim.local/"

EVENT_TYPES = ("hockey_score_goal", "hockey_score_game_start", "hockey_score_game_end")


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def rest(host: str, method: str, path: str, body=None, token: str | None = None):
    req = urllib.request.Request(f"http://{host}:8123{path}", method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=20) as resp:
            payload = resp.read().decode()
    except urllib.error.HTTPError as err:
        detail = err.read().decode()[:400]
        raise RuntimeError(f"{method} {path} -> HTTP {err.code}: {detail}") from err
    return json.loads(payload) if payload.strip() else {}


def wait_up(host: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"http://{host}:8123/api/", timeout=5)
            return True
        except urllib.error.HTTPError as err:
            # Any HTTP answer means the API is up (401/400 are fine).
            if err.code < 500:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def redeem_code(host: str, code: str) -> str:
    """Exchange the onboarding authorization code for an access token."""
    form = urllib.parse.urlencode(
        {"grant_type": "authorization_code", "code": code, "client_id": CLIENT_ID}
    ).encode()
    req = urllib.request.Request(f"http://{host}:8123/auth/token", data=form, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"/auth/token -> HTTP {err.code}: {err.read().decode()[:300]}") from err
    token = payload.get("access_token")
    if not token:
        fail(f"/auth/token gave no access_token: {payload}")
    return token


def entry_reload(host: str, token: str, entry_id: str) -> None:
    """Reload one config entry — the restartless-update primitive Settings
    and the Marketplace use: unload + fresh setup, HA itself never stops."""
    rest(host, "POST", f"/api/config/config_entries/entry/{entry_id}/reload", token=token)


def onboard(host: str) -> str:
    """Complete the fresh container's onboarding; returns an access token.

    Flow (2026.10): the users step is unauthenticated and returns an
    authorization code; that code is redeemed at /auth/token; the remaining
    steps are Bearer-authenticated. The final browser-redirect step
    (integration) is not needed for API access and is skipped.
    """
    resp = rest(host, "POST", "/api/onboarding/users", {
        "client_id": CLIENT_ID,
        "username": "nightsim@local",
        "password": "nightsim-pass-1",
        "name": "Night Sim",
        "language": "sv-SE",
    })
    print("onboarding/users: auth code received")
    token = redeem_code(host, resp["auth_code"])
    rest(host, "POST", "/api/onboarding/core_config", token=token)
    print("onboarding: core_config done, access token OK")
    return token


class Collector:
    def __init__(self, host: str, token: str) -> None:
        self.ws = websocket.create_connection(f"ws://{host}:8123/api/websocket", timeout=10)
        hello = json.loads(self.ws.recv())
        if hello.get("type") != "auth_required":
            fail(f"websocket hello: {hello}")
        self.ws.send(json.dumps({"type": "auth", "access_token": token}))
        auth = json.loads(self.ws.recv())
        if auth.get("type") != "auth_ok":
            fail(f"websocket auth: {auth}")
        for i, event_type in enumerate(EVENT_TYPES, start=1):
            self.ws.send(json.dumps({"id": i, "type": "subscribe_events", "event_type": event_type}))
            self.ws.recv()
        self.ws.settimeout(1.0)
        self.events: list[tuple[str, dict]] = []

    def pump(self, seconds: float) -> list[tuple[str, dict]]:
        """Read websocket messages for a while, collecting hockey_score events."""
        deadline = time.monotonic() + seconds
        fresh: list[tuple[str, dict]] = []
        while time.monotonic() < deadline:
            try:
                message = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if message.get("type") != "event":
                continue
            event = message.get("event", {})
            event_type = event.get("event_type", "")
            if event_type.startswith("hockey_score_"):
                data = event.get("data", {})
                self.events.append((event_type, data))
                fresh.append((event_type, data))
                print(f"  EVENT {event_type}: {json.dumps(data, ensure_ascii=False)}")
        return fresh


def assert_standings_sensor(host: str, token: str) -> None:
    """sensor.hockey_team_standings: state = tracked position, full table."""
    standings = json.loads((FIXTURES / "standings.json").read_text())
    state = rest(
        host, "GET", "/api/states/sensor.hockey_team_standings", token=token
    )
    attrs = state.get("attributes", {})
    want_pos = str(standings.get("tracked_position"))
    if state.get("state") != want_pos:
        fail(
            f"standings state: expected {want_pos!r}, got {state.get('state')!r}"
        )
    rows = attrs.get("standings")
    if not isinstance(rows, list) or len(rows) != len(standings["standings"]):
        fail(
            f"standings rows: expected {len(standings['standings'])}, "
            f"got {rows if not isinstance(rows, list) else len(rows)}"
        )
    want = next(r for r in standings["standings"] if r.get("tracked"))
    tracked = [r for r in rows if isinstance(r, dict) and r.get("tracked")]
    if (
        len(tracked) != 1
        or tracked[0].get("team") != want["team"]
        or tracked[0].get("tp") != want["tp"]
    ):
        fail(f"standings tracked row mismatch: got {tracked}")


def assert_team_sensor(host: str, token: str, first: dict) -> None:
    state = rest(host, "GET", "/api/states/sensor.hockey_team", token=token)
    attrs = state.get("attributes", {})
    cur = first.get("current_game") or {}
    last = first.get("last_game") or {}
    team_name = first.get("team_name", "")
    if cur.get("home_team") == team_name:
        opponent = cur.get("away_team", "")
    else:
        opponent = cur.get("home_team", "")
    # Only values stable across consecutive polls are asserted here — the
    # live score advances while we onboard, and the event assertions own
    # the transitions.
    expected_state = "Live" if first.get("is_live") else "Idle"
    print(f"sensor.hockey_team: {state.get('state')} (expect {expected_state})")
    checks = {
        "state": (state.get("state"), expected_state),
        "is_live": (attrs.get("is_live"), bool(first.get("is_live"))),
        "current_game_date": (attrs.get("current_game_date"), cur.get("date", "")),
        "current_home_team": (attrs.get("current_home_team"), cur.get("home_team", "")),
        "last_result": (attrs.get("last_result"), last.get("team_result", "")),
        "last_overtime": (attrs.get("last_overtime"), bool(last.get("overtime"))),
        "opponent_name": (attrs.get("opponent_name"), opponent),
        "current_game (object)": (isinstance(attrs.get("current_game"), dict), True),
    }
    for name, (got, want) in checks.items():
        if got != want:
            fail(f"sensor.hockey_team {name}: expected {want!r}, got {got!r}")


def assert_badges_sensor(host: str, token: str) -> None:
    static = json.loads((FIXTURES / "static_badges.json").read_text())
    state = rest(host, "GET", "/api/states/sensor.hockey_team_badges", token=token)
    attrs = state.get("attributes", {})
    if state.get("state") != static.get("team_name"):
        fail(f"badges state: expected {static.get('team_name')!r}, got {state.get('state')!r}")
    for name, want in {
        "team_badge": static.get("team_badge"),
        "current_home_badge": static["current_game_badges"]["home_badge"],
        "next_away_badge": static["next_game_badges"]["away_badge"],
    }.items():
        if attrs.get(name) != want:
            fail(f"badges attribute {name}: expected {want!r}, got {attrs.get(name)!r}")


def assert_card_assets(host: str) -> None:
    """The integration serves its bundled card module itself (extra JS
    URL): the JS must be reachable unauthenticated and define both cards —
    and it must still be served after any entry reload."""
    url = f"http://{host}:8123/hockey_score_cards/hockey-score-cards.js"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            body = resp.read().decode()
    except Exception as err:
        fail(f"card module not served at {url}: {err}")
    required = (
        '"hockey-score-card"',
        '"hockey-score-standings-card"',
        '"sensor.hockey_team_standings"',
    )
    missing = [token for token in required if token not in body]
    if missing:
        fail(f"card module served but incomplete, missing: {missing}")
    print(f"card module served OK ({len(body)} bytes, both cards defined)")


def assert_cadence(log_path: Path, cadence: dict) -> None:
    """Verify the real request cadence from the director's own log."""
    if not log_path.is_file():
        print(f"cadence: no director log at {log_path} — skipping")
        return
    hits = [
        json.loads(line)
        for line in log_path.read_text().splitlines()
        if line.strip()
    ]
    team_ts = [h["ts"] for h in hits if h.get("path") == "/team" and h.get("status") == 200]
    gaps = [round(b - a, 2) for a, b in zip(team_ts, team_ts[1:])]
    print(f"cadence: {len(team_ts)} /team polls, gaps={gaps}")

    if cadence.get("check_idle_gap"):
        if not gaps or not 45 <= gaps[0] <= 90:
            fail(f"idle gap expected 45–90 s, got {gaps[0] if gaps else 'none'}")

    if cadence.get("check_live_gap"):
        window = 4
        found = any(
            all(1.2 <= gap <= 3.5 for gap in gaps[i : i + window])
            for i in range(max(len(gaps) - window + 1, 0))
        )
        if not found:
            fail("no 4 consecutive ~2 s gaps found — live cadence not happening")

    if cadence.get("check_single_poller"):
        # A zombie keeps whatever offset the reload left it at — the measured
        # boundary gap was 10 ms — so its gaps alternate delta / 2s-delta
        # forever: roughly HALF the live gaps go short, at ANY offset.
        # Consecutive-pair matching misses that (a 10 ms offset never pairs),
        # so COUNT instead: one coordinator restart boundary legitimately
        # makes ONE short gap (the fresh coordinator's immediate first
        # refresh); a zombie makes dozens.
        short = [g for g in gaps if g < 1.4]
        budget = cadence.get("short_gaps_allowed", 1)
        if len(short) > budget:
            fail(
                f"single-poller violated: {len(short)} short /team gaps "
                f"({short}) > {budget} allowed — a second coordinator "
                "survived the unload"
            )
        print(
            f"cadence: single-poller OK ({len(short)} short gap(s), "
            f"budget {budget})"
        )

    static_hits = [h for h in hits if h.get("path") == "/team/static" and h.get("status") == 200]
    print(f"cadence: /team/static fetched {len(static_hits)} time(s) (rollover refetch expected)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True, help="container IP of the scratch HA")
    parser.add_argument("--scenario", required=True, help="scenario json (expect_events + cadence)")
    parser.add_argument("--director-log", required=True)
    parser.add_argument("--boot-timeout", type=float, default=240)
    parser.add_argument("--run-timeout", type=float, default=300)
    parser.add_argument("--grace-seconds", type=float, default=10)
    args = parser.parse_args()

    scenario = json.loads(Path(args.scenario).read_text())
    expected: list[str] = scenario["expect_events"]
    cadence: dict = scenario.get("cadence", {})

    print(f"waiting for HA at {args.host}:8123 ...")
    if not wait_up(args.host, args.boot_timeout):
        fail("Home Assistant did not come up")
    token = onboard(args.host)
    print("onboarding OK")

    collector = Collector(args.host, token)
    print("subscribed to hockey_score_* events")

    # Sensors must appear once the integration's first refresh completed.
    deadline = time.monotonic() + 90
    first = json.loads((FIXTURES / f"{scenario['start_fixture']}.json").read_text())
    while time.monotonic() < deadline:
        try:
            assert_team_sensor(args.host, token, first)
            assert_badges_sensor(args.host, token)
            assert_standings_sensor(args.host, token)
            break
        except RuntimeError:
            collector.pump(2)
    else:
        fail("sensors did not appear within 90 s of HA being up")
    print("sensors verified: flat attributes match the contract")
    assert_card_assets(args.host)

    print(f"collecting events (expecting {len(expected)}) ...")
    reload_plan = scenario.get("reload") or None
    reloaded = False
    deadline = time.monotonic() + args.run_timeout
    while time.monotonic() < deadline and len(collector.events) < len(expected):
        collector.pump(2)
        if (
            reload_plan
            and not reloaded
            and len(collector.events) >= reload_plan["after_events"]
        ):
            print(
                f">>> reloading config entry {reload_plan['entry_id']} mid-game "
                "(restartless-update simulation, no HA restart) ..."
            )
            entry_reload(args.host, token, reload_plan["entry_id"])
            reloaded = True
            # Unload + setup + first refresh takes a moment: wait for the
            # sensors to come back with the same entity ids. The game is
            # LIVE by now — assert against the phase the scenario says we
            # are in, not the boot fixture.
            reload_now = json.loads(
                (FIXTURES / f"{reload_plan['expect_fixture']}.json").read_text()
            )
            settle = time.monotonic() + 60
            while time.monotonic() < settle:
                try:
                    assert_team_sensor(args.host, token, reload_now)
                    assert_standings_sensor(args.host, token)
                    break
                except RuntimeError:
                    collector.pump(1)
            else:
                fail("sensors did not come back after the entry reload")
            print(">>> sensors back after reload, entity ids intact")
    if len(collector.events) < len(expected):
        fail(
            f"timed out: expected {len(expected)} events, saw "
            f"{[t for t, _ in collector.events]}"
        )

    print(f"all {len(expected)} events in — grace of {args.grace_seconds}s to catch replays …")
    fresh = collector.pump(args.grace_seconds)
    if fresh:
        fail(f"REPLAYED events during grace: {[(t, d) for t, d in fresh]}")

    got_types = [t for t, _ in collector.events]
    if got_types != expected:
        fail(f"event sequence mismatch:\n  expected {expected}\n  got      {got_types}")

    for event_type, data in collector.events:
        if event_type == "hockey_score_goal":
            if data.get("team") != "Leksands IF" or int(data.get("rise", 0)) < 1:
                fail(f"goal payload broken: {data}")
        if event_type == "hockey_score_game_end":
            if data.get("team_result") != "win":
                fail(f"end payload broken: {data}")

    print("--- SUMMARY ---")
    print(f"events  : {len(got_types)} == expected, in order, no replays")
    assert_card_assets(args.host)  # still served after any entry reload
    assert_cadence(Path(args.director_log), cadence)
    print("PASS: night-sim green ✔")


if __name__ == "__main__":
    main()
