"""Offline test of Scripts/main.lua with lupa (Lua 5.4) and small mocks of UE4SS and the game.

The mocks stand in for the UE4SS functions that the script uses (the game-thread loops LoopInGameThreadWithDelay, the
old LoopAsync, ExecuteInGameThread, StaticFindObject) and for the game: the class default object of the subsystem
EventPipelineGameInstance with its static getter GetGlobalBP, and the live subsystem with the skip switch
(GetForceSkipAllSequence, SetForceSkipAllSequence). The mocks count the calls; READ_ONLY makes the setter do nothing,
and a getter or GetGlobalBP can be taken away, as after a game update.

CHECK(n) runs the mod's check n times (the 500 ms loop), CONFIG() the config read (the 5 s loop).

The checks: the loops; the switch set once, kept, and set again after the game reset it; Enable = false live and what
the mod gives back (only what it wrote, only while the switch is still true); the waiting states (no class, no
instance, a class default object) and a new instance; the failures (a setter that does not take, a missing function)
with the limit on error lines and the stop after 20 failed checks; LogDetail. Then the settings files a player may
have instead of the shipped config.lua: main.lua must start, and every setting the file does not give keeps its
default; the shipped config.lua must hold exactly the defaults of main.lua.

Usage:
    python tests/test_main.py        (needs lupa: python -m pip install lupa)

Exit code: 0 = all checks passed, 1 = a check failed.
"""

import json
import sys
import tempfile
from pathlib import Path

from lupa import lua54

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "src" / "phantombladezero_cutsceneskip" / "Scripts" / "main.lua"
CONFIG = MAIN.parent / "config.lua"

MOCKS = r"""
LOG = {}
print = function(...) LOG[#LOG + 1] = table.concat({...}, "") end

LOOPS = {}
DELAYS = {}
ASYNC_LOOPS = 0
function LoopInGameThreadWithDelay(ms, callback) LOOPS[#LOOPS + 1] = callback DELAYS[#DELAYS + 1] = ms return #LOOPS end
function LoopAsync(ms, callback) ASYNC_LOOPS = ASYNC_LOOPS + 1 LOOPS[#LOOPS + 1] = callback DELAYS[#DELAYS + 1] = ms end
function ExecuteInGameThread(callback) callback() end
function RUN(ms) for i = 1, #LOOPS do if DELAYS[i] == ms then LOOPS[i]() end end end
function CHECK(times) for _ = 1, times or 1 do RUN(500) end end
function CONFIG() RUN(5000) end

-- Game objects: each has its own address and a name.
local nextAddress = 0x1000
local ObjectMeta = {}
ObjectMeta.__index = {
    IsValid = function(self) return self.valid ~= false end,
    GetAddress = function(self) return self.address end,
    GetFName = function(self) return { ToString = function() return self.name end } end,
}
function Object(fields)
    fields = fields or {}
    nextAddress = nextAddress + 0x100
    fields.address = nextAddress
    return setmetatable(fields, ObjectMeta)
end

-- The live subsystem with its skip switch. READ_ONLY: the setter does nothing.
GETS, SETS = 0, 0
READ_ONLY = false
function Subsystem(flag, name)
    return Object({
        name = name or "EventPipelineGameInstance_2147482593",
        flag = flag,
        GetForceSkipAllSequence = function(self) GETS = GETS + 1 return self.flag end,
        SetForceSkipAllSequence = function(self, value) SETS = SETS + 1 if not READ_ONLY then self.flag = value end end,
    })
end
INSTANCE = Subsystem(false)
-- What the game's GetGlobalBP gives: the live subsystem, nil, or what a test puts here.
CURRENT = INSTANCE
GLOBAL_CALLS = 0
LIBRARY_PATH = "/Script/ProjectPBZ.Default__EventPipelineGameInstance"
function Library()
    return Object({ name = "Default__EventPipelineGameInstance",
        GetGlobalBP = function(self) GLOBAL_CALLS = GLOBAL_CALLS + 1 return CURRENT end })
end
LIBRARY = Library()
OBJECTS = { [LIBRARY_PATH] = LIBRARY }
FINDS = 0
function StaticFindObject(path) FINDS = FINDS + 1 return OBJECTS[path] or Object({ valid = false }) end

function DESCRIBE(t)
    local names = {}
    for name in pairs(t) do names[#names + 1] = tostring(name) end
    table.sort(names)
    local parts = {}
    for i, name in ipairs(names) do parts[i] = name .. "=" .. tostring(t[name]) end
    return table.concat(parts, ", ")
end
"""

UNLOCKED = "The game's cutscene skip is unlocked: in a cutscene, hold the skip key"
ALREADY = "The game's cutscene skip was unlocked already"
OFF = "Enable = false: the mod changes nothing; the game's own skip rule applies."
NO_CLASS = "Waiting: the game's class EventPipelineGameInstance is not there (yet)."
NO_INSTANCE = "Waiting for the game to start up (its instance is not there yet)."

PLAYER_CONFIGS = [
    ("no config.lua", None, "No config.lua"),
    ("an empty or older config.lua", "return {}\n", None),
    ("a broken config.lua", "return {\n    Enable =\n", "config.lua not read"),
    ("a config.lua without a table", "-- nothing here\n", "does not return a table"),
    ("a config.lua with wrong types", "wrong types", "must be a"),
    ("a config.lua with an unknown setting", "return { NoSuchSetting = 1 }\n", "unknown setting NoSuchSetting"),
]


def lua_path(path: Path) -> str:
    return "[[" + path.as_posix() + "]]"


class Run:
    """main.lua in a fresh Lua state, with config.lua read from config_folder; before: Lua run before main.lua."""

    def __init__(self, config_folder: Path, before: str = ""):
        self.folder = config_folder
        self.lua = lua54.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(MOCKS)
        self.lua.execute(f'package.path = {lua_path(config_folder)} .. "/?.lua"; package.cpath = ""')
        if before:
            self.lua.execute(before)
        self.g = self.lua.globals()
        self.do(MAIN.read_text(encoding="utf-8"))

    def do(self, code: str):
        """Runs Lua code; a Lua error that stops it becomes an "Error" line in the log, so the checks fail."""
        try:
            return self.lua.execute(code)
        except lua54.LuaError as error:
            self.g.LOG[len(self.g.LOG) + 1] = "Error: main.lua stopped: " + str(error).splitlines()[0]

    def eval(self, expression: str):
        return self.lua.eval(expression)

    def log(self):
        return [self.g.LOG[i].rstrip() for i in range(1, len(self.g.LOG) + 1)]

    def count(self, text: str) -> int:
        return sum(text in line for line in self.log())

    def write_config(self, text: str):
        (self.folder / "config.lua").write_text(text, encoding="utf-8")


def settings_lines(log):
    return [line.split("] Settings: ", 1)[1] for line in log if "] Settings: " in line]


def main() -> None:
    version = json.loads((ROOT / "mod.json").read_text(encoding="utf-8"))["version"]
    failures = []

    def check(condition, text):
        print(("ok    " if condition else "FAIL  ") + text)
        if not condition:
            failures.append(text)

    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        shipped_text = CONFIG.read_text(encoding="utf-8")
        off_text = shipped_text.replace("Enable = true,", "Enable = false,")
        detail_text = shipped_text.replace("LogDetail = false,", "LogDetail = true, ")
        assert off_text != shipped_text and detail_text != shipped_text

        def folder(name, text=shipped_text):
            f = temp / name
            f.mkdir()
            if text is not None:
                (f / "config.lua").write_text(text, encoding="utf-8")
            return f

        # --- The mod as players get it.
        r = Run(folder("shipped"))
        e = r.eval
        log = r.log()
        check(list(r.g.DELAYS.values()) == [500, 5000] and r.g.ASYNC_LOOPS == 0,
              "game-thread loops: the check every 0.5 s, the config read every 5 s")
        check(any(f"{version} loaded." in line for line in log), f"load line with the version {version} of mod.json")
        shipped = e(f"DESCRIBE(dofile({lua_path(CONFIG)}))")
        check(settings_lines(log) == [shipped] and not any("config.lua" in line for line in log),
              "one settings line with the shipped values, no warning")
        check(e("SETS") == 0 and e("FINDS") == 0 and e("INSTANCE.flag") is False,
              "nothing is searched or written while main.lua loads")
        r.do("CHECK()")
        for line in r.log():
            print("      log: " + line)
        check(e("INSTANCE.flag") is True and e("SETS") == 1 and r.count(UNLOCKED) == 1,
              "the first check: the switch is set through the game's setter, one log line")
        r.do("CHECK(5)")
        check(e("SETS") == 1 and e("FINDS") == 1 and e("GLOBAL_CALLS") == 6 and r.count(UNLOCKED) == 1,
              "later checks: no new write, the class default object is kept, no new log line")
        r.do("INSTANCE.flag = false CHECK()")
        check(e("INSTANCE.flag") is True and e("SETS") == 2 and r.count(UNLOCKED) == 1,
              "the game reset the switch: the mod sets it again")

        # --- Enable, live.
        r.write_config(off_text)
        r.do("CONFIG() CHECK()")
        check(e("INSTANCE.flag") is False and e("SETS") == 3 and r.count(OFF) == 1
              and any("Enable=false" in line for line in settings_lines(r.log())),
              "Enable = false (live): the switch has its old value (false) again, one log line")
        r.do("CHECK(4)")
        check(e("SETS") == 3 and e("INSTANCE.flag") is False, "Enable = false: no more writes")
        r.write_config(shipped_text)
        r.do("CONFIG() CHECK()")
        check(e("INSTANCE.flag") is True and e("SETS") == 4 and r.count(UNLOCKED) == 2,
              "Enable = true again (live): the switch is set again")
        r.write_config("return {\n    Enable =\n")
        r.do("CONFIG() CHECK()")
        check(any("config.lua not read (line" in line and "the last settings stay" in line for line in r.log())
              and e("INSTANCE.flag") is True, "a broken (half-saved) file keeps the last settings")
        check(not any("Error" in line for line in r.log()), "no error line so far")

        # --- What the mod gives back.
        was = Run(folder("was"), "INSTANCE.flag = true")
        was.do("CHECK(3)")
        check(was.eval("SETS") == 0 and was.count(ALREADY) == 1 and was.count(UNLOCKED) == 0,
              "a switch that is true already: no write, its own log line")
        was.write_config(off_text)
        was.do("CONFIG() CHECK()")
        check(was.eval("SETS") == 0 and was.eval("INSTANCE.flag") is True,
              "Enable = false then: the switch stays true (the mod did not set it)")
        other = Run(folder("other"))
        other.do("CHECK() INSTANCE.flag = false")
        other.write_config(off_text)
        other.do("CONFIG() CHECK()")
        check(other.eval("SETS") == 1 and other.eval("INSTANCE.flag") is False,
              "the switch is no longer true at Enable = false: no write (another mod changed it)")
        late = Run(folder("late"), "INSTANCE.flag = true")
        late.do("CHECK() INSTANCE.flag = false CHECK()")
        check(late.eval("SETS") == 1 and late.eval("INSTANCE.flag") is True and late.count(UNLOCKED) == 1,
              "true at first, reset by the game later: the mod sets it")
        late.write_config(off_text)
        late.do("CONFIG() CHECK()")
        check(late.eval("INSTANCE.flag") is True and late.eval("SETS") == 2,
              "Enable = false then: it gets the first value back, which was true")

        # --- Waiting for the game, and a new instance.
        noclass = Run(folder("noclass"), "OBJECTS = {}")
        noclass.do("CHECK(4)")
        check(noclass.count(NO_CLASS) == 1 and noclass.eval("FINDS") == 4 and noclass.eval("SETS") == 0
              and not any("Error" in line for line in noclass.log()),
              "the class is not there: one waiting line, a lookup per check, no error")
        noclass.do("OBJECTS[LIBRARY_PATH] = LIBRARY CHECK()")
        check(noclass.eval("INSTANCE.flag") is True and noclass.count(UNLOCKED) == 1, "the class is there later: set")
        for case, before in [("nil", "CURRENT = nil"), ("an invalid object", "CURRENT = Object({ valid = false })"),
                             ("a class default object", "CDO = Subsystem(false, 'Default__EventPipelineGameInstance') "
                                                        "CURRENT = CDO")]:
            wait = Run(folder("wait" + str(len(case))), before)
            wait.do("CHECK(4)")
            fine = (wait.count(NO_INSTANCE) == 1 and wait.eval("SETS") == 0 and wait.eval("GETS") == 0
                    and not any("Error" in line for line in wait.log()))
            wait.do("CURRENT = INSTANCE CHECK()")
            check(fine and wait.eval("INSTANCE.flag") is True and wait.count(UNLOCKED) == 1,
                  f"GetGlobalBP gives {case}: one waiting line, nothing read or written; the live one later: set")
        new = Run(folder("new"))
        new.do("CHECK() NEW = Subsystem(false, 'EventPipelineGameInstance_2147480000') CURRENT = NEW CHECK()")
        check(new.eval("INSTANCE.flag") is False and new.eval("NEW.flag") is True and new.eval("SETS") == 3,
              "a new instance: the old one gets its value back, the new one is set")
        gone = Run(folder("gone"))
        gone.do("CHECK() INSTANCE.valid = false NEW = Subsystem(false) CURRENT = NEW CHECK()")
        check(gone.eval("INSTANCE.flag") is True and gone.eval("NEW.flag") is True and gone.eval("SETS") == 2,
              "a new instance after the old one is gone: no call on the old one")
        lost = Run(folder("lost"))
        lost.do("CHECK() CURRENT = nil CHECK()")
        check(lost.eval("INSTANCE.flag") is False and lost.count(NO_INSTANCE) == 1,
              "the game has no instance any more: the kept one gets its value back, a waiting line")
        relook = Run(folder("relook"))
        relook.do("CHECK() LIBRARY.valid = false OBJECTS[LIBRARY_PATH] = Library() CHECK(2)")
        check(relook.eval("FINDS") == 2 and relook.eval("INSTANCE.flag") is True
              and not any("Error" in line for line in relook.log()),
              "the class default object is gone: looked up again, once")

        # --- Failures.
        stuck = Run(folder("stuck"), "READ_ONLY = true")
        stuck.do("CHECK(19)")
        check(stuck.count("Error: the game did not take the skip switch") == 5 and stuck.count("the mod stops") == 0,
              "a setter that does not take: an error per check, at most 5 lines; 19 failed checks: still running")
        stuck.do("CHECK()")
        gets = stuck.eval("GETS")
        stuck.do("READ_ONLY = false CHECK(5)")
        check(stuck.count("20 checks in a row failed: the mod stops until the game starts again") == 1
              and stuck.eval("GETS") == gets and stuck.eval("INSTANCE.flag") is False,
              "20 failed checks in a row: one line, then no more calls")
        reset = Run(folder("reset"), "READ_ONLY = true")
        reset.do("CHECK(19) READ_ONLY = false CHECK() READ_ONLY = true INSTANCE.flag = false CHECK(19)")
        check(reset.count("the mod stops") == 0, "a good check between 19 and 19 failed ones: the count starts again")
        reset.do("READ_ONLY = false CHECK()")
        check(reset.eval("INSTANCE.flag") is True, "and the mod still works")
        nogetter = Run(folder("nogetter"), "INSTANCE.GetForceSkipAllSequence = function() return nil end")
        nogetter.do("CHECK()")
        check(nogetter.count("Error: GetForceSkipAllSequence gave nil, not true or false") == 1
              and nogetter.eval("SETS") == 0, "a getter that gives no true or false: an error, no write")
        noglobal = Run(folder("noglobal"), "LIBRARY.GetGlobalBP = nil")
        noglobal.do("CHECK(25)")
        check(noglobal.count("Error: ") == 5 and noglobal.count("the mod stops") == 1 and noglobal.eval("SETS") == 0,
              "a game without GetGlobalBP: 5 error lines, the stop line, no write")
        norestore = Run(folder("norestore"))
        norestore.do("CHECK() READ_ONLY = true")
        norestore.write_config(off_text)
        norestore.do("CONFIG() CHECK(2)")
        check(norestore.count("Error: the game did not take the switch's old value back") == 2
              and norestore.eval("INSTANCE.flag") is True, "a restore that does not take: an error at each check")
        norestore.do("READ_ONLY = false CHECK()")
        check(norestore.eval("INSTANCE.flag") is False and norestore.count(OFF) == 1,
              "the restore takes at a later check: the old value is back")

        # --- LogDetail.
        d = Run(folder("detail", detail_text))
        d.do("CHECK() INSTANCE.flag = false CHECK()")
        d.write_config(detail_text.replace("Enable = true,", "Enable = false,"))
        d.do("CONFIG() CHECK()")
        log = d.log()
        for line in log[-5:]:
            print("      log: " + line)
        check(d.count("the switch was not true: set (1 so far)") == 1
              and d.count("the switch was not true: set (2 so far)") == 1
              and d.count("the switch has its old value again (false)") == 1
              and not any("Error" in line for line in log), "LogDetail: each write and the restore")
        check(r.count("so far") == 0, "LogDetail = false: no such lines")

        # --- A UE4SS without the game-thread loops.
        old = Run(folder("old"), "LoopInGameThreadWithDelay = nil")
        old.do("CHECK()")
        check(old.eval("ASYNC_LOOPS") == 2 and old.count("no game-thread loops") == 1
              and old.eval("INSTANCE.flag") is True, "a UE4SS without game-thread loops: LoopAsync, and a log line")

        # --- The settings files a player may have.
        folders = {}
        for case, content, _ in PLAYER_CONFIGS:
            if content == "wrong types":
                content = r.eval(f"""(function()
                    local lines = {{}}
                    for name, value in pairs(dofile({lua_path(CONFIG)})) do
                        lines[#lines + 1] = string.format("    [%q] = %s,", name, type(value) == "string" and "0" or '"wrong"')
                    end
                    return "return {{\\n" .. table.concat(lines, "\\n") .. "\\n}}\\n"
                end)()""")
            folders[case] = folder(f"player{len(folders)}", content)
        defaults = settings_lines(Run(folders["an empty or older config.lua"]).log())
        check(defaults == [shipped], f"config.lua ships exactly the defaults of main.lua ({defaults})")
        count = len(list(r.eval(f"dofile({lua_path(CONFIG)})").keys()))
        for case, _, expected in PLAYER_CONFIGS:
            run = Run(folders[case])
            run.do("CHECK() CONFIG()")
            log = run.log()
            fine = (settings_lines(log) == defaults and len(run.g.LOOPS) == 2 and run.eval("INSTANCE.flag") is True
                    and not any("Error" in line for line in log))
            if expected is None:
                fine = fine and not any("config.lua" in line for line in log)
            else:
                fine = fine and sum(expected in line for line in log) == (count if case.endswith("wrong types") else 1)
            check(fine, f"{case}: starts with the defaults and unlocks the skip"
                  + (f", logs '{expected}' once per setting" if case.endswith("wrong types")
                     else (f", logs '{expected}' once" if expected else ", no warning")))
            if not fine:
                for line in log:
                    print("      log: " + line)
        off = Run(folder("off", "return { Enable = false }\n"))
        off.do("CHECK(3)")
        check(len(off.g.LOOPS) == 2 and off.eval("SETS") == 0 and off.eval("GETS") == 0 and off.eval("FINDS") == 0
              and off.count(OFF) == 1,
              "Enable = false at start: the loops run (live settings), nothing is searched, read or written")
        off.write_config(shipped_text)
        off.do("CONFIG() CHECK()")
        check(off.eval("INSTANCE.flag") is True and off.count(UNLOCKED) == 1,
              "Enable = true later (live): the switch is set")

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
