#!/usr/bin/env python3
"""Mafia — the computer is the host.

Run it on a laptop, open /table on that laptop's screen for everyone to see,
and have each player open the printed address on their own phone.

    python3 server.py [--port 8000] [--night 90] [--day 180] [--vote 60]

Standard library only: no pip install, no build step.
"""

import argparse
import json
import mimetypes
import os
import queue
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mafia.game import RuleError
from mafia.room import Room

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
HEARTBEAT_SECONDS = 15
TICK_SECONDS = 0.5

ROOM = Room()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Mafia"

    def log_message(self, fmt, *args):
        pass  # the console belongs to the game, not the access log

    # ------------------------------------------------------------------ GET

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self._send_file("index.html")
        if path == "/table":
            return self._send_file("table.html")
        if path == "/api/events":
            return self._stream_events()
        if path == "/api/state":
            return self._send_json(200, ROOM.snapshot(self._token()))
        if path.startswith("/static/"):
            return self._send_file(path[len("/static/"):])
        self._send_json(404, {"error": "not found"})

    # ----------------------------------------------------------------- POST

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            body = self._read_json()
        except ValueError:
            return self._send_json(400, {"error": "malformed request"})

        try:
            if path == "/api/join":
                token, pid = ROOM.join(str(body.get("name", "")))
                return self._send_json(200, {"token": token, "id": pid})
            if path == "/api/act":
                token = body.get("token")
                ROOM.act(token, body.get("type"), body)
                return self._send_json(200, {"ok": True})
            if path == "/api/leave":
                ROOM.leave(body.get("token"))
                return self._send_json(200, {"ok": True})
        except RuleError as exc:
            return self._send_json(409, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - report, never crash the party
            return self._send_json(500, {"error": f"unexpected: {exc}"})

        self._send_json(404, {"error": "not found"})

    # ------------------------------------------------------------------ SSE

    def _stream_events(self):
        token = self._token()
        sub = ROOM.subscribe(token)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self._sse_send(ROOM.snapshot(token))

            while True:
                try:
                    payload = sub.queue.get(timeout=HEARTBEAT_SECONDS)
                    self._sse_send(payload)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass  # phone locked, tab closed, walked out of Wi-Fi range
        finally:
            ROOM.unsubscribe(sub)

    def _sse_send(self, payload):
        data = json.dumps(payload, separators=(",", ":"))
        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
        self.wfile.flush()

    # -------------------------------------------------------------- plumbing

    def _token(self):
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        for part in query.split("&"):
            if part.startswith("token="):
                return part[len("token="):]
        return None

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(str(exc)) from exc
        if not isinstance(parsed, dict):
            raise ValueError("expected a JSON object")
        return parsed

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, relative):
        safe = os.path.normpath(relative).lstrip("./")
        full = os.path.join(STATIC_DIR, safe)
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            return self._send_json(404, {"error": "not found"})
        with open(full, "rb") as handle:
            body = handle.read()
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def ticker():
    """Drives phase deadlines so a distracted player cannot stall the table."""
    while True:
        time.sleep(TICK_SECONDS)
        try:
            ROOM.tick()
        except Exception:  # noqa: BLE001 - a bad tick must not stop the clock
            pass


def lan_address():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))  # no packets sent; just picks a route
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--night", type=int, default=90,
                        help="seconds for the night phase")
    parser.add_argument("--day", type=int, default=180,
                        help="seconds of discussion before the vote")
    parser.add_argument("--vote", type=int, default=60,
                        help="seconds to cast a vote")
    args = parser.parse_args()

    global ROOM
    ROOM = Room(durations={"night": args.night, "day": args.day,
                           "vote": args.vote})

    threading.Thread(target=ticker, daemon=True).start()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True

    address = f"http://{lan_address()}:{args.port}"
    print("\n  Mafia — the computer is the host\n")
    print(f"  Players, on your phones:   {address}")
    print(f"  Shared screen (this one):  {address}/table\n")
    print("  Everyone must be on the same Wi-Fi. Ctrl-C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Game over. Thanks for playing.\n")
        server.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
