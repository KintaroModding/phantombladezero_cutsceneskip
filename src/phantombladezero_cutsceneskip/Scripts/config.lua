-- Settings of Cutscene Skip. Change a value and save the file: the mod reads it again every 5 seconds, so the change
-- shows in the game without a restart. A file it cannot read (for example while it is saved) keeps the last settings.
-- A setting that this file does not have keeps its default, so an older copy of the file still works after an update.
return {
    Enable = true,       -- false: the game's own skip rule (most story cutscenes cannot be skipped)
    LogDetail = false,   -- true: ue4ss\UE4SS.log names each time the mod sets the game's skip switch (for tests)
}
