"""Role definitions and how many of each a game of N players gets."""

MAFIA = "mafia"
DETECTIVE = "detective"
DOCTOR = "doctor"
VILLAGER = "villager"

MIN_PLAYERS = 4
MAX_PLAYERS = 20

ROLE_BLURBS = {
    MAFIA: "Each night you and your partners choose someone to kill. By day, blend in.",
    DETECTIVE: "Each night you may investigate one player and learn whether they are mafia.",
    DOCTOR: "Each night you may protect one player from being killed. Never the same "
            "player two nights in a row.",
    VILLAGER: "You have no night action. Your weapon is the vote.",
}


def mafia_count(num_players):
    """One mafia per three players, always at least one.

    4-5 players -> 1, 6-8 -> 2, 9-11 -> 3, and so on.
    """
    return max(1, num_players // 3)


def role_counts(num_players):
    """Return {role: count} for a game of `num_players`."""
    if num_players < MIN_PLAYERS:
        raise ValueError(f"need at least {MIN_PLAYERS} players, got {num_players}")
    if num_players > MAX_PLAYERS:
        raise ValueError(f"at most {MAX_PLAYERS} players, got {num_players}")

    mafia = mafia_count(num_players)
    villagers = num_players - mafia - 2  # detective + doctor
    counts = {MAFIA: mafia, DETECTIVE: 1, DOCTOR: 1}
    if villagers > 0:
        counts[VILLAGER] = villagers
    return counts


def build_role_deck(num_players):
    """Flat list of roles, one per player, in a fixed (unshuffled) order."""
    deck = []
    for role, count in role_counts(num_players).items():
        deck.extend([role] * count)
    return deck
