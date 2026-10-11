"""Hold Archipelago's connect handshake open, to test the connect race.

`Connected` sets `ctx.slot` at the top, awaits a send in the middle and only
assigns `missing_locations` at the bottom. Between those the client looks
connected and knows no locations, and a check that is already true the moment a
match loads — `Build Capitol`, `Recruit Citizen`, `Recruit Female Citizen` —
gets asked about in that window. Reported by a player who was last to start in a
group, where a busier room widens the gap; solo it is far too small to land in.

This drops a sleep into that gap so it is seconds wide instead of microseconds,
which makes the bug reproducible on demand.

    py tools\\race_probe.py --on      widen the window
    py tools\\race_probe.py --off     put it back
    py tools\\race_probe.py           report which it is

Edits your Archipelago *source checkout*, not the frozen install, and only the
one line. Generation never runs this handler, so a seed built while it is on is
unaffected.
"""

from __future__ import annotations

import argparse
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from test_generation import AP_SOURCE                       # noqa: E402

TARGET = os.path.join(AP_SOURCE, "CommonClient.py")

ANCHOR = '        ctx.missing_locations = set(args["missing_locations"])'
PATCH = ("        import asyncio as _race_probe_asyncio  # race_probe\n"
         "        await _race_probe_asyncio.sleep(5)  # race_probe\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--on", action="store_true")
    ap.add_argument("--off", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(TARGET):
        sys.exit(f"no Archipelago checkout at {AP_SOURCE}")

    s = io.open(TARGET, encoding="utf-8").read()
    on = "# race_probe" in s

    if not (args.on or args.off):
        print(f"{TARGET}\nrace window: {'WIDE (5s)' if on else 'normal'}")
        return

    if args.on:
        if on:
            print("already on")
            return
        if ANCHOR not in s:
            sys.exit("the anchor line moved; check the Connected handler")
        s = s.replace(ANCHOR, PATCH + ANCHOR, 1)
    else:
        if not on:
            print("already off")
            return
        s = "".join(l for l in s.splitlines(keepends=True)
                    if "# race_probe" not in l)

    io.open(TARGET, "w", encoding="utf-8", newline="\n").write(s)
    print(f"race window: {'WIDE (5s)' if args.on else 'normal'}")


if __name__ == "__main__":
    main()
