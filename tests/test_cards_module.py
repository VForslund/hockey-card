"""Guards for the bundled frontend module (www/hockey-score-cards.js) —
the file behind custom:hockey-score-card and
custom:hockey-score-standings-card, served by the integration itself.

Plain text checks on purpose: the module is build-less vanilla JS. When a
node runtime exists (dev box and GitHub runners both have one) the module
is additionally syntax-checked.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from conftest import PKG_DIR

CARDS_JS = PKG_DIR / "www" / "hockey-score-cards.js"
MANIFEST = PKG_DIR / "manifest.json"

# The scoreboard reads exactly these flat attributes (flatten.py contract,
# MARKETPLACE_PLAN.md §4/§5): one prefix per slot, is_live cosmetic only.
SCOREBOARD_FLATS = (
    "is_live",
    "current_home_team",
    "current_away_team",
    "current_home_score",
    "current_away_score",
    "current_game_date",
    "current_game_time",
    "current_period",
    "last_result",
    "last_home_team",
    "last_away_team",
    "last_home_score",
    "last_away_score",
    "last_overtime",
    "last_shootout",
    "last_game_date",
    "next_home_team",
    "next_away_team",
    "next_game_date",
    "next_game_time",
)

SCOREBOARD_BADGE_FLATS = (
    "current_home_badge",
    "current_away_badge",
    "last_home_badge",
    "last_away_badge",
    "next_home_badge",
    "next_away_badge",
)


def test_module_defines_both_cards():
    js = CARDS_JS.read_text(encoding="utf-8")
    assert 'customElements.define("hockey-score-card"' in js
    assert 'customElements.define("hockey-score-standings-card"' in js


def test_scoreboard_reads_the_flat_contract():
    js = CARDS_JS.read_text(encoding="utf-8")
    for attr in SCOREBOARD_FLATS + SCOREBOARD_BADGE_FLATS:
        assert attr in js, f"scoreboard lost the {attr} flat attribute"


def test_cards_default_to_the_contract_entities():
    js = CARDS_JS.read_text(encoding="utf-8")
    for entity in (
        "sensor.hockey_team",
        "sensor.hockey_team_badges",
        "sensor.hockey_team_standings",
    ):
        assert f'"{entity}"' in js


def test_standings_table_shape():
    js = CARDS_JS.read_text(encoding="utf-8")
    for column in (">GP<", ">W-T-L<", ">GD<", ">TP<"):
        assert column in js, f"standings table lost its {column} column"
    for key in ("r.tracked", "r.badge", "r.team", "r.gp", "r.tp"):
        assert key in js, f"standings table lost the row.{key.split('.')[-1]} key"


def test_module_carries_no_hosts_or_secrets():
    # The repo goes public one day: the card JS must be hostless (badge and
    # JS URLs all arrive via sensor attributes at runtime) and keyless.
    js = CARDS_JS.read_text(encoding="utf-8").lower()
    assert "forslund" not in js
    assert "http://" not in js
    assert "https://" not in js
    assert "api_key" not in js


def test_manifest_version_fits_the_cache_busting_url():
    # __init__ serves the module at .../hockey-score-cards.js?v=<version>;
    # a missing or padded version would silently defeat the cache bust.
    version = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
    assert version and version == version.strip()


def test_js_is_valid_syntax_when_node_exists():
    node = shutil.which("node")
    if node is None:
        pytest.skip("no node runtime on this host")
    subprocess.run([node, "--check", str(CARDS_JS)], check=True)
