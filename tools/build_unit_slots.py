"""Write UnitSlots.py from the observed menu listings in tools/data.

The listings are what a vanilla game draws, epoch by epoch, position by
position — see barracks_slots.tsv for why they're observed rather than derived.
They name units the way the *screen* does, which is not how the object database
does: "Ballista" against `Gun Spear06 Balistae`, "Canine Scout" against
`Domestic Wolf`, "Battleship - Copper" against `s03 Copper Battleship [Galley]`.
This reconciles the two and emits the table.

Matching is on words, not on the whole string. A screen name matches a unit when
every word of it appears in that unit's database name, after dropping the tier
prefix and anything in brackets — so "Battleship - Copper" finds the Copper
Battleship whichever order the two words come in. Ties go to the shortest
candidate, because `Frigate - Good Hope` should find the Good Hope Frigate
rather than merely a Frigate.

    py tools\\build_unit_slots.py            # report what matched
    py tools\\build_unit_slots.py --write    # rewrite UnitSlots.py

Anything unmatched is printed rather than dropped, for an ALIASES entry. A
missing unit costs its check the moment its slot moves on, so this fails loudly
rather than emitting a table with holes in it.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(HERE, "data")
sys.path.insert(0, os.path.join(ROOT, "world", "empire_earth"))

if "BaseClasses" not in sys.modules:                     # see gen_unit_slots
    _fake = types.ModuleType("BaseClasses")
    _fake.Location = object
    _fake.Item = object

    class _Classification:
        progression = "progression"
        filler = "filler"
        useful = "useful"

    _fake.ItemClassification = _Classification
    sys.modules["BaseClasses"] = _fake

import Locations as L                                    # noqa: E402

OUT = os.path.join(ROOT, "world", "empire_earth", "UnitSlots.py")

# Screen name -> database name, where no amount of word matching gets there.
ALIASES = {
    "Canine Scout": "Domestic Wolf",
    # The medics were renamed to match the screen, which left the listings
    # naming this one the way the database still does.
    "Field Medic - Imperial": "Field Medic - Imperial",
    # Not a check — a second database record for the Digital medic — but it
    # holds Barracks slot 6 from the Digital Age on, so the table needs it or
    # the position reads as one that empties for good.
    "Field Medic 13": "Field Medic 13",
    "Ballista": "Gun Spear06 Balistae",
    "Siege Tower": "Siege04 - Tower",
    "Heavy Siege Tower": "Siege06 - Heavy Tower",
    "Colossus Artillery": "Gun Artillery13 Colossus",
    "Culverin": "Gun Cannon07 - Culverin Cannon",
    "Basilisk": "Gun Siege07 Basilisk Cannon",
    "Serpentine": "Gun Siege09 Serpentine Cannon",
    "120mm AT Gun": "Gun AT12 120mm At Gun",
    "War Raft": "s02 Stone Frigate [War Raft]",
    "Fishing Raft": "s02 Fishing Boat Stone",
    "Transport Raft": "s02 Stone Transport",
    "Fishing Boat - Trawler": "s11 Fishing Boat Modern",
    "Cruiser - Darbo": "s10 Cruiser",
    "Cruiser - Gunboat": "s08 Gunboat Cruiser",
    "Cruiser - Sagitarrian": "s13 Sagitarian Cruiser",
    "Battleship - Leviathan": "s13 Leviathon Battleship",
    "Frigate - Warrington": "s11 Warrington",
    "Transport - Atomic": "s10 Atomic Age Transport",
    "Transport - Gargantua": "s13 Gargantua Transport",
    "Fishing Boat - Digital": "s13 Digital Fishing Boat",
    "Sub - U-Boat": "s10 U Boat",
    "Carrier - Enterprise": "s11 Enterprise Aircraft Carrier",
    "Carrier - Nexus": "s13 Nexus Carrier",
    "Flak Halftrack": "10 AA - Tank",
    "Skywatcher AA": "13 AA Tank Skywatcher",
    "MkV Tank (HE)": "Tank10  Mk V",
    "M1 Tank (HE)": "Tank12  M1A1",
    "Travis Shackelford": "h2-11 Shackelford (Morale)",
    "Manfred von Richthofen": "h2-10 von Richtofen (Morale)",
    "Dennis St. Albans": "h2-12 St. Albans (Morale)",
    "RW Bresden": "h1-12 R.W. Bresden (heal)",
    "Erwin Rommel": "h1-11 Rommel (heal)",
    "Otto von Bismarck": "h1-9 Otto Von Bismarck (heal)",
    "Isabella of Castile": "h1-7 Isabella (heal)",
    "Oliver Cromwell": "h2-8 Oliver Cromwell (Morale)",
    "Julius Caesar": "h2-5 Julius Caesar (Morale)",
    # The Airport's helicopter row. Resolved from the database by epoch and
    # role, not from the screen: the Modern trio is the Apache Longbow for
    # anti-tank, the Gun Ship, and the Chinook, and the Digital transport is
    # the Pegasus that succeeds the Chinook in the same position.
    "Helicopter Anti-Tank": "a Helicopter Apache Longbow 12",
    "Helicopter Gunship": "a HelicopterGunShip12 Gun Ship",
    "Helicopter Transport": "a HelicopterXprt12 Chinook Transport 12",
    "Pegasus Transport": "a HelicopterXprt13 Pegasus",
    "P-51 Fighter": "a Fighter11 P51",
    "A-10 Anti-Tank": "a AT Fighter12 A-10",
    "Typhoon Anti-Tank": "a AT Fighter11 Typhoon",
    "A7V Tank (AP)": "Tank10 A7V",
    "Panzer Tank (AP)": "Tank11 Panzer",
    "Leopard Tank (AP)": "Tank12 Leopard",
    "Sherman Tank (HE)": "Tank11 Sherman",
    "Gladiator Tank": "Tank13 Gladiator",
    "Centurion Tank": "Tank14 Centurion",
    "B-29 Bomber": "a BomberNuc11 B-29",
    "B-52 Bomber": "a BomberNuc12 B-52",
    "Titan Bomber": "a BomberNuc13 Titan",
    "F-117 Fighter/Bomber": "a Strafe Fighter12 Stealth Fighter",
    "ME262 Fighter/Bomber": "a Strafe Fighter11 ME262",
    "Fokker Fighter/Bomber": "a Strafe Fighter10 Fokker DR.1",
    "Talon Fighter/Bomber": "a Strafe Fighter13 Talon",
    "Phoenix Fighter/Bomber": "a Strafe Fighter14 Phoenix",
    "F-15 Fighter": "a Fighter12 F-15",
    "Jackal Fighter": "a Fighter13 F-48 Jackal",
    "Nebula Fighter": "a Fighter14 F-96 Nebula",
    "Sopwith Fighter": "a Fighter10 Sopwith Camel F.1",
    "Frigate - Middle Ages": "s06 Middle Age Frigate",
    "Galley - Middle Ages": "s06 Middle Age Galley",
    "Long Sword": "Inf06 - LongSword",
    "Space Capital Ship": "Sp15 - Capital Ship",
    "Sub - Hammerhead": "s14 Hammerhead Submarine",
    "Sub - Nautilus": "s12 Nautilus Submarine",
    "Sub - Trident": "s12 Trident Submarine",
    "Sub - Triton": "s14 Triton Submarine",
    "Spectre AT Helicopter": "a HelicopterAT13 Spectre",
    "Reaper Gunship": "a HelicopterGunShip13 Reaper",
}

BRACKET = re.compile(r"[\[(].*?[\])]")
TIER = re.compile(r"^[A-Za-z]{0,4}\d*\s*-?\s*")


def words(s: str) -> set[str]:
    s = BRACKET.sub(" ", s)
    return {w for w in re.split(r"[^a-z0-9]+", s.lower()) if w}


def build_index():
    """Database name -> its words, for every unit in the database.

    Every unit, not only the ones that are checks. A menu position is occupied
    by whatever the game draws there, and some of those aren't checks —
    `Field Medic 13` is a second record for the Digital medic and was dropped
    to stop one unit appearing twice. Leave it out of the table and Barracks
    slot 6 looks like it empties after the Atomic Age, which is the shape of a
    check that closes for good, and `run_dead_slots` says so.

    Units that aren't checks fall out downstream: `_recruit_location` returns
    None for them, so they occupy a seat without sending or receiving anything.
    """
    try:
        from Objects import UNIT_FAMILY_BY_NAME
    except ImportError:
        from .Objects import UNIT_FAMILY_BY_NAME

    out = {db: words(TIER.sub("", db)) for db in UNIT_FAMILY_BY_NAME}
    for db, display in L.UNIT_DISPLAY.items():
        out.setdefault(db, set()).update(words(display))
    return out


def resolve(screen: str, index) -> str | None:
    if screen in ALIASES:
        db = ALIASES[screen]
        return db if db in index else None
    want = words(screen)
    if not want:
        return None
    hits = [db for db, have in index.items() if want <= have]
    if not hits:
        return None
    return min(hits, key=lambda db: (len(index[db]), len(db)))


def read_listings():
    """[(building, epoch, [screen name or '' per position])] from tools/data."""
    rows = []
    simple = {
        "barracks_slots.tsv": "Barracks",
        "archery_range_slots.tsv": "Archery Range",
        "stable_slots.tsv": "Stable",
        "temple_slots.tsv": "Temple",
    }
    for name, building in simple.items():
        path = os.path.join(DATA, name)
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8"):
            if line.startswith("#") or not line.strip():
                continue
            f = line.rstrip("\n").split("\t")
            rows.append((building, int(f[0]),
                         ["" if x == "-" else x for x in f[1:]]))
    path = os.path.join(DATA, "remaining_slots.tsv")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if line.startswith("#") or not line.strip():
                continue
            f = line.rstrip("\n").split("\t")
            rows.append((f[0], int(f[1]),
                         ["" if x == "-" else x for x in f[2:]]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    index = build_index()
    rows = read_listings()
    if not rows:
        sys.exit("no listings found in tools/data")

    # building -> slot number -> ordered, de-duplicated occupants
    slots: dict[str, dict[int, list[str]]] = {}
    spans: dict[tuple, list[int]] = {}
    last_epoch: dict[str, int] = {}
    unresolved: dict[str, int] = {}
    for building, epoch, positions in sorted(rows, key=lambda r: (r[0], r[1])):
        last_epoch[building] = max(last_epoch.get(building, 0), epoch)
        for n, screen in enumerate(positions):
            if not screen:
                continue
            db = resolve(screen, index)
            if db is None:
                unresolved[screen] = unresolved.get(screen, 0) + 1
                continue
            seat = slots.setdefault(building, {}).setdefault(n, [])
            if db not in seat:
                seat.append(db)
            span = spans.setdefault((building, n, db), [epoch, epoch])
            span[0] = min(span[0], epoch)
            span[1] = max(span[1], epoch)

    total = sum(len(s) for s in slots.values())
    print(f"{len(rows)} listing rows, {len(slots)} buildings, {total} slots")
    for building in sorted(slots):
        for n in sorted(slots[building]):
            seat = slots[building][n]
            if len(seat) > 1:
                names = " -> ".join(L.UNIT_DISPLAY.get(d, f"{d} (not a check)")
                                    for d in seat)
                print(f"  {building} slot {n + 1}: {names}")

    if unresolved:
        print(f"\n{len(unresolved)} screen name(s) unresolved:")
        for screen in sorted(unresolved):
            want = words(screen)
            near = sorted(
                ((len(want & index[db]) / max(len(want), 1), db)
                 for db in index if want & index[db]),
                reverse=True)[:3]
            hint = "  ".join(f"{db!r}" for _s, db in near) or "(nothing close)"
            print(f"    {screen!r:28s} -> {hint}")
        print("add each to ALIASES, then re-run")
        if args.write:
            sys.exit("refusing to write a table with holes in it")

    if not args.write:
        print("\nnot written; pass --write")
        return

    lines = [
        '"""Which units share a build-menu position.',
        "",
        "Built by tools/build_unit_slots.py from the observed listings in",
        "tools/data. Don't edit by hand.",
        "",
        "A building's menu is a fixed row of positions, one per line, showing",
        "the one unit of that line valid in this epoch. A unit retires and the",
        "next takes its position, so the check for a retired unit has to be",
        "carried by whatever takes its slot — not by whatever the upgrade chain",
        "calls its replacement. The two differ: slot 4 of the Barracks runs",
        "Viking to Hand Cannoneer to Heavy Mortar and no upgrade connects any",
        "of them.",
        '"""',
        "",
        "# building -> slots, each earliest occupant first, by database name",
        "UNIT_SLOTS: dict[str, tuple[tuple[str, ...], ...]] = {",
    ]
    for building in sorted(slots):
        inner = ", ".join(
            "(" + ", ".join(repr(d) for d in slots[building][n]) + ",)"
            for n in sorted(slots[building])
        )
        lines.append(f"    {building!r}: ({inner},),")
    # A slot with a hole in it: one occupant ends and nothing takes its place
    # for a while. `Recruit Rock Thrower` closes after the Stone Age and
    # nothing takes Barracks slot 1 until the Arquebus in the Renaissance, so
    # for four epochs that check cannot be sent by anything. Archipelago rules
    # are monotone and cannot say "reachable until epoch 1", so generation puts
    # progression on a check that has already closed.
    #
    # The fix is to hold the earlier unit open until its successor arrives —
    # one epoch short of it, so the two never overlap and the slot still
    # rotates on time. The client writes these; see Obsolescence.GAPS.
    #
    # A hole with nothing after it at all is the same problem and worse, because
    # it never closes. The AP tank line just stops: A7V to Panzer to Leopard,
    # and Tank Factory slot 2 is empty from the Digital Age to the end of the
    # game. `Recruit Leopard` shuts for good after Atomic Age - Modern, and a
    # seed put `Wonder: Library of Alexandria` on it. Those are held to NEVER,
    # which is safe for exactly the reason they're broken — nothing is waiting
    # for the position, so nothing can be squatted.
    NEVER = 15
    gaps = {}
    for building, seats in slots.items():
        for n, seat in seats.items():
            for db in seat:
                ends = spans[(building, n, db)][1]
                # The next occupant to start *after* this one finishes. Not the
                # next in the seat: the Capitol's balloon position runs Hot Air,
                # Observation, then Hot Air again, so ordering by first sighting
                # puts the one that ends last in the middle.
                later = [spans[(building, n, other)][0] for other in seat
                         if spans[(building, n, other)][0] > ends]
                if later:
                    if min(later) > ends + 1:
                        gaps[db] = min(later) - 1
                elif ends < last_epoch[building]:
                    gaps[db] = NEVER

    lines += [
        "}",
        "",
        "# unit -> the epoch it has to stay buildable through, because nothing",
        "# takes its menu position until then. 15 means nothing ever does. See",
        "# the note in this file's generator; without it the check closes and",
        "# logic never knows.",
        "SLOT_GAPS: dict[str, int] = {",
    ]
    for db in sorted(gaps):
        lines.append(f"    {db!r}: {gaps[db]},")
    # The epoch each unit is first drawn in, anywhere.
    #
    # `dbobjects.dat` is the usual source for a unit's floor and it reads low
    # for three: the Sea King II, Khan Sun Do and Hu Kwan Do are all stored an
    # epoch before the menu offers them. Low is the dangerous direction — logic
    # believes a check is reachable before it is — and it cost a seed, with
    # `Epoch: Nano Age` sitting on a Sea King II you need the Nano Age to build.
    first_epoch = {}
    for (building, n, db), (start, _end) in spans.items():
        first_epoch[db] = min(first_epoch.get(db, 99), start)

    lines += [
        "}",
        "",
        "# unit -> the earliest epoch any menu draws it. `Locations` takes this",
        "# against the database's own figure and keeps the later one.",
        "SLOT_FIRST_EPOCH: dict[str, int] = {",
    ]
    for db in sorted(first_epoch):
        lines.append(f"    {db!r}: {first_epoch[db]},")
    lines += [
        "}",
        "",
        "# unit -> every unit that held its slot before it, so the current",
        "# occupant sends all of their checks.",
        "SLOT_PREDECESSORS: dict[str, tuple[str, ...]] = {",
        "    unit: tuple(seat[:i])",
        "    for seats in UNIT_SLOTS.values()",
        "    for seat in seats",
        "    for i, unit in enumerate(seat)",
        "    if i",
        "}",
        "",
    ]
    with open(OUT, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n{len(gaps)} slot gap(s) recorded")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
