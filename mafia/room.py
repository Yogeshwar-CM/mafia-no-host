"""Thread-safe wrapper around a Game: player tokens, and push to subscribers.

The engine knows nothing about players' identities beyond an integer id. This
layer maps secret tokens to those ids, which is what keeps one phone's view
from being another phone's view.
"""

import queue
import secrets
import threading
import time

from .game import PHASE_LOBBY, Game, RuleError


class Subscriber:
    def __init__(self, token):
        self.token = token
        self.queue = queue.Queue(maxsize=32)


class Room:
    def __init__(self, durations=None):
        self.lock = threading.RLock()
        self.durations = durations
        self.game = Game(durations=durations)
        self.tokens = {}        # token -> player id
        self.host_token = None
        self.subscribers = []
        self.version = 0

    # ------------------------------------------------------------- identity

    def join(self, name):
        with self.lock:
            pid = self.game.add_player(name)
            token = secrets.token_urlsafe(16)
            self.tokens[token] = pid
            if self.host_token is None:
                self.host_token = token
            self._bump()
            return token, pid

    def player_id(self, token):
        return self.tokens.get(token)

    def is_host(self, token):
        return token is not None and token == self.host_token

    def leave(self, token):
        with self.lock:
            pid = self.tokens.get(token)
            if pid is None:
                return
            self.game.remove_player(pid)   # raises unless still in the lobby
            self.tokens.pop(token, None)
            if token == self.host_token:
                self.host_token = next(iter(self.tokens), None)
            self._bump()

    # -------------------------------------------------------------- actions

    def act(self, token, kind, payload):
        """Apply one player action. Raises RuleError on anything illegal."""
        with self.lock:
            pid = self.tokens.get(token)
            if pid is None:
                raise RuleError("you are not in this game")
            now = time.time()

            if kind == "start":
                if not self.is_host(token):
                    raise RuleError("only the host can start the game")
                self.game.start(now)
            elif kind == "night":
                self.game.night_action(pid, payload.get("target"), now)
            elif kind == "ready":
                self.game.set_ready(pid, payload.get("ready", True), now)
            elif kind == "vote":
                self.game.cast_vote(pid, payload.get("target"), now)
            elif kind == "reset":
                if not self.is_host(token):
                    raise RuleError("only the host can start a new game")
                self._reset()
            else:
                raise RuleError(f"unknown action: {kind}")

            self._bump()

    def _reset(self):
        """New game, same people, same seats."""
        names = [p.name for p in self.game.players.values()]
        old_ids = {p.name: p.id for p in self.game.players.values()}
        self.game = Game(durations=self.durations)
        remap = {}
        for name in names:
            remap[old_ids[name]] = self.game.add_player(name)
        self.tokens = {t: remap[pid] for t, pid in self.tokens.items()
                       if pid in remap}

    def tick(self):
        with self.lock:
            if self.game.tick(time.time()):
                self._bump()

    # ---------------------------------------------------------------- views

    def snapshot(self, token):
        with self.lock:
            pid = self.tokens.get(token)
            return {
                "version": self.version,
                "public": self.game.public_state(),
                "private": self.game.private_state(pid) if pid else {},
                "you": pid,
                "is_host": self.is_host(token),
                "can_join": self.game.phase == PHASE_LOBBY,
                "server_time": time.time(),
            }

    # ------------------------------------------------------------ broadcast

    def subscribe(self, token):
        sub = Subscriber(token)
        with self.lock:
            self.subscribers.append(sub)
            self._mark_connected(token, True)
        return sub

    def unsubscribe(self, sub):
        with self.lock:
            if sub in self.subscribers:
                self.subscribers.remove(sub)
            still_here = any(s.token == sub.token for s in self.subscribers)
            if not still_here:
                self._mark_connected(sub.token, False)
                self.version += 1
                self._push()

    def _mark_connected(self, token, connected):
        pid = self.tokens.get(token)
        if pid and pid in self.game.players:
            self.game.players[pid].connected = connected

    def _bump(self):
        self.version += 1
        self._push()

    def _push(self):
        for sub in list(self.subscribers):
            try:
                sub.queue.put_nowait(self.snapshot(sub.token))
            except queue.Full:
                # A wedged client is not the game's problem; it will catch up
                # on its next reconnect.
                pass
