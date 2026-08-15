"""End-to-end test: drives a real game over HTTP against a live server.

Starts the server on an ephemeral port, plays a full game through the same
JSON API the phones use, and checks that the shared screen never sees a secret.

Run with: python3 -m unittest discover -s tests -t .
"""

import json
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class LiveServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        cls.proc = subprocess.Popen(
            [sys.executable, "server.py", "--port", str(cls.port),
             "--host", "127.0.0.1", "--night", "3", "--day", "3", "--vote", "3"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(80):
            try:
                cls.get("/api/state")
                return
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.05)
        raise RuntimeError("server did not come up")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=5)

    # ------------------------------------------------------------- helpers

    @classmethod
    def get(cls, path):
        with urllib.request.urlopen(cls.base + path, timeout=5) as res:
            return json.loads(res.read())

    @classmethod
    def post(cls, path, payload):
        req = urllib.request.Request(
            cls.base + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def state(self, token):
        return self.get(f"/api/state?token={token}")

    def act(self, token, kind, **extra):
        return self.post("/api/act", {"token": token, "type": kind, **extra})

    # --------------------------------------------------------------- tests

    def test_plays_a_whole_game(self):
        names = ["Ana", "Ben", "Cy", "Dot", "Eli"]
        tokens = {}
        for name in names:
            status, body = self.post("/api/join", {"name": name})
            self.assertEqual(status, 200, body)
            tokens[name] = body["token"]

        host = tokens["Ana"]
        self.assertTrue(self.state(host)["is_host"])

        # A non-host cannot start the game.
        status, body = self.act(tokens["Ben"], "start")
        self.assertEqual(status, 409)
        self.assertIn("host", body["error"])

        status, _ = self.act(host, "start")
        self.assertEqual(status, 200)

        # Map out who got what, using each player's own private view only.
        roles = {n: self.state(t)["private"]["role"] for n, t in tokens.items()}
        self.assertEqual(sorted(roles.values()),
                         ["detective", "doctor", "mafia", "villager", "villager"])

        # The shared screen (no token) must not see a single living role.
        table = self.get("/api/state")
        self.assertIsNone(table["you"])
        self.assertEqual(table["private"], {})
        for entry in table["public"]["players"]:
            self.assertIsNone(entry["role"])

        # One player cannot read another's private state.
        ben_view = self.state(tokens["Ben"])
        self.assertEqual(ben_view["private"]["name"], "Ben")

        # Play until somebody wins, driving whatever phase we land in.
        deadline = time.time() + 60
        while time.time() < deadline:
            snap = self.state(host)
            phase = snap["public"]["phase"]

            if phase == "over":
                break
            if phase == "night":
                self._play_night(tokens, roles)
            elif phase == "day":
                for name, token in tokens.items():
                    if self.state(token)["private"].get("alive"):
                        self.act(token, "ready", ready=True)
            elif phase == "vote":
                self._play_vote(tokens, roles)
            time.sleep(0.05)

        final = self.state(host)
        self.assertEqual(final["public"]["phase"], "over", final["public"]["log"])
        self.assertIn(final["public"]["winner"], ("town", "mafia"))
        # Everything is revealed once it is over.
        for entry in final["public"]["players"]:
            self.assertIsNotNone(entry["role"])

    def _play_night(self, tokens, roles):
        for name, token in tokens.items():
            private = self.state(token)["private"]
            if not private.get("alive") or not private.get("action"):
                continue
            targets = private.get("targets") or []
            if not targets:
                continue
            self.act(token, "night", target=targets[0]["id"])

    def _play_vote(self, tokens, roles):
        # The town always lynches a mafia, so the game terminates quickly.
        mafia_names = [n for n, r in roles.items() if r == "mafia"]
        for name, token in tokens.items():
            snap = self.state(token)
            if snap["public"]["phase"] != "vote":
                return
            if not snap["private"].get("alive"):
                continue
            target = next((p["id"] for p in snap["public"]["players"]
                           if p["alive"] and p["name"] in mafia_names), None)
            self.act(token, "vote", target=target)

    def test_rejects_a_bad_token(self):
        status, body = self.act("not-a-real-token", "start")
        self.assertEqual(status, 409)
        self.assertIn("not in this game", body["error"])

    def test_rejects_malformed_json(self):
        req = urllib.request.Request(
            self.base + "/api/act", data=b"{{{not json",
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=5)
            self.fail("expected a 400")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 400)

    def test_serves_the_two_screens(self):
        for path in ("/", "/table", "/static/app.js", "/static/style.css"):
            with urllib.request.urlopen(self.base + path, timeout=5) as res:
                self.assertEqual(res.status, 200)
                self.assertTrue(len(res.read()) > 0, path)

    def test_static_path_cannot_escape_the_directory(self):
        try:
            with urllib.request.urlopen(
                    self.base + "/static/../server.py", timeout=5) as res:
                body = res.read()
            self.assertNotIn(b"import argparse", body)
        except urllib.error.HTTPError as exc:
            self.assertIn(exc.code, (400, 404))


if __name__ == "__main__":
    unittest.main()
