"""Shared test helpers: pure-module loader, fixture/scenario loaders, replayer.

The genuine package __init__ imports Home Assistant, which does not exist on
the test host — so here the pure modules (flatten/continuity/polling) are
imported as the "hockey_score" package WITHOUT executing __init__.py: a
stand-in parent package whose __path__ points at the real directory.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = REPO_ROOT / "custom_components" / "hockey_score"

if "hockey_score" not in sys.modules:
    _pkg = types.ModuleType("hockey_score")
    _pkg.__path__ = [str(PKG_DIR)]
    sys.modules["hockey_score"] = _pkg

from hockey_score import continuity, flatten, polling  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
SCENARIOS = Path(__file__).parent / "scenarios"


def load_fixture(name: str) -> dict:
    """Load a frozen /team (or /team/static) JSON snapshot."""
    return json.loads((FIXTURES / f"{name}.json").read_text())


def load_scenario(name: str) -> dict:
    """Load a director scenario (ordered /team steps + static step list)."""
    return json.loads((SCENARIOS / f"{name}.json").read_text())


def types_of(events) -> list:
    return [event_type for event_type, _payload in events]


def replay(steps, failures=()) -> list:
    """Push a fixture sequence through the continuity engine, collect events.

    ``steps`` items are fixture names or raw dict payloads (dicts are used
    as-is — handy for score mutations). ``failures`` is the 1-based index of
    steps whose poll FAILED; a failed step feeds no data and breaks the
    consecutive-pair chain, exactly like a real outage.
    """
    state = continuity.initial_state()
    collected = []
    for index, step in enumerate(steps, start=1):
        if index in failures:
            state = continuity.on_poll_failure(state)
            continue
        data = load_fixture(step) if isinstance(step, str) else step
        events, state = continuity.on_poll_success(state, data)
        collected.extend(events)
    return collected
