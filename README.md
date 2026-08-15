# Mafia — the computer is the host

Play Mafia with no moderator. Everyone at the table gets to play, including the
person who used to be stuck running the game.

Each player's phone is their private screen: it shows their role, takes their
night action, and shows the detective their results. A laptop or TV shows the
shared table screen, which by construction can only ever display public
information.

## Running it

Needs Python 3.8+. Nothing to install — no pip, no npm, no build step.

```bash
python3 server.py
```

It prints two addresses:

```
Players, on your phones:   http://192.168.1.42:8000
Shared screen (this one):  http://192.168.1.42:8000/table
```

Everyone joins the first address on their own phone; put the second one on the
big screen. Everyone must be on the same Wi-Fi.

Phase timers are adjustable:

```bash
python3 server.py --port 8000 --night 90 --day 180 --vote 60
```

## How a game goes

1. **Lobby.** Players type a name and join. The first to join is the host and
   gets the Start button. Four players minimum.
2. **Night.** The mafia agree on a target, the detective investigates someone,
   the doctor protects someone. Everyone acts *at the same time* on their own
   phone — see the note below. Villagers wait.
3. **Dawn.** The shared screen narrates what happened. A successful save is
   announced only as "no one died last night" — naming the saved player would
   hand the town a confirmed-innocent every time the doctor guessed right.
4. **Discussion.** Talk. Anyone can tap "ready"; the vote opens when everyone is
   ready or the clock runs out.
5. **Vote.** Everyone picks someone or abstains. Plurality eliminates, and their
   role is revealed. A tie eliminates nobody.
6. Repeat until one side wins.

**Win conditions.** The town wins when the last mafia is gone. The mafia win
when they equal the number of remaining townsfolk.

## Roles

| Players | Mafia | Detective | Doctor | Villagers |
|--------:|------:|----------:|-------:|----------:|
| 4       | 1     | 1         | 1      | 1         |
| 5       | 1     | 1         | 1      | 2         |
| 6       | 2     | 1         | 1      | 2         |
| 7       | 2     | 1         | 1      | 3         |
| 9       | 3     | 1         | 1      | 4         |
| 12      | 4     | 1         | 1      | 6         |

One mafia per three players, always at least one. Up to 20 at a table.

The doctor may protect themselves, but **never the same person two nights in a
row**. Skipping a night clears that restriction.

## Why the night is simultaneous

With a human host, "mafia, open your eyes" has to happen one group at a time —
otherwise people peek. That constraint is about eyelids, not about the rules:
the kill, the investigation, and the save are independent, so resolving them
together produces exactly the same outcome. Doing it in parallel makes the night
about three times shorter. The engine still resolves them in a fixed order
internally, so the result is deterministic.

## How secrets stay secret

Every player gets an unguessable token when they join, stored in their browser.
The server keeps two views of the game and they are computed separately:

- `public_state()` — what the shared screen and everyone else may see. Living
  players' roles are never in it, and neither are night choices or who voted for
  whom.
- `private_state(player_id)` — one player's slice: their role, their mafia
  partners, their detective notebook, their legal targets.

The shared screen connects with no token at all, so there is nothing for it to
leak. The role card on each phone stays hidden behind a "tap to see your role"
veil so a neighbour cannot read it over your shoulder.

This protects against the ordinary problem — someone glancing at the wrong
screen. It is not hardened against a player who opens the browser devtools and
starts crafting requests. That's a house-rules problem, not a software one.

## If someone's phone dies

Roles are held by token, not by connection. Reopen the page on the same phone
and you are back where you were. The table screen shows a grey dot next to
anyone currently disconnected. Phase timers keep running regardless, so one
person walking away cannot stall the game — if the mafia never submit a target,
nobody dies that night.

## Layout

```
server.py           HTTP + server-sent events; argument parsing; the phase clock
mafia/game.py       the rules engine — pure state machine, no I/O, no threads
mafia/roles.py      role definitions and the count-per-table-size table
mafia/room.py       tokens, thread safety, and pushing state to subscribers
static/             the player phone view and the shared table view
tests/test_game.py  engine tests, including a random-play game that must end
tests/test_server.py end-to-end: plays a real game over HTTP
```

The engine takes `now` as an argument rather than reading the clock, so tests
drive time directly instead of sleeping.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```
