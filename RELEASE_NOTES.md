First release. Empire Earth: The Art of Conquest in an Archipelago multiworld. Needs Archipelago 0.6.7 or newer

### Added

- 370 checks: 14 epochs, 25 building types, 231 units, 100 technologies.
- `Epoch:` items replace the two-building requirement to advance.
- Building and wonder unlocks, an option each. A locked building leaves your build menu until its item arrives.
- Technology checks. Researching sends the check and opens the next tier of its chain; the benefit comes back as a `Tech:` item.
- Resource bundles for food, wood, stone, gold and iron.
- Wonder and epoch goals.
- Client for GOG and Steam Art of Conquest.

### Known issues/warnings

- Your antivirus may quarantine Archipelago. Delivering an item means writing code into the running game, which looks exactly like an injector to a behavioural scanner. Restore the files and add an exclusion for the Archipelago folder — see the README for what it actually does and which options reduce it.
- On Steam, start the Archipelago Launcher as administrator before the game, or it can't open an elevated process.
- `map_terrain` is you telling the seed which map you'll play. Nothing actually enforces said map type.
- 214 unit epochs are pinned to the epoch a vanilla build menu draws them in. The rest come from `dbobjects.dat`, which is all over the place, and there still might be one or two outliers that i missed (If you find any kind of issues relating Units please report to me on discord)
