"""Write Upgrades.py: which units a unit supersedes.

Empire Earth retires a unit when a later tier replaces it — the Archery Range
stops offering Slingers once you have Simple Bowmen — which makes a per-unit
check missable. The client used to clear the engine's `superseded` flag to stop
that. It doesn't keep the old unit *beside* the new one, it cancels the
upgrade — the menu falls back to Slingers and the Simple Bowman's own check can
never be sent. See `notes/REVERSE.md`.

So the upgrade is left alone and recruiting a unit sends the checks for
everything below it instead. Build a Simple Bowman and Slinger's check goes
too. Build a Long Bow and all four below it go.

    py tools\\gen_upgrades.py [--write]

## Where the chain comes from

Not from the database. A record is 1948 bytes and an "upgrades to" index would
be the obvious thing to find in one, but scanning `Arch03 - Simple Bowman`'s
record for `Arch02 - Slinger`'s index — and the same for Clubman/Maceman,
Horseman/Cataphract, Spearman/Phalanx — finds no offset that holds for more
than one pair. The field isn't there.

What the names do carry is a tier: `Arch02`, `Arch03`, `Arch05`, `Arch06`, and
the number is the epoch, one-indexed. Grouping by (family, name prefix) and
ordering by that tier gives the line.

Two things stop this being a plain sort.

*Same-tier units are alternatives, not upgrades.* `Arch05 - Composite Bow` and
`Arch05 - Cross Bow` both replace the Simple Bowman and neither replaces the
other, so a unit only ever supersedes **strictly lower** tiers. That falls out
of the rule and needs no special case.

*A few groups bundle several roles.* `Ship` holds 27 units across frigates,
transports, fishing boats, catapult ships and cruisers, and a Fishing Boat
doesn't upgrade into a Frigate. Those groups get a `ROLES` entry and split on
it.

## Why a wrong answer here is survivable in one direction only

* A **missing** link — nothing sends a superseded unit's check — can leave a
  seed unwinnable, because unit checks carry progression.
* An **extra** link — a check sent for something never built — is a free check
  and the seed still completes.

Every choice below leans the second way. Splitting a group is the risky
operation, since that's what creates missing links, so only groups whose roles
are unmistakable in the name get split. Any member whose role isn't recognised
stays in the bundle, superseded by every higher tier in the group whatever
their role. Merging too much costs checks, never runs.
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "world", "empire_earth"))
_f = types.ModuleType("BaseClasses")
_f.Location = object
_f.Item = object


class _Classification:
    progression = "progression"
    filler = "filler"
    useful = "useful"


_f.ItemClassification = _Classification
sys.modules.setdefault("BaseClasses", _f)
from Objects import UNIT_FAMILY_BY_NAME  # noqa: E402

OUT = os.path.join(ROOT, "world", "empire_earth", "Upgrades.py")

# `<letters><tier> - <name>`, where the tier is the epoch counted from 1.
TIER = re.compile(r"^([A-Za-z ]*?)(\d+)\s*(?:-\s*)?(.+)$")

# Heroes are civilisation choices rather than tiers — one per civ per rank, and
# only one can exist in a match — so they're paired in Locations.py instead.
SKIP_FAMILIES = {"Hero"}

# Groups that hold several separate lines, and the words that tell them apart.
# Order matters — the first word found in the name wins, so anything more
# specific has to come first.
#
# A name matching none of these keeps role None, which does NOT make it its own
# line. It stays superseded by every higher tier in the group. `s11 Warrington`
# is the case that matters — no role word, and guessing it into the cruiser
# line risks the one error that breaks seeds.
ROLES = {
    ("Ship", "s"): (
        "Fishing Boat", "Catapult Ship", "Transport", "Frigate", "Cruiser",
    ),
    # Ram and Tower are two lines that share tiers 4 and 6; "Heavy Ram" and
    # "Heavy Tower" carry their own role word, so this split is unambiguous.
    ("Ram", "Siege"): ("Ram", "Tower"),
}


# Units that are a line unto themselves — they replace nothing and nothing
# replaces them. A tier number alone can't tell these apart from a rung on a
# ladder, because they sit at a tier like anything else.
#
# `Arch05 - Cross Bow` shares the Dark Age with `Arch05 - Composite Bow`, so
# the strictly-lower rule already stopped those two sending each other.
# `Arch06 - Long Bow` is above both and was sending Cross Bow's check as if it
# were the next rung. The wiki is unambiguous — the Archery Range "has only
# five different unit lines", the Archer line "starts in the Stone age with the
# Slinger ... and it ends with Long Bow in the Middle Ages", and "The Crossbow
# is the only of its line."
#
# Everything else that page describes the derivation already had right —
# Javelin to Pilum, Chariot Archer to Cavalry Archer, Elephant Archer alone.
#
# Listing something here is the one edit that can *remove* a link, so it wants
# a source rather than a hunch. An entry is a claim that nothing in the game
# ever replaces this unit.
STANDALONE_UNITS = {
    "Arch05 - Cross Bow",
    # The `Human` / `Inf` group isn't one ladder but four short ones and three
    # units that stand alone; see ROLE_OVERRIDES for the lines. Nothing
    # replaces any of these three.
    "Inf01 - Rock Thrower",
    "Inf09 - Partisan",
    "Inf11 - Flame Thrower",
    # The sword line runs Clubman -> Maceman -> Short Sword -> Long Sword. A
    # Barbarian sits between the last two on tier alone and isn't part of it.
    # The wiki lists Barbarians beside Short Swords in the Dark Age and Middle
    # Ages, never as an upgrade of one.
    "Inf05 - Barbarian",
    # Art of Conquest's Space Age infantry. It shares the `Human` family and
    # the `Inf` prefix with everything from the Rock Thrower up, so the
    # fallback had it carrying eight checks. It replaces none of them.
    "Inf15 - Cyber Ninja",
}

# Upgrades that cross a group boundary, which the tier rule can't see at all —
# both sides have to share a family and a name prefix for it to look at them.
#
# `AA10 - Stinger Soldier` is family `Land AA`, `Inf11 - Bazooka Infantry` is
# family `Human`. Nothing in the names or the families connects them, but the
# wiki's Barracks list is explicit — Atomic Age - Modern reads "Bazookas ►
# Stinger Soldiers" — so on reaching that epoch the Bazooka goes and its check
# would have gone with it.
#
# Whatever is named here is closed transitively afterwards, so the Stinger also
# carries the Grenade Launcher that the Bazooka replaced.
EXTRA_SUPERSEDES = {
    "AA10 - Stinger Soldier": ("Inf11 - Bazooka Infantry",),
}

# Units whose line the name doesn't spell out. Same risk as STANDALONE_UNITS,
# so same standard of evidence.
#
# `s11 Warrington` is a frigate, and the only one not named "Frigate". Left to
# the role words it matched none of them, so under the rule below it stayed in
# the whole `Ship` bundle and sent 21 checks at once. The wiki gives
# the line explicitly, "upgrades from Frigate - Good Hope, upgrades to Frigate
# - Juggernaut", which is exactly where its tier already put it.
ROLE_OVERRIDES = {
    "s11 Warrington": "Frigate",

    # The `Human` / `Inf` group. Ten units sharing a family and a prefix, which
    # the tier rule read as one ladder from Rock Thrower to Heavy Mortar. It's
    # nothing of the sort — three stand alone (above) and the rest are four
    # separate two- and three-rung lines, none of them guessable from the
    # names. A Sharpshooter becomes a Sniper, a Hand Cannoneer becomes a Trench
    # Mortar.
    "Inf08 - Sharpshooter": "Marksman",
    "Inf10 - Sniper": "Marksman",

    "Inf08 - Hand Cannoneer": "Mortar",
    "Inf10 - Trench Mortar": "Mortar",
    "Inf12 - Heavy Mortar": "Mortar",

    "Inf10 - Grenade Launcher": "Grenade",
    "Inf11 - Bazooka Infantry": "Grenade",
}


def role_of(group: tuple[str, str], name: str) -> str | None:
    override = ROLE_OVERRIDES.get(name)
    if override:
        return override
    for word in ROLES.get(group, ()):
        if word.lower() in name.lower():
            return word
    return None


def lines() -> dict[tuple[str, str], list[tuple[int, str]]]:
    groups: dict[tuple[str, str], list[tuple[int, str]]] = collections.defaultdict(list)
    for name, family in UNIT_FAMILY_BY_NAME.items():
        if name.lower().startswith("x") or family in SKIP_FAMILIES:
            continue
        m = TIER.match(name)
        if not m:
            continue                        # no tier in the name: never a line
        groups[(family, m.group(1).strip())].append((int(m.group(2)), name))
    return groups


def supersedes() -> dict[str, list[str]]:
    """unit -> every unit it replaces, lowest tier first."""
    out: dict[str, list[str]] = {}
    for group, members in lines().items():
        for tier, name in members:
            if name in STANDALONE_UNITS:
                continue                    # replaces nothing
            role = role_of(group, name)
            below = [
                (t, n) for t, n in members
                if t < tier
                and n not in STANDALONE_UNITS   # and nothing replaces it
                # Same line, or either side's role is unknown — see ROLES.
                and (role is None or role_of(group, n) in (role, None))
            ]
            if below:
                out[name] = [n for _t, n in sorted(below)]

    for name, extra in EXTRA_SUPERSEDES.items():
        out.setdefault(name, [])
        out[name] += [n for n in extra if n not in out[name]]

    # Close transitively. Within a group this changes nothing — every lower
    # tier is already listed — but a cross-group link lands mid-chain, and the
    # rungs below it have to come too or they're lost at that same epoch.
    for name in list(out):
        seen, stack = set(out[name]), list(out[name])
        while stack:
            for below in out.get(stack.pop(), ()):
                if below not in seen and below != name:
                    seen.add(below)
                    stack.append(below)
        out[name] = sorted(seen)
    return out


def emit(table: dict[str, list[str]]) -> str:
    head = '"""Which units each unit replaces, generated by tools/gen_upgrades.py.'
    lines_out = [
        head,
        "",
        "Don't edit by hand — re-run the generator.",
        "",
        "Recruiting a unit sends the checks for everything it supersedes, which",
        "is what keeps those checks sendable once the game has retired them.",
        "Keys and values are raw database names, as the game reports them.",
        '"""',
        "",
        "UNIT_SUPERSEDES: dict[str, tuple[str, ...]] = {",
    ]
    for name in sorted(table):
        inner = ", ".join(repr(n) for n in table[name])
        lines_out.append(f"    {name!r}: ({inner},),")
    lines_out += ["}", ""]
    return "\n".join(lines_out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    groups = lines()
    table = supersedes()

    for group, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        family, prefix = group
        byrole = collections.defaultdict(list)
        alone = []
        for tier, name in sorted(members):
            # Shown apart, or the report reads as if these were rungs of the
            # line they're listed under — the exact mistake the list exists to
            # correct.
            if name in STANDALONE_UNITS:
                alone.append((tier, name))
            else:
                byrole[role_of(group, name)].append((tier, name))
        print(f"  {family} / {prefix}")

        def show(label: str, mem: list[tuple[int, str]], joiner: str) -> None:
            chain = joiner.join(f"{t}:{n.split(' - ')[-1]}" for t, n in mem)
            print(f"      {label:<34s} {chain}")

        for role, mem in sorted(byrole.items(), key=lambda kv: str(kv[0])):
            show(role or "(no role word - stays in the bundle)", mem, " -> ")
        if alone:
            show("(a line each - replaces nothing)", alone, ", ")
        print()

    covered = sum(1 for v in table.values() if v)
    tops = [n for g in groups.values() for _t, n in g if n not in table]
    print(f"{len(table)} units supersede something; {len(tops)} are the lowest "
          f"tier of their line and supersede nothing")
    print(f"{covered} cascade entries written")

    if args.write:
        with open(OUT, "w", encoding="utf-8", newline="\n") as f:
            f.write(emit(table))
        print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
