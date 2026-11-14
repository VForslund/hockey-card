#!/usr/bin/env python3
"""The game director: a scripted fake hockey-api for tests and night-sim.

Serves /team and /team/static from a scenario file: an ordered list of
steps per path, one step consumed per request. When a queue runs dry the
last fixture step repeats forever (steady state). Step shapes:

  "fixture_name"     → 200 with tests/fixtures/<name>.json
  {"status": 500}    → that HTTP status with a small JSON error body

Any other scenario keys are ignored (e.g. "expect_events", used by the
night-sim driver).

Every request appends one JSON line to --log: {"ts", "path", "status"}.
Tests read that log to verify the integration's real polling cadence from
the server side — the integration cannot fake its own request rate.

Usage:
  python tests/director.py --port 5959 \\
      --scenario tests/scenarios/full_game.json \\
      --log /tmp/opencode/nightsim/director.jsonl --key test-key
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"

PATH_ALIASES = {
    "team": "/team",
    "static": "/team/static",
    "standings": "/team/standings",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # silence default stderr chatter
        pass

    def _reply(self, status: int, body: bytes, path: str, ts: float) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        server: DirectorServer = self.server
        server.write_log(ts, path, status)

    def do_GET(self):  # noqa: N802 (http.server naming)
        server: DirectorServer = self.server
        ts = time.time()
        path = self.path.split("?", 1)[0]

        if path not in server.queues:
            self._reply(404, b'{"detail": "not found"}', path, ts)
            return

        if server.key is not None:
            expected = f"Bearer {server.key}"
            if self.headers.get("Authorization", "") != expected:
                self._reply(
                    401,
                    b'{"detail": "Invalid credentials"}',
                    path,
                    ts,
                )
                return

        step = server.pop(path)
        if isinstance(step, dict):
            status = int(step.get("status", 500))
            body = json.dumps({"detail": f"scripted HTTP {status}"}).encode()
        else:
            fixture = FIXTURES / f"{step}.json"
            if not fixture.is_file():
                self._reply(404, b'{"detail": "missing fixture"}', path, ts)
                return
            status = 200
            body = fixture.read_bytes()
        self._reply(status, body, path, ts)


class DirectorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, scenario: dict, key: str | None, log_path: str | None):
        super().__init__(addr, Handler)
        self.key = key
        self.lock = threading.Lock()
        self.queues: dict[str, list] = {}
        self.cursors: dict[str, int] = {}
        for name, steps in scenario.items():
            path = PATH_ALIASES.get(name)
            if path is None or not isinstance(steps, list) or not steps:
                continue  # expect_events / cadence / notes are not queues
            self.queues[path] = steps
            self.cursors[path] = 0
        if "/team" not in self.queues:
            raise SystemExit("scenario needs a non-empty 'team' step list")
        self.log_file = open(log_path, "a", encoding="utf-8") if log_path else None

    def pop(self, path: str):
        steps = self.queues[path]
        with self.lock:
            index = self.cursors[path]
            step = steps[index]
            if index < len(steps) - 1:
                self.cursors[path] = index + 1
            return step

    def write_log(self, ts: float, path: str, status: int) -> None:
        if self.log_file is None:
            return
        with self.lock:
            self.log_file.write(
                json.dumps({"ts": round(ts, 3), "path": path, "status": status}) + "\n"
            )
            self.log_file.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5959)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--log", default=None)
    parser.add_argument("--key", default=None)
    args = parser.parse_args()

    scenario = json.loads(Path(args.scenario).read_text())
    server = DirectorServer((args.host, args.port), scenario, args.key, args.log)
    print(
        f"director on {args.host}:{args.port}, scenario={args.scenario}, "
        f"queues={list(server.queues)}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
