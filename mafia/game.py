"""The Mafia rules engine.

Pure state machine: no sockets, no threads, no clock of its own. Time enters
through `now` arguments so tests can drive it. The server layer wraps this.
"""

import random

from .roles import (
    DETECTIVE,
    DOCTOR,
    MAFIA,
    MIN_PLAYERS,
    VILLAGER,
    build_role_deck,
)

PHASE_LOBBY = "lobby"
PHASE_NIGHT = "night"
PHASE_DAY = "day"
PHASE_VOTE = "vote"
PHASE_OVER = "over"

WIN_TOWN = "town"
WIN_MAFIA = "mafia"

DEFAULT_DURATIONS = {
    PHASE_NIGHT: 90,
    PHASE_DAY: 180,
    PHASE_VOTE: 60,
}

# Night action kinds.
KILL = "kill"
INVESTIGATE = "investigate"
PROTECT = "protect"

ROLE_ACTION = {MAFIA: KILL, DETECTIVE: INVESTIGATE, DOCTOR: PROTECT}


class RuleError(Exception):
    """A player tried something the rules do not allow."""


class Player:
    def __init__(self, pid, name):
        self.id = pid
        self.name = name
        self.role = None
        self.alive = True
        self.connected = True
        # Detective's private notebook: [{"name": str, "is_mafia": bool, "night": int}]
        self.investigations = []
        self.death = None  # {"night": int, "cause": "killed"|"voted"}

    def public_view(self, reveal_role):
        return {
            "id": self.id,
            "name": self.name,
            "alive": self.alive,
            "connected": self.connected,
            "role": self.role if (reveal_role and not self.alive) else None,
        }


class Game:
    def __init__(self, rng=None, durations=None):
        self.rng = rng or random.Random()
        self.durations = dict(DEFAULT_DURATIONS)
        if durations:
            self.durations.update(durations)

        self.players = {}
        self._next_id = 1
        self.phase = PHASE_LOBBY
        self.round = 0  # increments each night; night 1 is the first night
        self.log = []  # public narration, oldest first
        self.winner = None
        self.deadline = None  # epoch seconds, or None for "no clock"

        # Per-night scratch space.
        self.mafia_votes = {}       # mafia player id -> target id
        self.protect_target = None  # doctor's choice this night
        self.investigate_target = None
        # "Submitted" is tracked apart from the target because None is a legal
        # choice (skipping) for the doctor and detective, and the night should
        # still end early once everyone has decided.
        self.protect_submitted = False
        self.investigate_submitted = False
        self.doctor_last_target = None  # enforces the no-repeat rule

        # Per-day scratch space.
        self.ready = set()   # players who pressed "ready to vote"
        self.votes = {}      # voter id -> target id, or None for abstain

    # ---------------------------------------------------------------- lobby

    def add_player(self, name):
        if self.phase != PHASE_LOBBY:
            raise RuleError("the game has already started")
        name = " ".join(name.split())[:20]
        if not name:
            raise RuleError("name cannot be empty")
        if any(p.name.lower() == name.lower() for p in self.players.values()):
            raise RuleError(f"someone is already called {name}")
        if len(self.players) >= 20:
            raise RuleError("the table is full")

        pid = self._next_id
        self._next_id += 1
        self.players[pid] = Player(pid, name)
        return pid

    def remove_player(self, pid):
        if self.phase != PHASE_LOBBY:
            raise RuleError("cannot leave once the game has started")
        self.players.pop(pid, None)

    def start(self, now=0.0):
        if self.phase != PHASE_LOBBY:
            raise RuleError("the game has already started")
        if len(self.players) < MIN_PLAYERS:
            raise RuleError(f"need at least {MIN_PLAYERS} players to start")

        deck = build_role_deck(len(self.players))
        self.rng.shuffle(deck)
        for player, role in zip(self.players.values(), deck):
            player.role = role

        self._say("The game begins. Everyone check your role, then close your eyes.")
        self._begin_night(now)
        return self

    # ---------------------------------------------------------------- night

    def _begin_night(self, now):
        self.round += 1
        self.phase = PHASE_NIGHT
        self.mafia_votes = {}
        self.protect_target = None
        self.investigate_target = None
        self.protect_submitted = False
        self.investigate_submitted = False
        self.deadline = now + self.durations[PHASE_NIGHT]
        self._say(f"Night {self.round} falls.")

    def night_action(self, pid, target_id, now=0.0):
        """Submit (or change) this player's night action.

        Passing target_id=None means "skip" — allowed for the doctor and the
        detective, never for the mafia.
        """
        if self.phase != PHASE_NIGHT:
            raise RuleError("it is not night")
        actor = self._living_player(pid)
        action = ROLE_ACTION.get(actor.role)
        if action is None:
            raise RuleError("you have no night action")

        if target_id is not None:
            target = self._living_player(target_id)
            if action == KILL and target.role == MAFIA:
                raise RuleError("the mafia do not kill their own")
            if action == INVESTIGATE and target.id == actor.id:
                raise RuleError("you already know what you are")
            if action == PROTECT and target.id == self.doctor_last_target:
                raise RuleError(
                    f"you protected {target.name} last night — pick someone else"
                )

        if action == KILL:
            if target_id is None:
                raise RuleError("the mafia must choose a target")
            self.mafia_votes[actor.id] = target_id
        elif action == PROTECT:
            self.protect_target = target_id
            self.protect_submitted = True
        else:
            self.investigate_target = target_id
            self.investigate_submitted = True

        if self._night_complete():
            self._resolve_night(now)

    def _night_complete(self):
        for player in self._alive():
            if player.role == MAFIA and player.id not in self.mafia_votes:
                return False
            if player.role == DOCTOR and not self.protect_submitted:
                return False
            if player.role == DETECTIVE and not self.investigate_submitted:
                return False
        return True

    def _resolve_night(self, now):
        victim_id = self._tally_mafia_votes()

        if self.investigate_target is not None:
            detective = self._role_holder(DETECTIVE)
            target = self.players[self.investigate_target]
            if detective:
                detective.investigations.append({
                    "name": target.name,
                    "is_mafia": target.role == MAFIA,
                    "night": self.round,
                })

        self.doctor_last_target = self.protect_target

        self.phase = PHASE_DAY
        if victim_id is None:
            self._say("The mafia could not agree. Everyone survived the night.")
        elif victim_id == self.protect_target:
            # Deliberately vague: naming the saved player would hand the town
            # a confirmed-innocent every night the doctor guesses right.
            self._say("No one died last night.")
        else:
            victim = self.players[victim_id]
            victim.alive = False
            victim.death = {"night": self.round, "cause": "killed"}
            self._say(f"{victim.name} was killed in the night. They were the "
                      f"{victim.role}.")

        if self._check_win():
            return
        self._begin_day(now)

    def _tally_mafia_votes(self):
        if not self.mafia_votes:
            return None
        counts = {}
        for target_id in self.mafia_votes.values():
            counts[target_id] = counts.get(target_id, 0) + 1
        best = max(counts.values())
        tied = sorted(t for t, c in counts.items() if c == best)
        return self.rng.choice(tied)

    # ------------------------------------------------------------------ day

    def _begin_day(self, now):
        self.phase = PHASE_DAY
        self.ready = set()
        self.votes = {}
        self.deadline = now + self.durations[PHASE_DAY]
        self._say("Discuss. When everyone is ready, the vote begins.")

    def set_ready(self, pid, ready=True, now=0.0):
        if self.phase != PHASE_DAY:
            raise RuleError("there is nothing to be ready for")
        self._living_player(pid)
        if ready:
            self.ready.add(pid)
        else:
            self.ready.discard(pid)
        if self.ready >= {p.id for p in self._alive()}:
            self._begin_vote(now)

    # ----------------------------------------------------------------- vote

    def _begin_vote(self, now):
        self.phase = PHASE_VOTE
        self.votes = {}
        self.deadline = now + self.durations[PHASE_VOTE]
        self._say("The vote is open.")

    def cast_vote(self, pid, target_id, now=0.0):
        """target_id=None abstains."""
        if self.phase != PHASE_VOTE:
            raise RuleError("the vote is not open")
        voter = self._living_player(pid)
        if target_id is not None:
            self._living_player(target_id)
        self.votes[voter.id] = target_id

        if len(self.votes) >= len(self._alive()):
            self._resolve_vote(now)

    def _resolve_vote(self, now):
        counts = {}
        for target_id in self.votes.values():
            if target_id is not None:
                counts[target_id] = counts.get(target_id, 0) + 1

        eliminated = None
        if counts:
            best = max(counts.values())
            tied = [t for t, c in counts.items() if c == best]
            if len(tied) == 1:
                eliminated = tied[0]

        if eliminated is None:
            self._say("The town could not agree. No one was eliminated.")
        else:
            player = self.players[eliminated]
            player.alive = False
            player.death = {"night": self.round, "cause": "voted"}
            self._say(f"{player.name} was voted out. They were the {player.role}.")

        if self._check_win():
            return
        self._begin_night(now)

    # ---------------------------------------------------------------- clock

    def tick(self, now):
        """Called by the server on a timer. Resolves the phase if time is up."""
        if self.deadline is None or now < self.deadline:
            return False
        if self.phase == PHASE_NIGHT:
            self._resolve_night(now)
        elif self.phase == PHASE_DAY:
            self._begin_vote(now)
        elif self.phase == PHASE_VOTE:
            self._resolve_vote(now)
        else:
            return False
        return True

    # ------------------------------------------------------------ win check

    def _check_win(self):
        mafia = [p for p in self._alive() if p.role == MAFIA]
        town = [p for p in self._alive() if p.role != MAFIA]
        if not mafia:
            self._finish(WIN_TOWN, "Every mafia is gone. The town wins.")
        elif len(mafia) >= len(town):
            self._finish(WIN_MAFIA, "The mafia equal the town and take over. "
                                    "The mafia win.")
        else:
            return False
        return True

    def _finish(self, winner, message):
        self.winner = winner
        self.phase = PHASE_OVER
        self.deadline = None
        self._say(message)

    # -------------------------------------------------------------- helpers

    def _alive(self):
        return [p for p in self.players.values() if p.alive]

    def _living_player(self, pid):
        player = self.players.get(pid)
        if player is None:
            raise RuleError("no such player")
        if not player.alive:
            raise RuleError("the dead do not act")
        return player

    def _role_holder(self, role):
        for player in self.players.values():
            if player.role == role and player.alive:
                return player
        return None

    def _say(self, text):
        self.log.append({"round": self.round, "phase": self.phase, "text": text})

    # --------------------------------------------------------------- views

    def public_state(self):
        """What the shared screen — and anyone — is allowed to know."""
        over = self.phase == PHASE_OVER
        alive = self._alive()
        state = {
            "phase": self.phase,
            "round": self.round,
            "deadline": self.deadline,
            "winner": self.winner,
            "log": self.log,
            "players": [p.public_view(reveal_role=True) for p in self.players.values()],
            "alive_count": len(alive),
            "min_players": MIN_PLAYERS,
        }
        if over:
            state["players"] = [
                {**p.public_view(reveal_role=True), "role": p.role}
                for p in self.players.values()
            ]
        if self.phase == PHASE_VOTE:
            # Open ballot: who has voted, but not yet for whom.
            state["voted"] = sorted(self.votes.keys())
        if self.phase == PHASE_DAY:
            state["ready"] = sorted(self.ready)
        return state

    def private_state(self, pid):
        """The extra slice of truth that belongs to exactly one player."""
        player = self.players.get(pid)
        if player is None:
            return {}
        private = {
            "id": player.id,
            "name": player.name,
            "role": player.role,
            "alive": player.alive,
        }
        if player.role == MAFIA:
            private["partners"] = [
                {"id": p.id, "name": p.name, "alive": p.alive}
                for p in self.players.values()
                if p.role == MAFIA and p.id != player.id
            ]
        if player.role == DETECTIVE:
            private["investigations"] = player.investigations
        if player.role == DOCTOR:
            private["last_protected"] = self.doctor_last_target

        if self.phase == PHASE_NIGHT and player.alive:
            private["action"] = ROLE_ACTION.get(player.role)
            private["targets"] = self._legal_targets(player)
            if player.role == MAFIA:
                private["submitted"] = self.mafia_votes.get(player.id)
                private["partner_votes"] = [
                    {"voter": self.players[v].name,
                     "target": self.players[t].name}
                    for v, t in self.mafia_votes.items()
                ]
            elif player.role == DOCTOR:
                private["submitted"] = self.protect_target
                private["has_submitted"] = self.protect_submitted
            elif player.role == DETECTIVE:
                private["submitted"] = self.investigate_target
                private["has_submitted"] = self.investigate_submitted
        if self.phase == PHASE_VOTE and player.alive:
            private["submitted_vote"] = self.votes.get(player.id, "none")
        return private

    def _legal_targets(self, player):
        action = ROLE_ACTION.get(player.role)
        if action is None:
            return []
        targets = []
        for other in self._alive():
            if action == KILL and other.role == MAFIA:
                continue
            if action == INVESTIGATE and other.id == player.id:
                continue
            if action == PROTECT and other.id == self.doctor_last_target:
                continue
            targets.append({"id": other.id, "name": other.name})
        return targets
