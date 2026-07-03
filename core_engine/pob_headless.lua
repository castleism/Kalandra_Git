--[[
  pob_headless.lua  --  JSON-RPC stdio harness for headless Path of Building 2.

  Run by core_engine/pob_sim.py as:   luajit pob_headless.lua   (cwd = PoB src dir)

  Protocol: one JSON object per line on stdin -> one JSON object per line on stdout.
    request : {"id":N,"method":"<m>","params":{...}}
    response: {"id":N,"result":<...>}   or   {"id":N,"error":"<msg>"}

  Design notes:
  * Python decodes the PoB import code to XML (reliable) and sends us the XML, so
    we never depend on PoB's in-Lua base64/inflate (the old fragile path).
  * We resolve the build object and loader by PROBING several known names, since
    PoB2's internals vary by version. The `diag` method reports exactly what was
    found on THIS install, so any mismatch is a one-line fix rather than a guess.
  * All engine chatter goes to stderr; stdout carries ONLY JSON responses.

  PoB is GPL-3.0; this harness is distributed under GPL-3.0.
]]

io.stdout:setvbuf("no")
io.stderr:setvbuf("no")

local _real_stdout = io.stdout
local function elog(s) io.stderr:write(tostring(s) .. "\n") end
print = function(...)
  local t = {}
  for i = 1, select("#", ...) do t[i] = tostring(select(i, ...)) end
  io.stderr:write(table.concat(t, "\t") .. "\n")
end

-- ---------------------------------------------------------------------------
-- Minimal JSON encode/decode.
-- ---------------------------------------------------------------------------
local json = {}
function json.encode(v)
  local t = type(v)
  if t == "nil" then return "null"
  elseif t == "boolean" then return v and "true" or "false"
  elseif t == "number" then
    if v ~= v or v == math.huge or v == -math.huge then return "0" end
    return string.format("%.10g", v)
  elseif t == "string" then
    return '"' .. v:gsub('[%z\1-\31\\"]', function(c)
      local m = {['"']='\\"', ['\\']='\\\\', ['\n']='\\n', ['\r']='\\r', ['\t']='\\t'}
      return m[c] or string.format("\\u%04x", c:byte())
    end) .. '"'
  elseif t == "table" then
    if #v > 0 then
      local parts = {}
      for i = 1, #v do parts[i] = json.encode(v[i]) end
      return "[" .. table.concat(parts, ",") .. "]"
    else
      local parts = {}
      for k, val in pairs(v) do
        parts[#parts + 1] = json.encode(tostring(k)) .. ":" .. json.encode(val)
      end
      if #parts == 0 then return "{}" end
      return "{" .. table.concat(parts, ",") .. "}"
    end
  end
  return "null"
end

function json.decode(s)
  local i = 1
  local function ws() while i <= #s and s:sub(i,i):match("%s") do i = i + 1 end end
  local parseVal
  local function parseStr()
    local out, j = {}, i + 1
    while j <= #s do
      local c = s:sub(j, j)
      if c == '"' then i = j + 1; return table.concat(out)
      elseif c == "\\" then
        local n = s:sub(j+1, j+1)
        local map = {['"']='"', ['\\']='\\', ['/']='/', n='\n', t='\t', r='\r', b='\b', f='\f'}
        if n == "u" then out[#out+1] = string.char(tonumber(s:sub(j+2, j+5), 16) % 256); j = j + 6
        else out[#out+1] = (map[n] or n); j = j + 2 end
      else out[#out+1] = c; j = j + 1 end
    end
    error("bad string")
  end
  parseVal = function()
    ws()
    local c = s:sub(i, i)
    if c == '"' then return parseStr()
    elseif c == "{" then
      local o = {}; i = i + 1; ws()
      if s:sub(i,i) == "}" then i = i + 1; return o end
      while true do
        ws(); local k = parseStr(); ws(); i = i + 1
        o[k] = parseVal(); ws()
        local d = s:sub(i,i); i = i + 1
        if d == "}" then break end
      end
      return o
    elseif c == "[" then
      local a = {}; i = i + 1; ws()
      if s:sub(i,i) == "]" then i = i + 1; return a end
      while true do
        a[#a+1] = parseVal(); ws()
        local d = s:sub(i,i); i = i + 1
        if d == "]" then break end
      end
      return a
    elseif c == "t" then i = i + 4; return true
    elseif c == "f" then i = i + 5; return false
    elseif c == "n" then i = i + 4; return nil
    else
      local num = s:match("^%-?%d+%.?%d*[eE]?[%+%-]?%d*", i)
      i = i + #num; return tonumber(num)
    end
  end
  return parseVal()
end

local function respond(id, result, err)
  _real_stdout:write(json.encode({ id = id, result = result, error = err }) .. "\n")
end

-- ---------------------------------------------------------------------------
-- Boot the PoB2 engine headlessly. HeadlessWrapper.lua lives in the PoB src dir
-- (our cwd) and defines loadBuildFromXML + the global `build` in most versions.
-- ---------------------------------------------------------------------------
-- PoB's pure-Lua modules (xml, base64, dkjson, sha1/2, socket) live in
-- ../runtime/lua and its native modules (.dll) in ../runtime, relative to the
-- src dir we run from. PoB's normal host sets these search paths; a plain LuaJIT
-- does not, so we add them before booting or HeadlessWrapper's require("xml")
-- (Launch.lua:45) fails.
do
  local sep = package.config:sub(1, 1)              -- "\" on Windows
  local rt = ".." .. sep .. "runtime" .. sep
  package.path = rt .. "lua" .. sep .. "?.lua;"
              .. rt .. "lua" .. sep .. "?" .. sep .. "init.lua;"
              .. package.path
  package.cpath = rt .. "?.dll;" .. package.cpath
end

_G.__boot_ok = false
_G.__boot_err = nil
do
  local ok, err = pcall(function() dofile("HeadlessWrapper.lua") end)
  _G.__boot_ok = ok
  if not ok then
    _G.__boot_err = tostring(err)
    elog("HeadlessWrapper boot failed: " .. tostring(err))
  end
end

-- Resolve the build object across known locations (varies by version).
local function resolve_build()
  if type(build) == "table" then return build end
  if type(mainObject) == "table" then
    local mo = mainObject
    if mo.main and mo.main.modes and mo.main.modes["BUILD"] then
      build = mo.main.modes["BUILD"]; return build
    end
    if mo.build then build = mo.build; return build end
  end
  if type(launch) == "table" and launch.main and launch.main.modes
     and launch.main.modes["BUILD"] then
    build = launch.main.modes["BUILD"]; return build
  end
  return nil
end

-- Load a build from XML text (sent decoded by Python).
local function load_xml(xml)
  if type(xml) ~= "string" or #xml < 10 then error("empty/invalid build XML") end
  if type(loadBuildFromXML) == "function" then
    loadBuildFromXML(xml, "Kalandra")
  elseif type(LoadBuildFromXML) == "function" then
    LoadBuildFromXML(xml, "Kalandra")
  else
    local b = resolve_build()
    if b and type(b.Init) == "function" then
      b:Init(false, "Kalandra", xml)
    else
      error("no headless build loader found (loadBuildFromXML / build:Init)")
    end
  end
  local b = resolve_build()
  if b and b.calcsTab and type(b.calcsTab.BuildOutput) == "function" then
    pcall(function() b.calcsTab:BuildOutput() end)
  end
  return true
end

-- The output table where PoB stores computed stats.
local function output_table()
  local b = resolve_build()
  if not b then return nil end
  if b.calcsTab then
    if type(b.calcsTab.mainOutput) == "table" then return b.calcsTab.mainOutput end
    if b.calcsTab.mainEnv and b.calcsTab.mainEnv.player
       and type(b.calcsTab.mainEnv.player.output) == "table" then
      return b.calcsTab.mainEnv.player.output
    end
  end
  return nil
end

local function read_stats()
  local out = output_table() or {}
  local function num(...)
    for _, k in ipairs({...}) do
      if type(out[k]) == "number" then return out[k] end
    end
    return 0
  end
  -- DPS: take the MAX of the known DPS fields — for warcry / non-hit builds the
  -- real number is in CombinedDPS while FullDPS/TotalDPS are 0, so first-match
  -- would wrongly return 0. Then fall back to the largest 'DPS'-named value.
  local function dps_val()
    local best = 0
    for _, k in ipairs({"FullDPS", "CombinedDPS", "TotalDPS", "TotalDotDPS",
                        "AverageDamage", "WithImpaleDPS", "DPS"}) do
      if type(out[k]) == "number" and out[k] > best then best = out[k] end
    end
    if best == 0 then
      for k, v in pairs(out) do
        if type(v) == "number" and v > best and k:find("DPS") and not k:find("Cost") then
          best = v
        end
      end
    end
    return best
  end
  local res = {
    total_dps      = dps_val(),
    life           = num("Life"),
    energy_shield  = num("EnergyShield"),
    mana           = num("Mana"),
    ward           = num("Ward"),
    ehp            = num("TotalEHP", "EHP"),
    fire_res       = num("FireResist"),
    cold_res       = num("ColdResist"),
    lightning_res  = num("LightningResist"),
    chaos_res      = num("ChaosResist"),
    armour         = num("Armour"),
    evasion        = num("Evasion"),
    block          = num("BlockChance"),
    crit_chance    = num("CritChance"),
    crit_multi     = num("CritMultiplier"),
    spirit         = num("Spirit"),
    spirit_unreserved = num("SpiritUnreserved"),
  }
  local b = resolve_build()
  if b then
    if b.spec then
      res.class = b.spec.curClassName or b.spec.className or "?"
      res.ascendancy = b.spec.curAscendClassName or b.spec.ascendClassName or "None"
    end
    -- PoB stores the character level as `characterLevel` (build.level is unset
    -- in headless), so prefer that; fall back to the output table's Level.
    res.level = b.characterLevel or b.level or num("Level") or 0
  end
  return res
end

-- ---------------------------------------------------------------------------
-- Methods.
-- ---------------------------------------------------------------------------
local methods = {}
function methods.ping() return "pong" end

function methods.load_xml(p)
  _G.__loaded_xml = p.xml
  load_xml(p.xml)
  return read_stats()
end

function methods.get_stats() return read_stats() end

-- Diagnostic: report exactly what this PoB install exposes, so any version
-- mismatch is a precise fix instead of a guess. (Sent home by the self-test.)
function methods.diag()
  local d = {
    boot_ok = _G.__boot_ok,
    boot_err = _G.__boot_err,
    has_loadBuildFromXML = type(loadBuildFromXML) == "function",
    has_LoadBuildFromXML = type(LoadBuildFromXML) == "function",
    has_build_global = type(build) == "table",
    has_mainObject = type(mainObject) == "table",
    has_launch = type(launch) == "table",
  }
  local b = resolve_build()
  d.build_resolved = b ~= nil
  d.has_calcsTab = (b and b.calcsTab) ~= nil
  d.has_spec = (b and b.spec) ~= nil
  local out = output_table()
  d.has_output = out ~= nil
  if out then
    local keys, n = {}, 0
    for k, v in pairs(out) do
      if type(v) == "number" then
        n = n + 1
        if n <= 60 then keys[#keys + 1] = k end
      end
    end
    d.output_numeric_count = n
    d.sample_output_keys = keys
  end
  return d
end

-- Re-load an alternate full build code to compare (robust cross-version what-if).
function methods.simulate(p)
  local before = read_stats()
  local after = before
  if p.changes and p.changes.alt_xml then
    load_xml(p.changes.alt_xml)
    after = read_stats()
    if _G.__loaded_xml then load_xml(_G.__loaded_xml) end  -- restore
  end
  local delta = {}
  for k, v in pairs(after) do
    if type(v) == "number" and type(before[k]) == "number" then
      delta[k] = v - before[k]
    end
  end
  return { before = before, after = after, delta = delta }
end

-- ---------------------------------------------------------------------------
-- JSON-RPC loop.
-- ---------------------------------------------------------------------------
for line in io.lines() do
  if line and #line > 0 then
    local ok_dec, req = pcall(json.decode, line)
    if ok_dec and type(req) == "table" then
      local fn = methods[req.method]
      if fn then
        local ok, result = pcall(fn, req.params or {})
        if ok then respond(req.id, result, nil)
        else respond(req.id, nil, tostring(result)) end
      else
        respond(req.id, nil, "unknown method: " .. tostring(req.method))
      end
    end
  end
end
