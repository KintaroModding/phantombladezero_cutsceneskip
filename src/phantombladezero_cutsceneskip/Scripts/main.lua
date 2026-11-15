-- Cutscene Skip for Phantom Blade Zero.
--
-- Unlocks the game's own manual skip for story cutscenes: with the mod, holding the game's skip key (E on the keyboard,
-- B or Circle on a gamepad) fills the skip ring in most cutscenes and skips them. A few scenes do not support the skip.
--
-- How: the game has a switch that allows the manual skip of every sequence, the bool ForceSkipAllSequence of its
-- game-instance subsystem EventPipelineGameInstance. The mod sets it to true through the game's own setter
-- (SetForceSkipAllSequence) and checks it again every CHECK_MS on the game thread: when the game has reset it, the mod
-- sets it again. It sends nothing to the cutscenes themselves and presses no key: the skip stays the game's own.
--
-- The mod remembers the value the switch had when it first read it. With Enable = false it gives that value back, but
-- only when it wrote the switch itself and the switch is still true (another mod or the game may have changed it
-- since). The switch lives in memory only; nothing goes into the save.
--
-- The live subsystem comes from the game's own static getter GetGlobalBP, called on the class default object. After
-- MAX_FAILS failed checks in a row (a game update can remove one of these functions) the mod stops until the game
-- starts again, and the log says so.
--
-- Settings: the player edits Scripts\config.lua. The mod reads it at start and again every CONFIG_INTERVAL_MS, so a
-- change shows without a restart; a broken or half-saved file keeps the last settings. DEFAULTS holds every setting
-- with its default. A player (or a mod manager) keeps their config.lua across updates, so a new main.lua can meet an
-- older file: a setting that the file lacks, or has with another type, keeps its default, and the log says so. Read a
-- setting only from Settings, never as `config.X or default`: for a true/false setting, `false or true` is true.

local MOD_NAME = "Cutscene Skip"
local VERSION = "1.0"
local CHECK_MS = 500
local CONFIG_INTERVAL_MS = 5000
-- The class default object of the game's subsystem; its static getter GetGlobalBP gives the live subsystem.
local LIBRARY_PATH = "/Script/ProjectPBZ.Default__EventPipelineGameInstance"
local DEFAULT_PREFIX = "Default__"
-- After this many failed checks in a row the mod stops until the game starts again.
local MAX_FAILS = 20
-- Log at most this many error lines in total.
local MAX_ERROR_LOGS = 5
-- LogDetail: at most this many lines per game start.
local MAX_DETAIL_LOGS = 400

-- Every setting with its default; config.lua ships the same names and values (tests\test_main.py checks it).
local DEFAULTS = {
    Enable = true,
    LogDetail = false,
}

local errors = 0
local details = 0

local function Log(message)
    print(string.format("[%s] %s\n", MOD_NAME, message))
end

local function LogError(message)
    errors = errors + 1
    if errors <= MAX_ERROR_LOGS then
        Log(message)
    end
end

local Settings = {}

-- LogDetail lines; message is a function, so nothing is built while LogDetail is off.
local function Detail(message)
    if Settings.LogDetail and details < MAX_DETAIL_LOGS then
        details = details + 1
        Log(message())
    end
end

local function Valid(object)
    if object == nil then
        return false
    end
    local ok, valid = pcall(function()
        return object:IsValid()
    end)
    return ok and valid == true
end

---------------------------------------------------------------------------------------------------------------------
-- Settings
---------------------------------------------------------------------------------------------------------------------

local function CopyDefaults()
    local settings = {}
    for name, value in pairs(DEFAULTS) do
        settings[name] = value
    end
    return settings
end

-- One line for the log: every setting, sorted by name.
local function Describe(settings)
    local names = {}
    for name in pairs(settings) do
        names[#names + 1] = name
    end
    table.sort(names)
    local parts = {}
    for i, name in ipairs(names) do
        parts[i] = name .. "=" .. tostring(settings[name])
    end
    return table.concat(parts, ", ")
end

-- Lua's line number and reason, without the chunk name.
local function Reason(message)
    message = tostring(message)
    local line, reason = message:match("config%.lua:(%d+): ([^\n]*)")
    return line and ("line " .. line .. ": " .. reason) or (message:gsub("%s*\n%s*", " "))
end

-- DEFAULTS with the values of config.lua's text over them; nil and the reason when the text is not a usable file.
local function ParseConfig(text)
    local chunk, problem = load(text, "=config.lua", "t", {})
    if not chunk then
        return nil, "config.lua not read (" .. Reason(problem) .. ")"
    end
    local ok, config = pcall(chunk)
    if not ok then
        return nil, "config.lua not read (" .. Reason(config) .. ")"
    end
    if type(config) ~= "table" then
        return nil, "config.lua does not return a table"
    end
    local settings = CopyDefaults()
    for name, value in pairs(config) do
        local default = DEFAULTS[name]
        if default == nil then
            Log("config.lua: unknown setting " .. tostring(name) .. " ignored.")
        elseif type(value) ~= type(default) then
            Log(string.format("config.lua: %s must be a %s; the default %s is used.", name, type(default),
                tostring(default)))
        else
            settings[name] = value
        end
    end
    return settings
end

local configPath = nil
-- The text of the last read; false: no file at the last read; nil: not read yet.
local configText = nil

-- Reads config.lua when its text changed since the last read. At start, a missing or broken file means the defaults;
-- later, a broken file keeps the last settings (a half-saved file), and a missing one means the defaults.
local function ReadConfig()
    local atStart = configText == nil
    configPath = configPath or package.searchpath("config", package.path)
    local text = false
    if configPath then
        local file = io.open(configPath, "rb")
        if file then
            text = file:read("a") or false
            file:close()
        end
    end
    if text == configText then
        return
    end
    configText = text
    local settings, problem
    if text == false then
        settings, problem = CopyDefaults(), nil
        Log("No config.lua; every setting uses its default.")
    else
        settings, problem = ParseConfig(text)
    end
    if not settings then
        if atStart then
            Log(problem .. "; every setting uses its default.")
            settings = CopyDefaults()
        else
            Log(problem .. "; the last settings stay.")
            return
        end
    end
    local line = Describe(settings)
    if atStart or line ~= Describe(Settings) then
        Log("Settings: " .. line)
    end
    Settings = settings
end

---------------------------------------------------------------------------------------------------------------------
-- The game's skip switch
---------------------------------------------------------------------------------------------------------------------

local library = nil     -- the class default object of the subsystem, kept while it is valid
local bound = nil       -- the live subsystem whose switch the mod reads and writes
local original = nil    -- the switch's value when the mod first read it on `bound`
local applied = false   -- the mod wrote true on `bound`, so the restore is its job
local status = nil      -- the state of the last check, to log each change once
local sets = 0
local fails = 0
local stopped = false

local STATUS_LINES = {
    ["on"] = "The game's cutscene skip is unlocked: in a cutscene, hold the skip key (E, or B / Circle on a gamepad) "
        .. "until the ring fills.",
    ["already on"] = "The game's cutscene skip was unlocked already (the game or another mod set the switch); the mod "
        .. "keeps it so.",
    ["off"] = "Enable = false: the mod changes nothing; the game's own skip rule applies.",
    ["no class"] = "Waiting: the game's class EventPipelineGameInstance is not there (yet).",
    ["no instance"] = "Waiting for the game to start up (its instance is not there yet).",
}

-- Logs the state when it changed since the last check.
local function Report(state)
    if state ~= status then
        status = state
        Log(STATUS_LINES[state])
    end
end

-- The live subsystem; nil and the reason ("no class", "no instance") while the game does not have it.
local function Current()
    if not Valid(library) then
        library = StaticFindObject(LIBRARY_PATH)
        if not Valid(library) then
            library = nil
            return nil, "no class"
        end
    end
    local instance = library:GetGlobalBP()
    if not Valid(instance) then
        return nil, "no instance"
    end
    -- A class default object is not the live subsystem.
    if instance:GetFName():ToString():sub(1, #DEFAULT_PREFIX) == DEFAULT_PREFIX then
        return nil, "no instance"
    end
    return instance
end

local function GetSwitch(instance)
    return instance:GetForceSkipAllSequence()
end

local function SetSwitch(instance, value)
    instance:SetForceSkipAllSequence(value)
end

-- Gives the switch its first value back and lets go of the subsystem. It writes only when the mod wrote before and
-- the switch is still true: another mod or the game may have changed it since. A restore that the game does not take
-- is an error, and the next check tries it again.
local function Release()
    if applied and Valid(bound) and GetSwitch(bound) == true then
        SetSwitch(bound, original)
        if GetSwitch(bound) ~= original then
            error("the game did not take the switch's old value back", 0)
        end
        Detail(function() return "the switch has its old value again (" .. tostring(original) .. ")" end)
    end
    bound, original, applied = nil, nil, false
end

-- One check: the switch is true while Enable is true, and has its old value while it is false.
local function Check()
    if not Settings.Enable then
        Release()
        Report("off")
        return
    end
    local current, reason = Current()
    if not current then
        Release()
        Report(reason)
        return
    end
    if bound and (not Valid(bound) or bound:GetAddress() ~= current:GetAddress()) then
        Release()
    end
    if not bound then
        local first = GetSwitch(current)
        if type(first) ~= "boolean" then
            error("GetForceSkipAllSequence gave " .. tostring(first) .. ", not true or false", 0)
        end
        bound, original = current, first
    end
    -- Also when the game reset the switch after the mod set it.
    if GetSwitch(bound) ~= true then
        -- Before the call: the restore stays the mod's job when the call fails halfway.
        applied = true
        SetSwitch(bound, true)
        sets = sets + 1
        Detail(function() return "the switch was not true: set (" .. sets .. " so far)" end)
    end
    if GetSwitch(bound) ~= true then
        error("the game did not take the skip switch", 0)
    end
    Report(applied and "on" or "already on")
end

---------------------------------------------------------------------------------------------------------------------
-- Start
---------------------------------------------------------------------------------------------------------------------

Settings = CopyDefaults()
Log(VERSION .. " loaded.")
local read, problem = pcall(ReadConfig)
if not read then
    LogError("Error while reading config.lua: " .. tostring(problem))
end

local function Step()
    if stopped then
        return
    end
    local ok, err = pcall(Check)
    if ok then
        fails = 0
        return
    end
    fails = fails + 1
    LogError("Error: " .. tostring(err))
    if fails >= MAX_FAILS then
        stopped = true
        Log(MAX_FAILS .. " checks in a row failed: the mod stops until the game starts again. A game update may need a "
            .. "new version of the mod.")
    end
end

local function ConfigStep()
    local ok, err = pcall(ReadConfig)
    if not ok then
        LogError("Error while reading config.lua: " .. tostring(err))
    end
end

-- Both loops run on the game thread (UE4SS's Delayed Action API): no Lua on a second thread (Witch Time's crash
-- lesson). A UE4SS without it gets the old LoopAsync loops, and the log says so.
if type(LoopInGameThreadWithDelay) == "function" then
    LoopInGameThreadWithDelay(CHECK_MS, Step)
    LoopInGameThreadWithDelay(CONFIG_INTERVAL_MS, ConfigStep)
else
    Log("This UE4SS has no game-thread loops (LoopInGameThreadWithDelay): the older LoopAsync is used; a newer UE4SS "
        .. "is safer.")
    LoopAsync(CHECK_MS, function()
        ExecuteInGameThread(Step)
        -- false keeps the loop running.
        return false
    end)
    LoopAsync(CONFIG_INTERVAL_MS, function()
        ExecuteInGameThread(ConfigStep)
        return false
    end)
end
