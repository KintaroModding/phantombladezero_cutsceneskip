# Cutscene Skip

Unlocks the game's own cutscene skip: hold E (gamepad B or Circle) in a story cutscene until the skip ring fills. A few scenes still cannot be skipped.

## What it does

The game has its own skip for story cutscenes (hold the skip key), but most of them cannot be skipped. With this mod
most of them can.

- In a cutscene, hold **E** on the keyboard, or **B** / **Circle** on a gamepad, until the skip ring is full.
- It is the game's own skip: the same key and the same ring.
- Nothing is skipped by itself. A cutscene plays until you hold the key.
- `Enable = false` in `config.lua` brings the game's own rule back, live in game.

It is a UE4SS Lua script: it sets one switch of the game while the game runs. It replaces no game file and writes
nothing into your save.

## Screenshots

![Cutscene Skip](docs/cover.webp)

## How to install

1. Install UE4SS for Phantom Blade Zero, for example [UE4SS](https://github.com/KintaroModding/ue4ss) (its zip
   `phantombladezero_ue4ss_<version>.zip`: the official UE4SS build with a config that makes it run in this game).
2. Download the zip of the latest release on GitHub (`phantombladezero_cutsceneskip_<version>.zip`).
3. Unpack it into the game folder `platform\steam\`, next to the game's exe. It adds the folder
   `ue4ss\Mods\phantombladezero_cutsceneskip\` (with the file `enabled.txt`, UE4SS starts it by itself).
4. Start the game.

To check that it runs: `platform\steam\ue4ss\UE4SS.log` has the line `[Cutscene Skip] <version> loaded.`, and a few
seconds later `[Cutscene Skip] The game's cutscene skip is unlocked: ...`.

To update the mod, replace the folder with the one of the new release; to keep your settings, put your old
`Scripts\config.lua` back (a setting that it does not have keeps its default). To remove it, delete the folder
`ue4ss\Mods\phantombladezero_cutsceneskip\`; after the next game start the game's own rule is back.

## How to use

Nothing to set up. When a story cutscene plays, hold E (gamepad: B or Circle) until the skip ring is full.

## Settings

The settings are in `platform\steam\ue4ss\Mods\phantombladezero_cutsceneskip\Scripts\config.lua`. Open it with a
text editor, change a value and save: the mod reads the file every 5 seconds, so you see the change in the game
without a restart. A file it cannot read (for example a typo) keeps the last settings. `UE4SS.log` shows the settings
in use in the line `[Cutscene Skip] Settings: ...`, and names each value it could not use.

| Setting | Default | What it does |
|---|---|---|
| `Enable` | `true` | `false`: the game's own skip rule (most story cutscenes cannot be skipped) |
| `LogDetail` | `false` | `true`: `UE4SS.log` names each time the mod sets the game's skip switch (for tests) |

## Compatibility

- Game version: Steam build 26367565 (`CL-302256_JKS-17280`).
- Tested with UE4SS `v3.0.1-1195-g1ceefac8`.
- Another mod that unlocks the same skip (it sets the game's switch `ForceSkipAllSequence`) does the same job. Use one
  of them: while this mod is on, it sets the switch again within half a second after another mod turns it off.

## Known issues

- A few scenes do not support the game's skip.

## How to build

There is nothing to build: `src\phantombladezero_cutsceneskip\Scripts\main.lua` is the mod. `tests\test_main.py` runs the script
outside the game with Lua 5.4 ([lupa](https://pypi.org/project/lupa/)) and mocks of UE4SS:
`python tests\test_main.py`. `README.md` has the details.

## Credits

Made by Kintaro. MIT license: you may use, change and share this mod. UE4SS is made by the
[UE4SS-RE team](https://github.com/UE4SS-RE/RE-UE4SS). Phantom Blade Zero belongs to its makers.
