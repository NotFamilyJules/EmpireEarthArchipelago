"""Write TechUnlocks.py: which technology a technology's effect makes available.

A technology's effect set is not only stat changes. For the chained ones it also
opens the next tier, and `technology_checks` withholds that effect until the
`Tech:` item arrives — so researching Ancestor Worship no longer reveals
Monotheism. Logic has to know, or it hides an item behind a check that item is
needed to reach. That shipped: `Epoch: Dark Age` on `Build Fortress`,
`Building: Fortress` on `Research Monotheism`, and Monotheism behind a
`Tech: Ancestor Worship` locked in the Atomic Age.

Read, not measured. Granting each effect and watching which button appeared was
the first attempt and it under-reports badly: an effect only opens a node once,
so whichever technology happens to be granted first takes the credit and every
other route to that node is invisible. It also can't see past the current
epoch, because a node above it reads unavailable whatever its chain does.

    py tools\\gen_tech_unlocks.py            # report
    py tools\\gen_tech_unlocks.py --write    # rewrite TechUnlocks.py

Run it with Empire Earth open, in a match. Nothing is written to the game — the
match is only there to resolve each technology's effect set from its node.

## The tables

`0x005CA76C` applies an effect set. It indexes a table at `0x0095CF80` by set
id, stride 16, taking a pointer to an array of record indices at `+0x04` and
their count at `+0x08`, then dispatches each through `0x005CA7CF`.

Records live at `0x00931FF8`, stride `0x58`. `+0x20` is the type, 1 to 22, and
the dispatcher jumps through a table at `0x005CA918` indexed by a byte table at
`0x005CA94C`.

Type 8 is the one that matters, and `+0x28` is its payload:

    0x005CB92B   ecx = player + 0x9CC, the tech tree
                 call 0x005CCE4C(tree)([rec+0x28], own id)
    0x005CCE4C   epoch = [rec+0x28] / 1000 - 1
                 ecx = tree + 8 + epoch * 0x54, the epoch record
                 call 0x005CE738(epoch)([rec+0x28], own id)
    0x005CE738   look [rec+0x28] up in the epoch's map at +0x24
                 call 0x005CF995 on what it finds

So `[rec+0x28]` is the id of the thing being opened, and the epoch it lives in
falls out of the id — 4060 is Monotheism, 4060/1000-1 = 3, the Bronze Age.

Ids that name no technology are units and buildings, which the wall and tower
line opens alongside its next tier. Those need no rule: their own checks carry
the epoch and producer requirements already.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "world", "empire_earth"))

from Memory import attach                                       # noqa: E402
from Addresses import profile_for, ResourceAccess               # noqa: E402
from Epochs import EpochAccess                                  # noqa: E402
from Roster import Roster                                       # noqa: E402
from BuildingGate import (NODE_VTABLE, NODE_SIZE, NODE_TREE,     # noqa: E402
                          NODE_BUTTON, NODE_EPOCH, BUTTON_TEXTURE)
from Technologies import TECHNOLOGIES                            # noqa: E402

OUT = os.path.join(ROOT, "world", "empire_earth", "TechUnlocks.py")
EXE_NAMES = ("EE-AOC.exe", "ee-aoc.exe")

SET_TABLE = 0x0095CF80       # effect set id -> entry array, stride 16
SET_ARRAY = 0x04
SET_COUNT = 0x08
SET_MAX = 0x5DC              # the applier's own bound

REC_TABLE = 0x00931FF8       # effect record, stride 0x58
REC_STRIDE = 0x58
REC_TYPE = 0x20
REC_TARGET = 0x28
REC_MAX = 0x7D0              # the dispatcher's own bound

TYPE_UNLOCK = 8

NODE_STATE = 0x08            # -> the node's state object
STATE_EFFECT_SET = 0x50


def local_nodes(proc, roster, tree):
    """(icon, node epoch) -> address, for the local player's tree."""
    nodes = {}
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
            stem = texture.split("\\")[-1].lower()
            if stem.endswith(".sst"):
                stem = stem[:-4]
            key = (stem, struct.unpack_from("<i", data, off + NODE_EPOCH)[0])
            nodes.setdefault(key, base + off)
    return nodes


def unlock_targets(proc, effect_set: int) -> list[int]:
    """Every id this effect set makes available."""
    if effect_set is None or not 0 <= effect_set <= SET_MAX:
        return []
    row = SET_TABLE + effect_set * 16
    array = proc.read_u32(row + SET_ARRAY)
    count = proc.read_u32(row + SET_COUNT)
    if not array or not count:
        return []
    out = []
    for i in range(count):
        index = proc.read_u32(array + i * 4)
        if index is None or index >= REC_MAX:
            continue
        record = REC_TABLE + index * REC_STRIDE
        if proc.read_u32(record + REC_TYPE) != TYPE_UNLOCK:
            continue
        target = proc.read_u32(record + REC_TARGET)
        if target:
            out.append(target)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="rewrite TechUnlocks.py")
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
        sys.exit("not in a match; this needs a tech tree to read effect sets from")

    nodes = local_nodes(proc, Roster(proc, profile), tree)
    by_id = {entry[4]: name for name, entry in TECHNOLOGIES.items()}

    unlocks: dict[str, list[str]] = {}
    missing, other = [], 0
    for name, (_e, _b, texture, node_epoch, _i) in sorted(TECHNOLOGIES.items()):
        node = nodes.get((texture, node_epoch))
        if not node:
            missing.append(name)
            continue
        state = proc.read_u32(node + NODE_STATE)
        effect_set = proc.read_u32(state + STATE_EFFECT_SET) if state else None
        named = []
        for target in unlock_targets(proc, effect_set):
            hit = by_id.get(target)
            if hit:
                named.append(hit)
            else:
                other += 1
        if named:
            unlocks[name] = sorted(set(named))

    for name in sorted(unlocks):
        print(f"  {name:34s} -> {', '.join(unlocks[name])}")
    print(f"\n{len(unlocks)} of {len(TECHNOLOGIES)} technologies open another")
    print(f"{other} unlock a unit or building instead, which needs no rule")
    if missing:
        print(f"no node found for: {', '.join(missing)}")

    opened = [t for v in unlocks.values() for t in v]
    if len(opened) != len(set(opened)):
        dupes = sorted({t for t in opened if opened.count(t) > 1})
        print(f"\nopened by more than one technology: {', '.join(dupes)}")

    if not args.write:
        print("\nnot written; pass --write")
        return

    lines = [
        '"""Which technology a technology\'s effect makes available.',
        "",
        "Generated by tools/gen_tech_unlocks.py from the running game's effect",
        "tables. Don't edit by hand.",
        "",
        "Researching a technology opens the next tier of its chain, and",
        "`technology_checks` withholds that effect until the `Tech:` item",
        "arrives — so the successor stays unavailable until then. A rule that",
        "doesn't know this hides an item behind a check you need that item to",
        "reach, which is how a run ended stuck in the Bronze Age with",
        "`Epoch: Dark Age` sitting on a Fortress it could not unlock.",
        "",
        "Read out of the game rather than guessed. The database says nothing",
        "about chains, and only the wall and tower line gives itself away, by",
        "sharing one icon across seven tiers.",
        '"""',
        "",
        "# technology -> the technologies its effect makes researchable",
        "TECH_UNLOCKS: dict[str, tuple[str, ...]] = {",
    ]
    for name in sorted(unlocks):
        inner = ", ".join(repr(v) for v in unlocks[name])
        lines.append(f"    {name!r}: ({inner},),")
    lines += [
        "}",
        "",
        "# The reverse: technology -> the technology whose `Tech:` item has to",
        "# arrive before its button exists.",
        "TECH_REQUIRES: dict[str, str] = {",
        "    later: earlier",
        "    for earlier, opened in TECH_UNLOCKS.items()",
        "    for later in opened",
        "}",
        "",
    ]
    with open(OUT, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
