# Design brief — Mafia (hostless party game)

A self-contained prompt. Paste into Claude Design or any design tool; it assumes
no knowledge of the codebase.

---

## The product

Mafia (Werewolf) played in one room, with the computer acting as host so nobody
has to sit out and moderate. Every player uses their own phone. A laptop or TV
shows a shared screen.

4–20 players. Roles: mafia (scales with table size), one detective, one doctor,
the rest villagers. Nights and days alternate until the mafia are all gone or
they equal the town.

## Design two surfaces with opposite jobs

**The phone — a private script.** Held low, in a dim room, glanced at for a few
seconds at a time. It carries the only genuinely secret information in the game:
your role, your night action, the detective's findings. Its hardest constraint
is social, not technical — the person beside you must not be able to read it,
including by accident when you put the phone down.

**The shared screen — the stage.** Read from three or four metres away by
everyone at once. It is the narrator: it announces the phase, tells the story of
each night, and shows who is alive. It must never display anything secret. Type
here should be large enough to read across a room.

The tension between these two — intimate versus theatrical — is the brief.

## States to design

Phone: join, lobby, night (three variants: mafia choosing a victim, detective
investigating, doctor protecting, plus a "you have no night action" state), day
discussion, voting, dead-player view, game over.

Shared screen: lobby with the join address, night, day, vote, game over with all
roles revealed.

## The direction

Playbill theatre. The computer is narrating a performance the people in the room
are giving, so the interface is styled as a theatre programme: acts, title
cards, a cast list, stage directions.

**Palette.** The whole interface inverts between two lighting states. Gold is
the only colour that survives the inversion.

| role | night (ink) | day (parchment) |
|---|---|---|
| ground | `#0E1020` | `#EFE7D6` |
| raised surface | `#171B33` | `#F7F2E6` |
| text | `#C9D2F0` | `#23201A` |
| secondary text | `#7C86AE` | `#6E6555` |
| gold (as text) | `#C9A227` | `#6F5714` |
| death / mafia | `#E0566D` | `#8E2436` |

Gold as *text* must differ per mode: `#C9A227` on parchment measures 1.97:1 and
is unreadable. Every text pair must clear WCAG AA (4.5:1).

**Type.** Display: Cinzel — engraved Roman capitals, inscriptional, used only for
title cards, phase names, and the role name. Body and controls: a plain system
sans, so the display face carries all the personality. Stage directions
(narration) in a system serif italic.

**Structure.** The player roster is set as a **cast list**: name, leader dots,
billing. A roster *is* a cast list, so the device is true rather than decorative.

## The two things worth keeping

1. **Hold to peek.** The role card is face-down by default. Press *and hold* to
   look at it; releasing hides it again. Borrowed from peeking at hole cards —
   and unlike a tap-to-toggle, it makes it impossible to leave your role sitting
   face-up on the table.

2. **The room changes light.** At every phase change the entire interface
   inverts — ink to parchment at dawn, back at dusk — with a brief full-screen
   title card announcing the act ("Act 2 · Night — The town sleeps"). Every phone
   in the room does this at the same moment. Twelve screens turning over at once
   is a real physical event at a party, and it is the thing people remember.

Spend the boldness there. Keep everything else quiet.

## Copy

Plain and active. Buttons say exactly what happens: "Kill Ana", "Protect Cy",
"Vote out Dot", "I'm ready to vote". Do **not** rename the mechanics into theatre
language — players say "detective" and "doctor" out loud at the table, so the
interface must use the same words. The theatre framing lives in the narration,
the structure, and the title cards, never in the labels.

Announce a successful save as "No one died last night" without naming who was
saved — naming them would hand the town a confirmed-innocent every time the
doctor guessed right.

## Constraints

- Phone-first, responsive; the shared screen is a wide layout.
- Legible in a dark room without being a flashlight in someone's face.
- Visible keyboard focus; `prefers-reduced-motion` respected.
- Self-hosted assets only — the game must run on a laptop with no internet,
  on a home Wi-Fi network. No CDN fonts, no external requests.

## Please avoid

The default "dark game UI" look: pure black plus one acid accent, neon glow,
glassmorphism, heavy border-radius, generic 01/02/03 numbering, or a
high-contrast serif with a terracotta accent on cream. Nothing here should look
like it could belong to any other product.
