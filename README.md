# Cutscene Skip

Unlocks the game's own manual skip for most story cutscenes: hold E (gamepad B or Circle) until the skip ring fills. A few scenes still cannot be skipped. Enable in config.lua turns it on or off, live in game.

A [UE4SS](https://github.com/UE4SS-RE/RE-UE4SS) Lua mod for Phantom Blade Zero (Unreal Engine 5.7), made with
game version `CL-302256_JKS-17280` and UE4SS `v3.0.1-1195-g1ceefac8`. This README is for developers; what the mod does and
how to install it are in [openmods.md](openmods.md), the mod page on [openmods](https://openmods.nexus).

## How it works

The game has a switch that allows the manual skip of every sequence: the bool `ForceSkipAllSequence` of its
game-instance subsystem `EventPipelineGameInstance`. With the switch true, holding the game's skip key (E, or B /
Circle on a gamepad) fills the skip ring in most story cutscenes. `Scripts/main.lua` sets the switch to true through
the game's own setter and checks it every 0.5 seconds on the game thread; when the game has reset it, the mod sets it
again. It sends nothing to the cutscenes and presses no key.

Every 0.5 seconds (`Check`):

1. The live subsystem comes from the game's static getter: `GetGlobalBP()`, called on the class default object
   `/Script/ProjectPBZ.Default__EventPipelineGameInstance` (kept while it is valid). No object, or a class default
   object, means that the game is not ready: the mod waits.
2. At the first sight of a subsystem the mod remembers the switch's value (`GetForceSkipAllSequence()`).
3. When the switch is not true, it calls `SetForceSkipAllSequence(true)` and reads the switch again; a switch that
   did not take the value is an error.

With `Enable = false`, or when the game has a new subsystem, the mod gives the old subsystem's switch its first value
back (`Release`): only when the mod wrote it, and only while it is still true, because the game or another mod may
have changed it since. The switch lives in memory only; nothing goes into the save.

After 20 failed checks in a row (a game update can remove one of these functions) the mod stops until the game starts
again; the log has at most 5 error lines and one line for the stop.

## Deploy and test

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy.ps1     # copy the mod folder into the game's ue4ss\Mods
python tests\test_main.py                                 # offline test of main.lua (needs lupa)
```

`deploy.ps1` copies `src\phantombladezero_cutsceneskip\` to `<game folder>\platform\steam\ue4ss\Mods\phantombladezero_cutsceneskip\`. The game
folder is `$env:UE5_GAMES_DIR\PBZ`; `-GameDir` or `-ModsDir` override it. The mod folder holds
`enabled.txt`, so UE4SS starts it without an entry in `mods.txt`. An existing `Scripts\config.lua` in the game stays
(the tester's settings); `-ResetConfig` copies the shipped one. UE4SS loads Lua mods at game start. The mod writes
its lines into `ue4ss\UE4SS.log`, for example `[Cutscene Skip] 1.0 loaded.`

`tests\test_main.py` runs `main.lua` in Lua 5.4 ([lupa](https://pypi.org/project/lupa/)) with mocks of the UE4SS
functions that the script uses. It finds syntax and logic errors before a game start.

Versioning: every change raises the second number (1.0 -> 1.1) in `mod.json` and in `main.lua`:
`python scripts\bump_version.py`.

## Settings

`Scripts/config.lua` holds the player's settings (`Enable`, `LogDetail`), `DEFAULTS` in `main.lua` every setting with
its default. The mod reads the file at start and again every 5 seconds (`ReadConfig`): a changed file applies at the
next check, a broken or half-saved one keeps the last settings, a missing one means the defaults. Players and mod
managers keep their own `config.lua` across updates, so a new `main.lua` can meet an older file: a setting that the
file lacks, or has with another type, keeps its default, and the log says so (`ParseConfig`). Add each setting to
both files with the same value, and read it only from `Settings`, never as `config.X or default` (for a true/false
setting, `false or true` is true). `tests\test_main.py` checks that `config.lua` ships exactly the defaults, and runs
`main.lua` with a missing, empty, broken and wrong `config.lua`.

## Project layout

```
src/phantombladezero_cutsceneskip/   The UE4SS mod folder: Scripts/main.lua, Scripts/config.lua, enabled.txt
tests/test_main.py    Offline test of main.lua with mocks of UE4SS and the game
docs/                 Cover and screenshots
scripts/              bump_version.py
deploy.ps1            Copies the mod folder into the game's ue4ss\Mods
mod.json              Name, version, game, engine and UE4SS version
```

## License

MIT, see [LICENSE](LICENSE).
