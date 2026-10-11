"""Write UnitSlots.py: which units share a build-menu position.

A building's unit menu is a fixed row of positions, one per *line*, and each
position shows the one unit of its line that is valid right now. An empty
position means that line has no tier in this epoch. Read off a vanilla Barracks:

    slot   Bronze        Dark          Imperial          Digital
    1      (empty)       (empty)       Musketeer         Sentinel
    2      Short Sword   Short Sword   (empty)           (empty)
    3      Phalanx       Phalanx       Halberdier        (empty)
    4      -             Viking        Hand Cannoneer    Heavy Mortar
    5      -             Barbarian     Sharpshooter      (empty)
    6      -             -             Medic-Imperial    Medic-Digital
    7      -             -             Elite Guard       Stinger Soldier

This is not the upgrade chain. `gen_upgrades` calls the Viking and the
Barbarian standalone and is right about upgrades — nothing replaces either —
yet slot 4 runs Viking to Hand Cannoneer to Heavy Mortar. What decides whether
you can still recruit something is the slot, so that is what a retired unit's
check has to follow.

It matters because holding units open breaks the rotation. When two units of
one slot are valid at once the engine shows the earlier, so clearing every
unit's expiry pins each slot to its first tier and hides the rest — a run
reached the Imperial Age with the Rock Thrower still sitting in slot 1 and no
way to recruit a Musketeer.

Slots are derived, not read: no field in the node, its state object or its
button holds a position. Every unit has a first epoch (`node + 0x14`) and an
expiry (`node + 0x18`), and units sharing a slot hold disjoint consecutive
intervals within one building, so partitioning the intervals recovers the row.

    py tools\\gen_unit_slots.py            # derive and report
    py tools\\gen_unit_slots.py --verify   # check against the listings above
    py tools\\gen_unit_slots.py --write    # rewrite UnitSlots.py

Run it in a **vanilla** match. An Archipelago client rewrites the very expiry
this reads, and the tool refuses to run when it sees that.
"""

from __future__ import annotations

import argparse
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "world", "empire_earth"))

# `Locations` imports names from BaseClasses, which only exists inside
# Archipelago. Stubbed with just enough to satisfy the class definitions —
# none of the tables this reads touch it.
import types as _types                                            # noqa: E402

if "BaseClasses" not in sys.modules:
    _fake = _types.ModuleType("BaseClasses")
    _fake.Location = object
    _fake.Item = object

    class _Classification:
        progression = "progression"
        filler = "filler"
        useful = "useful"

    _fake.ItemClassification = _Classification
    sys.modules["BaseClasses"] = _fake

from Memory import attach                                        # noqa: E402
from Addresses import profile_for, ResourceAccess                # noqa: E402
from Epochs import EpochAccess                                   # noqa: E402
from Roster import Roster                                        # noqa: E402
from BuildingGate import (NODE_VTABLE, NODE_SIZE, NODE_TREE,      # noqa: E402
                          NODE_BUTTON, NODE_EPOCH, BUTTON_TEXTURE)
from Technologies import TECHNOLOGIES                             # noqa: E402
import Locations as L                                             # noqa: E402

OUT = os.path.join(ROOT, "world", "empire_earth", "UnitSlots.py")
EXE_NAMES = ("EE-AOC.exe", "ee-aoc.exe")
NODE_OBSOLETE_AFTER = 0x18
NEVER = 15

# The four rows above, as the tool should reproduce them. Read off a vanilla
# Barracks; the Viking/Hand Cannoneer pairing in slot 4 is the one that proves
# this isn't just re-deriving the upgrade chain.
LISTINGS = {
    3: ["", "Short Sword", "Phalanx"],
    4: ["", "Short Sword", "Phalanx", "Viking", "Barbarian"],
    7: ["Musketeer", "", "Halberdier", "Hand Cannoneer", "Sharpshooter",
        "Field Medic - Imperial", "Elite Guard"],
    12: ["Sentinel", "", "", "Heavy Mortar", "", "Field Medic 13",
         "Stinger Soldier"],
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def icon_stem(texture: str) -> str:
    stem = texture.split("\\")[-1].lower()
    if stem.endswith(".sst"):
        stem = stem[:-4]
    m = re.match(r"^but_(.*?)(?:_\d+t?)?$", stem)
    return m.group(1) if m else stem


def sweep(proc, roster, tree):
    """(icon, first epoch, expires-after) for every node on this tree."""
    out = []
    needle = struct.pack("<I", NODE_VTABLE)
    for base, data in proc.snapshot(want_image=False, want_private=True,
                                    want_mapped=False):
        off = -1
        while True:
            off = data.find(needle, off + 1)
            if off < 0:
                break
            if off % 4 or off + NODE_SIZE > len(data):
                continue
            if struct.unpack_from("<I", data, off + NODE_TREE)[0] != tree:
                continue
            button = struct.unpack_from("<I", data, off + NODE_BUTTON)[0]
            if not button:
                continue
            texture = roster.read_uwstring(button + BUTTON_TEXTURE)
            if not texture:
                continue
            out.append((
                texture,
                struct.unpack_from("<i", data, off + NODE_EPOCH)[0],
                struct.unpack_from("<i", data, off + NODE_OBSOLETE_AFTER)[0],
            ))
    return out


# Icons the game spells differently from the unit. Same idea as
# `gen_technologies.ALIASES`, and the same reason: fuzzy matching on a name
# this short guesses wrong more often than it helps.
ALIASES = {
    # The Sampson throws a log at buildings and the game files him under
    # `but_logguy_03t`, so nothing about his name reaches his icon. Found by
    # his span instead: the only node starting at epoch 1 and expiring after 2.
    "Sampson": "logguy",
    "Long Sword": "longswordsman",
    "Field Medic - Imperial": "medicimperial",
    "Field Medic WWII": "medicwwii",
    "Field Medic 11": "medic11",
    "Field Medic 13": "medic13",
    # The rest are units whose menu position is never taken by anything, so
    # they have to be held open to the end of the game and the client needs a
    # node for each. Names read off the button icons in `data.ssa`; the epoch
    # check picks which tier when several share a stem.
    "Persian Cavalry": "persiancav",
    "Balistae": "ballista",            # one L in the icon, two in the database
    "Heavy Ram": "ram",                # `but_ram_06t`, beside the Ram's `_04t`
    "Heavy Tower": "siegetower",
    "Bazooka Infantry": "bazooka",
    "Flame Thrower": "flamethrowercamo",
    "Sopwith Camel F.1": "sopwith",
    "Royal Galleon": "galleon",
    # The Sniper is drawn as the epoch 10 Sharpshooter and the Sharpshooter as
    # the epoch 8 one, which is the whole difference between them.
    "Sniper": "sharpshooter",
    # Both balloons are `but_observationballoon`, whatever the database calls
    # them. Also the reason the Capitol listing reads Hot Air, Observation, Hot
    # Air across epochs 8 to 11 — one of those was read off the icon.
    "Hot Air Balloon": "observationballoon",
}


def match_nodes(rows, tech):
    """Unit display name -> (first epoch, expires-after), one node each.

    Matched per *unit* rather than per icon, and constrained to a node within
    an epoch of where the unit belongs. Keying on the icon alone put three
    different `Spearman` intervals in the table and a `Short Sword` that never
    expired, because several nodes normalise to one name — the same trap
    `Research` avoids by keying on (texture, epoch).
    """
    try:
        from Objects import UNIT_MIN_EPOCH
    except ImportError:
        from .Objects import UNIT_MIN_EPOCH

    by_stem = {}
    for texture, first, last in rows:
        raw = texture.split("\\")[-1].lower()
        if raw.endswith(".sst"):
            raw = raw[:-4]
        if raw in tech:
            continue
        full = texture.split("\\")[-1].lower()
        if full.endswith(".sst"):
            full = full[:-4]
        by_stem.setdefault(norm(icon_stem(texture)), []).append(
            (first, last, full))

    out, missed = {}, []
    for db, display in sorted(L.UNIT_DISPLAY.items()):
        if f"Recruit {display}" not in L.ALWAYS_LOCATIONS:
            continue
        want = UNIT_MIN_EPOCH.get(db, 0)
        keys = [norm(ALIASES.get(display, display)),
                norm(re.sub(r"^[A-Za-z]*\d*\s*-?\s*", "", db))]
        hits = [h for k in keys for h in by_stem.get(k, ())]
        near = [h for h in hits if abs(h[0] - want) <= 1]
        if not near:
            missed.append(f"{display} (epoch {want})")
            continue
        out[db] = min(near, key=lambda h: abs(h[0] - want))
    return out, missed


def write_icons(matched, path):
    """Write UnitIcons.py: database name -> the button icon of its node.

    The one thing that can only come from a running game. Everything else about
    a slot is in tools/data, but a node carries no name — its icon is the only
    handle these structures offer — so closing a slot gap needs this map to
    find the node to write to. See Obsolescence.GAPS.
    """
    lines = [
        '"""Database name -> the button icon of that unit\'s tech tree node.',
        "",
        "Generated by tools/gen_unit_slots.py --icons against a running game.",
        "Don't edit by hand.",
        "",
        "A node holds no name. The icon is the only handle, which is why this",
        "exists at all — the client needs it to find the node behind a unit",
        "named in UnitSlots.SLOT_GAPS.",
        '"""',
        "",
        "UNIT_ICONS: dict[str, str] = {",
    ]
    for db in sorted(matched):
        lines.append(f"    {db!r}: {matched[db][2]!r},")
    lines += ["}", ""]
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return len(matched)


def clamp(matched):
    """End each unit's interval where the next tier of its line begins.

    A unit is hidden two ways, and expiry is only one of them. The Clubman and
    the Maceman both read `obsolete-after = 6`, yet the Clubman is gone by the
    Copper Age — the Maceman *supersedes* it (`node + 0x05`), which the expiry
    field says nothing about. Partitioning on expiry alone put consecutive
    tiers of one line in different slots because their intervals overlapped.

    `UNIT_SUPERSEDES` gives the next tier inside a line, so its first epoch is
    where the current one stops being drawn. Expiry still ends the interval
    where no upgrade follows, which is what carries a slot across lines —
    nothing upgrades a Viking into a Hand Cannoneer.
    """
    try:
        from Upgrades import UNIT_SUPERSEDES
    except ImportError:
        from .Upgrades import UNIT_SUPERSEDES

    # unit -> the earliest unit that replaces it, by first epoch
    successor = {}
    for later, replaced in UNIT_SUPERSEDES.items():
        if later not in matched:
            continue
        for db in replaced:
            if db not in matched:
                continue
            best = successor.get(db)
            if best is None or matched[later][0] < matched[best][0]:
                successor[db] = later

    out = {}
    for db, (first, last) in matched.items():
        nxt = successor.get(db)
        if nxt is not None:
            last = min(last, matched[nxt][0] - 1)
        out[db] = (first, max(first, last))
    return out


def partition(units):
    """Group [(display, first, last)] into slots of disjoint intervals.

    Greedy by first epoch, into the earliest slot already free. The row the
    game draws is the smallest such partition — a line only exists because
    nothing else is using that position — so the minimal packing is the one to
    reproduce.
    """
    slots: list[list[tuple[str, int, int]]] = []
    for entry in sorted(units, key=lambda u: (u[1], u[2], u[0])):
        for slot in slots:
            if slot[-1][2] < entry[1]:
                slot.append(entry)
                break
        else:
            slots.append([entry])
    return slots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--icons", action="store_true",
                    help="write UnitIcons.py and stop")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--building", default="Barracks")
    args = ap.parse_args()

    proc = attach(*EXE_NAMES)
    if not proc:
        sys.exit("Empire Earth is not running, or it is elevated and this "
                 "shell is not.")
    mods = proc.modules()
    profile = profile_for(mods[0][0] if mods else proc.exe)
    if profile is None:
        sys.exit("no memory profile matches this build")
    res = ResourceAccess(proc, profile)
    epochs = EpochAccess(proc, res)
    tree = epochs.tech_tree()
    if not tree:
        sys.exit("not in a match")

    rows = sweep(proc, Roster(proc, profile), tree)
    tech = {v[2] for v in TECHNOLOGIES.values()}

    matched, missed = match_nodes(rows, tech)
    if args.icons:
        out = os.path.join(ROOT, "world", "empire_earth", "UnitIcons.py")
        n = write_icons(matched, out)
        print(f"wrote {n} icons -> {out}")
        if missed:
            print(f"{len(missed)} unit(s) had no node: {', '.join(missed[:8])}")
        return
    matched = clamp(matched)
    named = [(L.UNIT_DISPLAY[db], a, b) for db, (a, b) in matched.items()]
    unmatched = missed

    expiring = [u for u in named if u[2] < NEVER]
    if named and len(expiring) < len(named) // 20:
        sys.exit(f"only {len(expiring)} of {len(named)} units expire — this "
                 "looks like a match an Archipelago client has already opened "
                 "up. Run it in a vanilla game.")

    print(f"{len(named)} units matched to a node, {len(unmatched)} not found")
    if unmatched:
        print("  unmatched: " + "; ".join(sorted(unmatched)[:60]))

    per_building: dict[str, list] = {}
    for display, first, last in named:
        for b in L.RECRUIT_LOCATION_PRODUCERS.get(f"Recruit {display}", ()):
            per_building.setdefault(b, []).append((display, first, last))

    slots = {b: partition(u) for b, u in per_building.items()}

    row = slots.get(args.building, [])
    print(f"\n{args.building}: {len(row)} slots")
    for n, slot in enumerate(row, 1):
        print(f"  {n}: " + ", ".join(f"{d} [{a}..{b}]" for d, a, b in slot))

    if args.verify:
        print("\nverifying against the vanilla listings")
        bad = 0
        for epoch, expected in sorted(LISTINGS.items()):
            got = []
            for slot in row:
                live = [d for d, a, b in slot if a <= epoch <= b]
                got.append(live[0] if live else "")
            got = got[:len(expected)]
            ok = got == expected
            bad += 0 if ok else 1
            print(f"  epoch {epoch:2d}  {'OK  ' if ok else 'WRONG'}  {got}")
            if not ok:
                print(f"            expected  {expected}")
        print("all four rows reproduced" if not bad else f"{bad} row(s) wrong")
        if bad:
            return

    if not args.write:
        print("\nnot written; pass --write")
        return

    lines = [
        '"""Which units share a build-menu position.',
        "",
        "Generated by tools/gen_unit_slots.py from a vanilla match. Don't edit",
        "by hand.",
        "",
        "A building's menu is a fixed row of positions, one per line, showing",
        "the one unit of that line valid in this epoch. A unit retires and the",
        "next takes its position — so the check for a retired unit has to be",
        "carried by whatever takes its slot, not by whatever the upgrade chain",
        "calls its replacement. The two differ: slot 4 of the Barracks runs",
        "Viking to Hand Cannoneer to Heavy Mortar, and no upgrade connects any",
        "of them.",
        '"""',
        "",
        "# building -> slots, each earliest occupant first",
        "UNIT_SLOTS: dict[str, tuple[tuple[str, ...], ...]] = {",
    ]
    for b in sorted(slots):
        inner = ", ".join(
            "(" + ", ".join(repr(d) for d, _a, _z in slot) + ",)"
            for slot in slots[b]
        )
        lines.append(f"    {b!r}: ({inner},),")
    lines += [
        "}",
        "",
        "# unit -> every unit that held its slot before it, so the current",
        "# occupant sends all of their checks.",
        "SLOT_PREDECESSORS: dict[str, tuple[str, ...]] = {",
        "    unit: tuple(slot[:i])",
        "    for slots in UNIT_SLOTS.values()",
        "    for slot in slots",
        "    for i, unit in enumerate(slot)",
        "    if i",
        "}",
        "",
    ]
    with open(OUT, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
