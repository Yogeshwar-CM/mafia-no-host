"""Engine tests. Run with: python3 -m unittest discover -s tests -t ."""

import random
import unittest

from mafia.game import (
    PHASE_DAY,
    PHASE_LOBBY,
    PHASE_NIGHT,
    PHASE_OVER,
    PHASE_VOTE,
    WIN_MAFIA,
    WIN_TOWN,
    Game,
    RuleError,
)
from mafia.roles import DETECTIVE, DOCTOR, MAFIA, VILLAGER, mafia_count, role_counts


class RoleDistribution(unittest.TestCase):
    def test_mafia_scale_with_table_size(self):
        self.assertEqual(mafia_count(4), 1)
        self.assertEqual(mafia_count(5), 1)
        self.assertEqual(mafia_count(6), 2)
        self.assertEqual(mafia_count(7), 2)
        self.assertEqual(mafia_count(9), 3)
        self.assertEqual(mafia_count(12), 4)

    def test_every_table_has_one_detective_and_one_doctor(self):
        for n in range(4, 21):
            counts = role_counts(n)
            self.assertEqual(counts[DETECTIVE], 1)
            self.assertEqual(counts[DOCTOR], 1)
            self.assertEqual(sum(counts.values()), n)

    def test_four_players_is_the_floor(self):
        with self.assertRaises(ValueError):
            role_counts(3)

    def test_mafia_never_reach_parity_at_deal_time(self):
        for n in range(4, 21):
            counts = role_counts(n)
            self.assertLess(counts[MAFIA], n - counts[MAFIA])


def make_game(names, seed=0, durations=None):
    game = Game(rng=random.Random(seed), durations=durations)
    ids = {name: game.add_player(name) for name in names}
    return game, ids


def rigged_game(roles, durations=None):
    """Build a started game with roles assigned exactly as given.

    Bypasses the shuffle so tests can state the scenario instead of hunting
    for a seed that produces it.
    """
    game, ids = make_game(list(roles), durations=durations)
    game.start(now=0.0)
    for name, role in roles.items():
        game.players[ids[name]].role = role
    return game, ids


def pass_the_day(game):
    """Advance from day through a vote that eliminates nobody."""
    for player in [p for p in game.players.values() if p.alive]:
        if game.phase == PHASE_DAY:
            game.set_ready(player.id)
    for player in [p for p in game.players.values() if p.alive]:
        if game.phase == PHASE_VOTE:
            game.cast_vote(player.id, None)


class Lobby(unittest.TestCase):
    def test_needs_four_to_start(self):
        game, _ = make_game(["a", "b", "c"])
        with self.assertRaises(RuleError):
            game.start()
        self.assertEqual(game.phase, PHASE_LOBBY)

    def test_duplicate_names_rejected(self):
        game, _ = make_game(["Ana"])
        with self.assertRaises(RuleError):
            game.add_player("ana")

    def test_start_deals_every_role(self):
        game, _ = make_game(["a", "b", "c", "d", "e", "f"])
        game.start()
        roles = sorted(p.role for p in game.players.values())
        self.assertEqual(roles, sorted([MAFIA, MAFIA, DETECTIVE, DOCTOR,
                                        VILLAGER, VILLAGER]))
        self.assertEqual(game.phase, PHASE_NIGHT)
        self.assertEqual(game.round, 1)

    def test_no_joining_mid_game(self):
        game, _ = make_game(["a", "b", "c", "d"])
        game.start()
        with self.assertRaises(RuleError):
            game.add_player("latecomer")


class Night(unittest.TestCase):
    def setUp(self):
        self.game, self.ids = rigged_game({
            "Mo": MAFIA, "Dee": DETECTIVE, "Doc": DOCTOR,
            "Vic": VILLAGER, "Wes": VILLAGER,
        })

    def test_mafia_kill_resolves_at_dawn(self):
        g, ids = self.game, self.ids
        g.night_action(ids["Mo"], ids["Vic"])
        g.night_action(ids["Dee"], ids["Wes"])
        g.night_action(ids["Doc"], ids["Doc"])
        self.assertFalse(g.players[ids["Vic"]].alive)
        self.assertEqual(g.phase, PHASE_DAY)

    def test_doctor_save_cancels_the_kill(self):
        g, ids = self.game, self.ids
        g.night_action(ids["Mo"], ids["Vic"])
        g.night_action(ids["Doc"], ids["Vic"])
        g.night_action(ids["Dee"], ids["Wes"])
        self.assertTrue(g.players[ids["Vic"]].alive)

    def test_save_is_not_announced(self):
        g, ids = self.game, self.ids
        g.night_action(ids["Mo"], ids["Vic"])
        g.night_action(ids["Doc"], ids["Vic"])
        g.night_action(ids["Dee"], ids["Wes"])
        narration = " ".join(entry["text"] for entry in g.log)
        self.assertIn("No one died", narration)
        self.assertNotIn("Vic", narration)

    def test_doctor_cannot_repeat_a_target(self):
        g, ids = self.game, self.ids
        g.night_action(ids["Mo"], ids["Vic"])
        g.night_action(ids["Doc"], ids["Wes"])
        g.night_action(ids["Dee"], ids["Wes"])
        # Survive the day so night 2 starts.
        for name in ["Mo", "Dee", "Doc", "Wes"]:
            if g.players[ids[name]].alive:
                g.set_ready(ids[name])
        for name in ["Mo", "Dee", "Doc", "Wes"]:
            if g.players[ids[name]].alive:
                g.cast_vote(ids[name], None)
        self.assertEqual(g.phase, PHASE_NIGHT)
        with self.assertRaises(RuleError):
            g.night_action(ids["Doc"], ids["Wes"])
        g.night_action(ids["Doc"], ids["Doc"])  # someone else is fine

    def test_doctor_may_repeat_after_skipping_a_night(self):
        g, ids = self.game, self.ids
        g.night_action(ids["Doc"], ids["Wes"])   # night 1: protect Wes
        g.night_action(ids["Mo"], ids["Vic"])
        g.night_action(ids["Dee"], ids["Vic"])
        pass_the_day(g)

        g.night_action(ids["Doc"], None)         # night 2: skip
        g.night_action(ids["Mo"], ids["Wes"])
        g.night_action(ids["Dee"], ids["Wes"])
        self.assertFalse(g.players[ids["Wes"]].alive)
        pass_the_day(g)

        # The chain is broken, so Wes-again would have been legal.
        self.assertIsNone(g.doctor_last_target)

    def test_mafia_cannot_target_mafia(self):
        g, ids = rigged_game({
            "Mo": MAFIA, "Sal": MAFIA, "Dee": DETECTIVE,
            "Doc": DOCTOR, "Vic": VILLAGER, "Wes": VILLAGER,
        })
        with self.assertRaises(RuleError):
            g.night_action(ids["Mo"], ids["Sal"])

    def test_detective_learns_the_truth(self):
        g, ids = self.game, self.ids
        g.night_action(ids["Dee"], ids["Mo"])
        g.night_action(ids["Mo"], ids["Vic"])
        g.night_action(ids["Doc"], ids["Doc"])
        notes = g.players[ids["Dee"]].investigations
        self.assertEqual(notes, [{"name": "Mo", "is_mafia": True, "night": 1}])

    def test_detective_result_is_private(self):
        g, ids = self.game, self.ids
        g.night_action(ids["Dee"], ids["Mo"])
        g.night_action(ids["Mo"], ids["Vic"])
        g.night_action(ids["Doc"], ids["Doc"])
        self.assertNotIn("investigations", g.public_state())
        self.assertNotIn("investigations", g.private_state(ids["Vic"]))
        self.assertIn("investigations", g.private_state(ids["Dee"]))

    def test_villager_has_no_night_action(self):
        with self.assertRaises(RuleError):
            self.game.night_action(self.ids["Vic"], self.ids["Mo"])

    def test_timeout_with_no_mafia_vote_kills_nobody(self):
        g, ids = self.game, self.ids
        g.tick(now=10_000)
        self.assertEqual(g.phase, PHASE_DAY)
        self.assertEqual(len([p for p in g.players.values() if p.alive]), 5)

    def test_tied_mafia_votes_pick_one_target(self):
        g, ids = rigged_game({
            "Mo": MAFIA, "Sal": MAFIA, "Dee": DETECTIVE,
            "Doc": DOCTOR, "Vic": VILLAGER, "Wes": VILLAGER,
        })
        g.night_action(ids["Mo"], ids["Vic"])
        g.night_action(ids["Sal"], ids["Wes"])
        g.night_action(ids["Dee"], ids["Mo"])
        g.night_action(ids["Doc"], ids["Doc"])
        dead = [p for p in g.players.values() if not p.alive]
        self.assertEqual(len(dead), 1)
        self.assertIn(dead[0].name, {"Vic", "Wes"})


class Voting(unittest.TestCase):
    def setUp(self):
        self.game, self.ids = rigged_game({
            "Mo": MAFIA, "Dee": DETECTIVE, "Doc": DOCTOR,
            "Vic": VILLAGER, "Wes": VILLAGER,
        })
        g, ids = self.game, self.ids
        g.night_action(ids["Mo"], ids["Wes"])
        g.night_action(ids["Dee"], ids["Vic"])
        g.night_action(ids["Doc"], ids["Doc"])
        self.alive = [n for n in ["Mo", "Dee", "Doc", "Vic"]
                      if g.players[ids[n]].alive]

    def test_day_opens_after_the_night(self):
        self.assertEqual(self.game.phase, PHASE_DAY)

    def test_everyone_ready_opens_the_vote(self):
        for name in self.alive:
            self.game.set_ready(self.ids[name])
        self.assertEqual(self.game.phase, PHASE_VOTE)

    def test_plurality_eliminates(self):
        g, ids = self.game, self.ids
        for name in self.alive:
            g.set_ready(ids[name])
        for name in self.alive:
            g.cast_vote(ids[name], ids["Mo"])
        self.assertFalse(g.players[ids["Mo"]].alive)

    def test_tie_eliminates_nobody(self):
        g, ids = self.game, self.ids
        for name in self.alive:
            g.set_ready(ids[name])
        g.cast_vote(ids["Mo"], ids["Dee"])
        g.cast_vote(ids["Dee"], ids["Mo"])
        g.cast_vote(ids["Doc"], ids["Vic"])
        g.cast_vote(ids["Vic"], ids["Doc"])
        self.assertEqual(len([p for p in g.players.values() if p.alive]), 4)
        self.assertIn("could not agree",
                      " ".join(e["text"] for e in g.log))

    def test_ballot_hides_who_voted_for_whom(self):
        g, ids = self.game, self.ids
        for name in self.alive:
            g.set_ready(ids[name])
        g.cast_vote(ids["Mo"], ids["Dee"])
        state = g.public_state()
        self.assertEqual(state["voted"], [ids["Mo"]])
        self.assertNotIn("votes", state)

    def test_dead_players_cannot_vote(self):
        g, ids = self.game, self.ids
        for name in self.alive:
            g.set_ready(ids[name])
        with self.assertRaises(RuleError):
            g.cast_vote(ids["Wes"], ids["Mo"])


class WinConditions(unittest.TestCase):
    def test_town_wins_when_last_mafia_is_voted_out(self):
        g, ids = rigged_game({
            "Mo": MAFIA, "Dee": DETECTIVE, "Doc": DOCTOR, "Vic": VILLAGER,
        })
        g.night_action(ids["Mo"], ids["Vic"])
        g.night_action(ids["Dee"], ids["Mo"])
        g.night_action(ids["Doc"], ids["Doc"])
        for name in ["Mo", "Dee", "Doc"]:
            g.set_ready(ids[name])
        for name in ["Mo", "Dee", "Doc"]:
            g.cast_vote(ids[name], ids["Mo"])
        self.assertEqual(g.phase, PHASE_OVER)
        self.assertEqual(g.winner, WIN_TOWN)

    def test_mafia_win_at_parity(self):
        g, ids = rigged_game({
            "Mo": MAFIA, "Dee": DETECTIVE, "Doc": DOCTOR, "Vic": VILLAGER,
        })
        g.night_action(ids["Mo"], ids["Vic"])
        g.night_action(ids["Dee"], ids["Doc"])
        g.night_action(ids["Doc"], ids["Doc"])
        self.assertFalse(g.players[ids["Vic"]].alive)
        pass_the_day(g)  # 3 left: Mo, Dee, Doc

        g.night_action(ids["Mo"], ids["Dee"])
        g.night_action(ids["Dee"], ids["Mo"])
        g.night_action(ids["Doc"], ids["Mo"])  # cannot repeat Doc; guesses wrong
        self.assertFalse(g.players[ids["Dee"]].alive)
        self.assertEqual(g.phase, PHASE_OVER)
        self.assertEqual(g.winner, WIN_MAFIA)

    def test_doctor_can_stall_a_mafia_win(self):
        g, ids = rigged_game({
            "Mo": MAFIA, "Dee": DETECTIVE, "Doc": DOCTOR, "Vic": VILLAGER,
        })
        g.night_action(ids["Mo"], ids["Vic"])
        g.night_action(ids["Dee"], ids["Doc"])
        g.night_action(ids["Doc"], ids["Doc"])
        pass_the_day(g)

        g.night_action(ids["Mo"], ids["Dee"])
        g.night_action(ids["Dee"], ids["Mo"])
        g.night_action(ids["Doc"], ids["Dee"])  # correct guess
        self.assertTrue(g.players[ids["Dee"]].alive)
        self.assertEqual(g.phase, PHASE_DAY)
        self.assertIsNone(g.winner)

    def test_game_over_reveals_every_role(self):
        g, ids = rigged_game({
            "Mo": MAFIA, "Dee": DETECTIVE, "Doc": DOCTOR, "Vic": VILLAGER,
        })
        g.night_action(ids["Mo"], ids["Vic"])
        g.night_action(ids["Dee"], ids["Mo"])
        g.night_action(ids["Doc"], ids["Doc"])
        for name in ["Mo", "Dee", "Doc"]:
            g.set_ready(ids[name])
        for name in ["Mo", "Dee", "Doc"]:
            g.cast_vote(ids[name], ids["Mo"])
        for entry in g.public_state()["players"]:
            self.assertIsNotNone(entry["role"])


class Secrecy(unittest.TestCase):
    def test_public_state_hides_living_roles(self):
        g, _ = make_game(["a", "b", "c", "d", "e"])
        g.start()
        for entry in g.public_state()["players"]:
            self.assertIsNone(entry["role"])

    def test_public_state_never_leaks_night_choices(self):
        g, ids = rigged_game({
            "Mo": MAFIA, "Dee": DETECTIVE, "Doc": DOCTOR,
            "Vic": VILLAGER, "Wes": VILLAGER,
        })
        g.night_action(ids["Mo"], ids["Vic"])
        state = g.public_state()
        blob = repr(state)
        self.assertNotIn("mafia_votes", blob)
        self.assertNotIn("protect", blob)

    def test_mafia_see_each_other_and_nobody_else_does(self):
        g, ids = rigged_game({
            "Mo": MAFIA, "Sal": MAFIA, "Dee": DETECTIVE,
            "Doc": DOCTOR, "Vic": VILLAGER, "Wes": VILLAGER,
        })
        partners = g.private_state(ids["Mo"])["partners"]
        self.assertEqual([p["name"] for p in partners], ["Sal"])
        self.assertNotIn("partners", g.private_state(ids["Vic"]))

    def test_unknown_player_gets_nothing(self):
        g, _ = make_game(["a", "b", "c", "d"])
        g.start()
        self.assertEqual(g.private_state(9999), {})


class FullGame(unittest.TestCase):
    def test_a_game_always_terminates(self):
        """Random play from many seeds must always reach a winner."""
        for seed in range(60):
            rng = random.Random(seed)
            n = rng.randint(4, 12)
            game, ids = make_game([f"p{i}" for i in range(n)], seed=seed)
            game.start(now=0.0)

            for _ in range(500):
                if game.phase == PHASE_OVER:
                    break
                if game.phase == PHASE_NIGHT:
                    for p in list(game.players.values()):
                        if not p.alive:
                            continue
                        targets = game._legal_targets(p)
                        if not targets:
                            continue
                        try:
                            game.night_action(p.id, rng.choice(targets)["id"])
                        except RuleError:
                            pass
                    game.tick(now=10 ** 9)
                elif game.phase == PHASE_DAY:
                    for p in list(game.players.values()):
                        if p.alive and game.phase == PHASE_DAY:
                            game.set_ready(p.id)
                elif game.phase == PHASE_VOTE:
                    for p in list(game.players.values()):
                        if p.alive and game.phase == PHASE_VOTE:
                            alive = [q.id for q in game.players.values() if q.alive]
                            game.cast_vote(p.id, rng.choice(alive))

            self.assertEqual(game.phase, PHASE_OVER, f"seed {seed} never ended")
            self.assertIn(game.winner, (WIN_TOWN, WIN_MAFIA))


if __name__ == "__main__":
    unittest.main()
