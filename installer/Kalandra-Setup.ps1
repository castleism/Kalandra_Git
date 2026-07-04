# =====================================================================
#  Kalandra Installer / Repair  (PowerShell GUI)
#  - Per-dependency: Install (opens the download page, or a terminal for
#    repo/pip commands), Check Location (set folder + verify the file is
#    found, with a success/fail popup), and Connect Account where relevant.
#  - Doubles as a REPAIR tool: "Verify All" re-checks every dependency.
#  - Shows the revision of each dependency verified with this Kalandra rev.
#  Runs on a brand-new Windows 10/11 (PowerShell + .NET are built in).
# =====================================================================

$ErrorActionPreference = "Stop"
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot  = Split-Path -Parent $ScriptDir
$ConfigPath   = Join-Path $ProjectRoot "data_engine\config.json"
$ResourcesDir = Join-Path $ProjectRoot "Additional Resources"

function PF86 { return ${env:ProgramFiles(x86)} }

# ---- version (single source of truth: ..\version.py) ----------------
$Version = "0.0.0"
try {
    $vp = Join-Path $ProjectRoot "version.py"
    if (Test-Path $vp) {
        $m = Select-String -Path $vp -Pattern 'KALANDRA_VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
        if ($m) { $Version = $m.Matches[0].Groups[1].Value }
    }
} catch {}

# ---- component catalogue --------------------------------------------
$Components = @(
    @{ Id="python"; Name="Python 3.12 (64-bit) - the runtime Kalandra runs on";
       Cat="Required"; Credit="Python Software Foundation"; Verified="3.12.x (64-bit)";
       Install=@{Kind="terminal"; Cmd="winget install -e --id Python.Python.3.12"};
       Check=@{Kind="python"}; Account=@{Kind="none"}; Paths=@() }

    @{ Id="pip"; Name="Python packages (PyQt6, Whisper, AI SDKs, scraper)";
       Cat="Required"; Credit="Riverbank, SYSTRAN, OpenAI, Google + PyPI authors";
       Verified="see requirements.txt (PyQt6>=6.7, faster-whisper>=1.0, ...)";
       Install=@{Kind="terminal"; Cmd="{PY} -m pip install -r requirements.txt"};
       Check=@{Kind="pip"}; Account=@{Kind="none"}; Paths=@() }

    @{ Id="luajit"; Name="LuaJIT - Path of Building simulator engine";
       Cat="Engine extras"; Credit="Mike Pall; build by ScriptTiger"; Verified="LuaJIT-For-Windows (latest)";
       Install=@{Kind="terminal"; Cmd="{PY} scripts\install_dependencies.py --yes luajit"};
       Check=@{Kind="file"; File="LuaJIT-For-Windows.exe"; CfgKey="luajit_path"; SaveFile=$true};
       Account=@{Kind="none"}; Paths=@((Join-Path $ProjectRoot "tools\luajit")) }

    @{ Id="rhubarb"; Name="Rhubarb Lip Sync - talking-orb mouth shapes";
       Cat="Engine extras"; Credit="Daniel Wolf"; Verified="Rhubarb 1.14.0";
       Install=@{Kind="terminal"; Cmd="{PY} scripts\install_dependencies.py --yes rhubarb"};
       Check=@{Kind="file"; File="rhubarb.exe"; CfgKey="rhubarb_path"; SaveFile=$true};
       Account=@{Kind="none"}; Paths=@((Join-Path $ProjectRoot "tools\rhubarb")) }

    @{ Id="pob_source"; Name="Path of Building 2 source - headless simulator";
       Cat="Engine extras"; Credit="Path of Building Community"; Verified="PathOfBuilding-PoE2 (latest)";
       Install=@{Kind="terminal"; Cmd="{PY} scripts\install_dependencies.py --yes pob_source"};
       Check=@{Kind="file"; File="HeadlessWrapper.lua"; CfgKey="pob_install_dir"; SaveFile=$false};
       Account=@{Kind="none"}; Paths=@((Join-Path $ProjectRoot "tools")) }

    @{ Id="pob2_app"; Name="Path of Building 2 - the build planner app";
       Cat="Companion apps"; Credit="Path of Building Community"; Verified="latest (tested 2026-06)";
       Install=@{Kind="web"; Url="https://github.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/releases"};
       Check=@{Kind="file"; File="Path of Building-PoE2.exe"; CfgKey="pob_app_dir"; SaveFile=$false; ExeKey="pob_exe"};
       Account=@{Kind="none"};
       Paths=@((Join-Path (PF86) "Path of Building Community (PoE2)"),
               (Join-Path $env:LOCALAPPDATA "Programs\Path of Building Community (PoE2)")) }

    @{ Id="exiled2"; Name="Exiled Exchange 2 - PoE2 price-check overlay";
       Cat="Companion apps"; Credit="Kvan7 (fork of Awakened PoE Trade)"; Verified="latest (tested 2026-06)";
       Install=@{Kind="web"; Url="https://kvan7.github.io/Exiled-Exchange-2/download"};
       Check=@{Kind="file"; File="*.exe"; CfgKey="exiled_exchange2"; SaveFile=$false};
       Account=@{Kind="none"};
       Paths=@((Join-Path $env:LOCALAPPDATA "Programs\exiled-exchange-2")) }

    @{ Id="xiletrade"; Name="Xiletrade - PoE1/2 overlay + price checker";
       Cat="Companion apps"; Credit="maxensas"; Verified="latest (tested 2026-06)";
       Install=@{Kind="web"; Url="https://github.com/maxensas/xiletrade/releases"};
       Check=@{Kind="file"; File="*.exe"; CfgKey="xiletrade"; SaveFile=$false};
       Account=@{Kind="none"};
       Paths=@((Join-Path $env:ProgramFiles "Xiletrade")) }

    @{ Id="lailloken"; Name="Lailloken Exile-UI - PoE2 QoL overlay (AutoHotkey)";
       Cat="Companion apps"; Credit="Lailloken"; Verified="v1.51.x (runs via AutoHotkey)";
       Install=@{Kind="web"; Url="https://github.com/Lailloken/Exile-UI/releases"};
       Check=@{Kind="file"; File="*.ahk"; CfgKey="lailloken_ui"; SaveFile=$false};
       Account=@{Kind="none"}; Paths=@((Join-Path $ProjectRoot "tools\apps\Exile-UI")) }

    @{ Id="obsidian"; Name="Obsidian - views Kalandra's knowledge database";
       Cat="Companion apps"; Credit="Dynalist Inc. (obsidian.md)"; Verified="Obsidian 1.x";
       Install=@{Kind="web"; Url="https://obsidian.md/download"};
       Check=@{Kind="file"; File="Obsidian.exe"; CfgKey="obsidian_dir"; SaveFile=$false};
       Account=@{Kind="none"};
       Paths=@((Join-Path $env:LOCALAPPDATA "Obsidian"),
               (Join-Path $env:LOCALAPPDATA "Programs\obsidian")) }

    @{ Id="game"; Name="Path of Exile 2 install - for game-file extraction";
       Cat="Game"; Credit="Grinding Gear Games (not installed by us)"; Verified="PoE2 0.x (current)";
       Install=@{Kind="web"; Url="https://pathofexile2.com"};
       Check=@{Kind="file"; File="oo2core*.dll"; AltDir="Bundles2"; CfgKey="game_install_dir"; SaveFile=$false};
       Account=@{Kind="url"; Url="https://www.pathofexile.com/login"};
       Paths=@("C:\Program Files (x86)\Steam\steamapps\common\Path of Exile 2",
               "C:\Program Files (x86)\Grinding Gear Games\Path of Exile 2",
               "D:\SteamLibrary\steamapps\common\Path of Exile 2",
               "E:\SteamLibrary\steamapps\common\Path of Exile 2") }

    @{ Id="openai"; Name="OpenAI / ChatGPT - AI brain (browser/API key, nothing installed)";
       Cat="AI brains (browser / API key - nothing installed locally)"; Credit="OpenAI"; Verified="API (gpt-4o-mini)";
       Install=@{Kind="web"; Url="https://platform.openai.com/api-keys"; Label="Get API key (web)"};
       Check=@{Kind="none"}; Account=@{Kind="apikey"; Service="openai"}; Paths=@() }

    @{ Id="gemini"; Name="Google Gemini - AI brain (browser/API key, nothing installed)";
       Cat="AI brains (browser / API key - nothing installed locally)"; Credit="Google"; Verified="API (gemini-2.5-flash)";
       Install=@{Kind="web"; Url="https://aistudio.google.com/app/apikey"; Label="Get API key (web)"};
       Check=@{Kind="none"}; Account=@{Kind="apikey"; Service="gemini"}; Paths=@() }
)

# ---- credits --------------------------------------------------------
$CreditsText = @"
KALANDRA  -  version $Version  (pre-release, released 2026-06-29)

Independent, fan-made PoE2 companion. Not affiliated with Grinding Gear Games.
Components are made by others; Kalandra only helps you install them. Thanks to:
  Python (PSF) | PyQt6 (Riverbank) | faster-whisper (SYSTRAN) | OpenAI | Google
  LuaJIT (Mike Pall / ScriptTiger) | Rhubarb Lip Sync (Daniel Wolf)
  Path of Building 2 (PoB Community) | Exiled Exchange 2 (Kvan7 / SnosMe)
  Xiletrade (maxensas) | Lailloken Exile-UI (Lailloken) | Obsidian (obsidian.md)
  Path of Exile 2 (Grinding Gear Games)
Each project keeps its own license; see its repository for full terms.
"@

# ---- colors ---------------------------------------------------------
$bg   = [System.Drawing.Color]::FromArgb(20,24,31)
$card = [System.Drawing.Color]::FromArgb(28,33,42)
$fg   = [System.Drawing.Color]::FromArgb(232,232,238)
$muted= [System.Drawing.Color]::FromArgb(150,160,171)
$gold = [System.Drawing.Color]::FromArgb(212,163,115)
$green= [System.Drawing.Color]::FromArgb(120,200,140)
$red  = [System.Drawing.Color]::FromArgb(225,110,110)

# ---- helpers --------------------------------------------------------
$script:LogBox = $null
function Log($m) {
    if ($script:LogBox) { $script:LogBox.AppendText($m + "`r`n"); [System.Windows.Forms.Application]::DoEvents() }
    else { Write-Host $m }
}

function Find-Python {
    foreach ($c in @("py -3.12","py -3","python")) {
        try {
            $p = @($c -split " "); $exe=$p[0]; $rest=@(); if($p.Count -gt 1){$rest=$p[1..($p.Count-1)]}
            $v = & $exe @rest --version 2>$null
            if ($LASTEXITCODE -eq 0 -and $v) { return $c }
        } catch {}
    }
    $known = @((Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
               "C:\Python312\python.exe")
    foreach ($k in $known) { if (Test-Path $k) { return $k } }
    return $null
}

function Read-Config {
    if (Test-Path $ConfigPath) { try { return (Get-Content $ConfigPath -Raw | ConvertFrom-Json) } catch {} }
    return [PSCustomObject]@{}
}
function Write-ConfigValue($cfg, $key, $value) {
    if ($null -eq $cfg.PSObject.Properties[$key]) { $cfg | Add-Member -NotePropertyName $key -NotePropertyValue $value -Force }
    else { $cfg.$key = $value }
}
function Save-Config($cfg) {
    $dir = Split-Path -Parent $ConfigPath
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    ($cfg | ConvertTo-Json -Depth 6) | Set-Content -Path $ConfigPath -Encoding UTF8
}

function Invoke-Py($pyArgs, $stdinText) {
    $py = Find-Python; if (-not $py) { return "Python not found." }
    $p = @($py -split " "); $exe=$p[0]; $lead=@(); if($p.Count -gt 1){$lead=$p[1..($p.Count-1)]}
    $full = $lead + $pyArgs
    try {
        if ($null -ne $stdinText) { $o = $stdinText | & $exe @full 2>&1 } else { $o = & $exe @full 2>&1 }
        return ($o | Out-String)
    } catch { return $_.Exception.Message }
}

function PyQuoted {
    $py = Find-Python; if (-not $py) { return "python" }
    if ($py -like '*\*') { return ('"' + $py + '"') }
    return $py
}

function Detect-Default($comp) {
    foreach ($p in $comp.Paths) { if ($p -and (Test-Path $p)) { return $p } }
    return $null
}

function ResourceFor($id) {
    switch ($id) {
        "python"     { "Python" }
        "pip"        { "Python Packages (wheels)" }
        "luajit"     { "LuaJIT" }
        "rhubarb"    { "Rhubarb" }
        "pob_source" { "Path of Building 2 Source" }
        "pob2_app"   { "Path of Building 2" }
        "exiled2"    { "Exiled Exchange 2" }
        "xiletrade"  { "Xiletrade" }
        "lailloken"  { "Lailloken Exile-UI" }
        "obsidian"   { "Obsidian" }
        default      { $null }
    }
}

# Read-Secret: small masked input box. Returns text or $null.
function Read-Secret($prompt) {
    $f = New-Object System.Windows.Forms.Form
    $f.Text = "Kalandra - connect account"; $f.StartPosition = "CenterParent"
    $f.Size = New-Object System.Drawing.Size(460,170); $f.BackColor = $bg; $f.ForeColor = $fg
    $l = New-Object System.Windows.Forms.Label
    $l.Text = $prompt; $l.Location = New-Object System.Drawing.Point(12,12); $l.Size = New-Object System.Drawing.Size(420,40)
    $f.Controls.Add($l)
    $tb = New-Object System.Windows.Forms.TextBox
    $tb.Location = New-Object System.Drawing.Point(12,58); $tb.Size = New-Object System.Drawing.Size(420,22)
    $tb.UseSystemPasswordChar = $true; $tb.BackColor = $card; $tb.ForeColor = $fg
    $f.Controls.Add($tb)
    $ok = New-Object System.Windows.Forms.Button
    $ok.Text = "Save"; $ok.Location = New-Object System.Drawing.Point(256,92); $ok.Size = New-Object System.Drawing.Size(80,28)
    $ok.DialogResult = [System.Windows.Forms.DialogResult]::OK; $ok.FlatStyle="Flat"; $ok.BackColor=$gold; $ok.ForeColor=[System.Drawing.Color]::Black
    $f.Controls.Add($ok); $f.AcceptButton = $ok
    $cn = New-Object System.Windows.Forms.Button
    $cn.Text = "Cancel"; $cn.Location = New-Object System.Drawing.Point(344,92); $cn.Size = New-Object System.Drawing.Size(88,28)
    $cn.DialogResult = [System.Windows.Forms.DialogResult]::Cancel; $cn.FlatStyle="Flat"; $cn.BackColor=$card; $cn.ForeColor=$fg
    $f.Controls.Add($cn)
    if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { return $tb.Text } else { return $null }
}

function Notify($title, $text) {
    [System.Windows.Forms.MessageBox]::Show($text, $title,
        [System.Windows.Forms.MessageBoxButtons]::OK) | Out-Null
}

# Verify a "file" component against a folder. Returns @{Ok; Found; Save}.
function Test-FileComponent($check, $folder) {
    $found = $null
    if ($check.File -and (Test-Path $folder)) {
        $hit = Get-ChildItem -Path $folder -Recurse -Filter $check.File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { $found = $hit }
    }
    if (-not $found -and $check.AltDir -and (Test-Path (Join-Path $folder $check.AltDir))) {
        return @{ Ok=$true; Found=$null; Save=$folder }
    }
    if ($found) {
        $save = if ($check.SaveFile) { $found.FullName } else { $folder }
        return @{ Ok=$true; Found=$found; Save=$save }
    }
    return @{ Ok=$false; Found=$null; Save=$null }
}

# =====================================================================
#  GUI
# =====================================================================
$form = New-Object System.Windows.Forms.Form
$form.Text = "Kalandra Installer / Repair"
$form.Size = New-Object System.Drawing.Size(820,820)
$form.StartPosition = "CenterScreen"
$form.BackColor = $bg; $form.ForeColor = $fg
$form.Font = New-Object System.Drawing.Font("Segoe UI",9)

$title = New-Object System.Windows.Forms.Label
$title.Text = "Kalandra  -  Installer / Repair    (v$Version, pre-release)"
$title.ForeColor = $gold; $title.Font = New-Object System.Drawing.Font("Segoe UI",15,[System.Drawing.FontStyle]::Bold)
$title.Location = New-Object System.Drawing.Point(16,12); $title.Size = New-Object System.Drawing.Size(620,28)
$form.Controls.Add($title)

$sub = New-Object System.Windows.Forms.Label
$sub.Text = "Install (download page / terminal), Check Location to verify, Connect accounts. Optional items can be skipped. 'Finish' when done; re-run any time to repair."
$sub.ForeColor = $muted; $sub.Location = New-Object System.Drawing.Point(18,42); $sub.Size = New-Object System.Drawing.Size(770,18)
$form.Controls.Add($sub)

$creditsBtn = New-Object System.Windows.Forms.Button
$creditsBtn.Text = "Credits"; $creditsBtn.Location = New-Object System.Drawing.Point(700,10); $creditsBtn.Size = New-Object System.Drawing.Size(96,26)
$creditsBtn.FlatStyle="Flat"; $creditsBtn.BackColor=$card; $creditsBtn.ForeColor=$fg
$creditsBtn.Add_Click({
    $cf = New-Object System.Windows.Forms.Form
    $cf.Text="Credits"; $cf.Size=New-Object System.Drawing.Size(680,420); $cf.StartPosition="CenterParent"; $cf.BackColor=$bg
    $tb=New-Object System.Windows.Forms.TextBox; $tb.Multiline=$true; $tb.ReadOnly=$true; $tb.ScrollBars="Vertical"
    $tb.Dock="Fill"; $tb.BackColor=$card; $tb.ForeColor=$fg; $tb.Font=New-Object System.Drawing.Font("Consolas",9); $tb.Text=$CreditsText
    $cf.Controls.Add($tb); $cf.ShowDialog() | Out-Null
})
$form.Controls.Add($creditsBtn)

# data strategy note: poe2db is the primary database; the rest are backups.
$stratLabel = New-Object System.Windows.Forms.Label
$stratLabel.Text = "Database: built primarily from poe2db.tw (cleanest, fastest, tracks every patch). poe2wiki / poe.ninja / game-extraction are optional backups."
$stratLabel.ForeColor = $gold
$stratLabel.Location = New-Object System.Drawing.Point(12,58); $stratLabel.Size = New-Object System.Drawing.Size(792,16)
$form.Controls.Add($stratLabel)

# database freshness (per source "current as of" dates)
$freshLabel = New-Object System.Windows.Forms.Label
$freshLabel.Text = "Databases: (checking...)"; $freshLabel.ForeColor = $green
$freshLabel.Location = New-Object System.Drawing.Point(12,76); $freshLabel.Size = New-Object System.Drawing.Size(792,18)
$form.Controls.Add($freshLabel)

# scrollable rows
$panel = New-Object System.Windows.Forms.Panel
$panel.Location = New-Object System.Drawing.Point(12,98); $panel.Size = New-Object System.Drawing.Size(792,526)
$panel.AutoScroll = $true; $panel.BackColor = $bg
$form.Controls.Add($panel)

$rows = @()
$y = 6
$lastCat = ""
foreach ($comp in $Components) {
    if ($comp.Cat -ne $lastCat) {
        $hdr = New-Object System.Windows.Forms.Label
        $hdr.Text = $comp.Cat.ToUpper(); $hdr.ForeColor = $gold
        $hdr.Font = New-Object System.Drawing.Font("Segoe UI",9,[System.Drawing.FontStyle]::Bold)
        $hdr.Location = New-Object System.Drawing.Point(4,$y); $hdr.Size = New-Object System.Drawing.Size(760,18)
        $panel.Controls.Add($hdr); $y += 22; $lastCat = $comp.Cat
    }

    $name = New-Object System.Windows.Forms.Label
    $name.Text = $comp.Name; $name.ForeColor = $fg; $name.Font = New-Object System.Drawing.Font("Segoe UI",9,[System.Drawing.FontStyle]::Bold)
    $name.Location = New-Object System.Drawing.Point(6,$y); $name.Size = New-Object System.Drawing.Size(470,18)
    $panel.Controls.Add($name)

    $ver = New-Object System.Windows.Forms.Label
    $ver.Text = "Verified: " + $comp.Verified; $ver.ForeColor = $muted
    $ver.Location = New-Object System.Drawing.Point(480,$y); $ver.Size = New-Object System.Drawing.Size(290,18)
    $panel.Controls.Add($ver); $y += 19

    $det = Detect-Default $comp
    $status = New-Object System.Windows.Forms.Label
    if ($det) { $status.Text = "Detected: $det"; $status.ForeColor = $green }
    else { $status.Text = "Not verified yet - Install, then Check Location."; $status.ForeColor = $muted }
    $status.Location = New-Object System.Drawing.Point(8,$y); $status.Size = New-Object System.Drawing.Size(764,16)
    $panel.Controls.Add($status); $y += 18

    $bx = 8
    if ($comp.Install.Kind -ne "none") {
        $ib = New-Object System.Windows.Forms.Button
        $ibText = "Install (terminal)"
        if ($comp.Install.Kind -eq "web") { $ibText = "Install (open page)" }
        if ($comp.Install.Label) { $ibText = $comp.Install.Label }
        $ib.Text = $ibText
        $ib.Location = New-Object System.Drawing.Point($bx,$y); $ib.Size = New-Object System.Drawing.Size(150,26)
        $ib.FlatStyle="Flat"; $ib.BackColor=$gold; $ib.ForeColor=[System.Drawing.Color]::Black
        $ib.Tag = @{ Ins=$comp.Install; Id=$comp.Id }
        $ib.Add_Click({
            $t = $this.Tag; $ins = $t.Ins; $id = $t.Id
            try {
                $res = ResourceFor $id
                $resDir = if ($res) { Join-Path $ResourcesDir $res } else { $null }

                if ($id -eq "pip") {
                    $py = PyQuoted
                    $cmd = "$py -m pip install -r requirements.txt"
                    if ($resDir -and (Test-Path $resDir) -and
                        (Get-ChildItem $resDir -Filter *.whl -ErrorAction SilentlyContinue)) {
                        $cmd = "$py -m pip install --no-index --find-links ""$resDir"" -r requirements.txt"
                        Log "Offline: installing packages from bundled wheels."
                    }
                    $inner = "cd /d `"$ProjectRoot`" && $cmd"
                    Start-Process -FilePath "cmd.exe" -ArgumentList "/k $inner"
                    return
                }

                # Prefer a bundled installer in Additional Resources (offline).
                if ($resDir -and (Test-Path $resDir)) {
                    $exe = Get-ChildItem $resDir -File -ErrorAction SilentlyContinue |
                           Where-Object { @('.exe','.msi') -contains $_.Extension.ToLower() } | Select-Object -First 1
                    if ($exe) { Start-Process $exe.FullName; Log "Offline: running bundled installer $($exe.Name)"; return }
                    $other = Get-ChildItem $resDir -File -ErrorAction SilentlyContinue |
                             Where-Object { $_.Name -ne 'README.txt' } | Select-Object -First 1
                    if ($other) { Start-Process $resDir; Log "Offline: opened bundled resource folder for $id"; return }
                }

                # Online fallback.
                if ($ins.Kind -eq "web") { Start-Process $ins.Url; Log "Opened download page: $($ins.Url)" }
                elseif ($ins.Kind -eq "terminal") {
                    $cmd = $ins.Cmd.Replace("{PY}", (PyQuoted))
                    $inner = "cd /d `"$ProjectRoot`" && $cmd"
                    Start-Process -FilePath "cmd.exe" -ArgumentList "/k $inner"
                    Log "Opened a terminal: $cmd"
                }
            } catch { Log "Install action failed: $($_.Exception.Message)" }
        })
        $panel.Controls.Add($ib); $bx += 158
    }

    if ($comp.Check.Kind -ne "none") {
        $cbtn = New-Object System.Windows.Forms.Button
        $cbText = "Check Location"
        if ($comp.Check.Kind -eq "python") { $cbText = 'Check for: "python.exe"' }
        elseif ($comp.Check.Kind -eq "pip") { $cbText = "Verify packages" }
        elseif ($comp.Check.File) { $cbText = 'Check Location for: "' + $comp.Check.File + '"' }
        $cbtn.Text = $cbText
        $cbtn.Location = New-Object System.Drawing.Point($bx,$y); $cbtn.Size = New-Object System.Drawing.Size(250,26)
        $cbtn.FlatStyle="Flat"; $cbtn.BackColor=$card; $cbtn.ForeColor=$fg
        $cbtn.Tag = @{ Comp=$comp; Status=$status }
        $cbtn.Add_Click({
            $t = $this.Tag; $comp = $t.Comp; $st = $t.Status; $chk = $comp.Check
            try {
                if ($chk.Kind -eq "python") {
                    $py = Find-Python
                    if ($py) { $st.Text="OK: Python found ($py)"; $st.ForeColor=$green; Notify "Check: SUCCESS" "Python is installed:`n$py" }
                    else { $st.Text="FAIL: Python not found"; $st.ForeColor=$red; Notify "Check: FAILED" "Python was not found. Use Install first." }
                    return
                }
                if ($chk.Kind -eq "pip") {
                    $o = Invoke-Py @("-c","import PyQt6, requests, bs4, numpy, keyring; print('packages OK')")
                    if ($o -match "packages OK") { $st.Text="OK: core packages import"; $st.ForeColor=$green; Notify "Check: SUCCESS" "Core Python packages import correctly." }
                    else { $st.Text="FAIL: packages missing"; $st.ForeColor=$red; Notify "Check: FAILED" ("Packages not importable:`n" + $o) }
                    return
                }
                # file kind: pick a folder, verify the expected file
                $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
                $dlg.Description = "Select the folder for: " + $comp.Name
                $det = Detect-Default $comp
                if ($det) { $dlg.SelectedPath = $det }
                if ($dlg.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { return }
                $res = Test-FileComponent $chk $dlg.SelectedPath
                if ($res.Ok) {
                    $cfg = Read-Config
                    Write-ConfigValue $cfg $chk.CfgKey $res.Save
                    if ($chk.ExeKey -and $res.Found) { Write-ConfigValue $cfg $chk.ExeKey $res.Found.FullName }
                    Save-Config $cfg
                    $st.Text = "OK: found and saved -> $($res.Save)"; $st.ForeColor=$green
                    Notify "Check Location: SUCCESS" ("Found it and saved the location:`n" + $res.Save)
                } else {
                    $st.Text = "FAIL: '$($chk.File)' not found in $($dlg.SelectedPath)"; $st.ForeColor=$red
                    Notify "Check Location: FAILED" ("Could not find '" + $chk.File + "' in:`n" + $dlg.SelectedPath)
                }
            } catch { Log "Check failed: $($_.Exception.Message)" }
        })
        $panel.Controls.Add($cbtn); $bx += 258
    }

    if ($comp.Account.Kind -ne "none") {
        $ab = New-Object System.Windows.Forms.Button
        $ab.Text = "Connect Account"
        $ab.Location = New-Object System.Drawing.Point($bx,$y); $ab.Size = New-Object System.Drawing.Size(140,26)
        $ab.FlatStyle="Flat"; $ab.BackColor=$card; $ab.ForeColor=$fg
        $ab.Tag = @{ Acct=$comp.Account; Status=$status; Name=$comp.Name }
        $ab.Add_Click({
            $t = $this.Tag; $a = $t.Acct; $st = $t.Status
            try {
                if ($a.Kind -eq "url") { Start-Process $a.Url; Log "Opened sign-in page: $($a.Url)" }
                elseif ($a.Kind -eq "apikey") {
                    $val = Read-Secret ("Paste your API key for " + $t.Name + ".`nStored securely in the Windows keychain.")
                    if ($val -ne $null -and $val.Trim() -ne "") {
                        $r = Invoke-Py @((Join-Path $ProjectRoot "scripts\configure.py"),"set-secret",$a.Service) $val
                        $st.Text = "Account: " + ($r.Trim()); $st.ForeColor=$green
                        Notify "Connect Account" $r.Trim()
                    }
                }
            } catch { Log "Connect failed: $($_.Exception.Message)" }
        })
        $panel.Controls.Add($ab); $bx += 148
    }

    $y += 34
    $rows += @{ Comp=$comp; Status=$status }
}

# ---- profile area ----
$profLabel = New-Object System.Windows.Forms.Label
$profLabel.Text = "PROFILE:  account name / league / AI brain"
$profLabel.ForeColor=$gold; $profLabel.Font=New-Object System.Drawing.Font("Segoe UI",9,[System.Drawing.FontStyle]::Bold)
$profLabel.Location = New-Object System.Drawing.Point(18,632); $profLabel.Size = New-Object System.Drawing.Size(400,16)
$form.Controls.Add($profLabel)

$acctBox = New-Object System.Windows.Forms.TextBox
$acctBox.Location = New-Object System.Drawing.Point(18,652); $acctBox.Size = New-Object System.Drawing.Size(260,22)
$acctBox.BackColor=$card; $acctBox.ForeColor=$fg; $form.Controls.Add($acctBox)
$acctHint = New-Object System.Windows.Forms.Label
$acctHint.Text="Account name (Name#1234)"; $acctHint.ForeColor=$muted
$acctHint.Location=New-Object System.Drawing.Point(18,676); $acctHint.Size=New-Object System.Drawing.Size(260,14); $form.Controls.Add($acctHint)

$leagueBox = New-Object System.Windows.Forms.TextBox
$leagueBox.Location = New-Object System.Drawing.Point(290,652); $leagueBox.Size = New-Object System.Drawing.Size(160,22)
$leagueBox.BackColor=$card; $leagueBox.ForeColor=$fg; $form.Controls.Add($leagueBox)
$leagueHint = New-Object System.Windows.Forms.Label
$leagueHint.Text="League"; $leagueHint.ForeColor=$muted
$leagueHint.Location=New-Object System.Drawing.Point(290,676); $leagueHint.Size=New-Object System.Drawing.Size(160,14); $form.Controls.Add($leagueHint)

$brainCombo = New-Object System.Windows.Forms.ComboBox
$brainCombo.DropDownStyle="DropDownList"; $brainCombo.Items.AddRange(@("gemini","openai")) | Out-Null
$brainCombo.Location = New-Object System.Drawing.Point(462,652); $brainCombo.Size = New-Object System.Drawing.Size(150,22)
$brainCombo.BackColor=$card; $brainCombo.ForeColor=$fg; $form.Controls.Add($brainCombo)
$brainHint = New-Object System.Windows.Forms.Label
$brainHint.Text="AI brain"; $brainHint.ForeColor=$muted
$brainHint.Location=New-Object System.Drawing.Point(462,676); $brainHint.Size=New-Object System.Drawing.Size(150,14); $form.Controls.Add($brainHint)

$saveProfBtn = New-Object System.Windows.Forms.Button
$saveProfBtn.Text="Save profile"; $saveProfBtn.Location=New-Object System.Drawing.Point(626,650); $saveProfBtn.Size=New-Object System.Drawing.Size(160,26)
$saveProfBtn.FlatStyle="Flat"; $saveProfBtn.BackColor=$card; $saveProfBtn.ForeColor=$fg; $form.Controls.Add($saveProfBtn)

# ---- log box ----
$script:LogBox = New-Object System.Windows.Forms.TextBox
$script:LogBox.Multiline=$true; $script:LogBox.ReadOnly=$true; $script:LogBox.ScrollBars="Vertical"
$script:LogBox.Location=New-Object System.Drawing.Point(12,700); $script:LogBox.Size=New-Object System.Drawing.Size(792,66)
$script:LogBox.BackColor=[System.Drawing.Color]::FromArgb(12,14,19); $script:LogBox.ForeColor=$fg
$script:LogBox.Font=New-Object System.Drawing.Font("Consolas",8); $form.Controls.Add($script:LogBox)

# ---- database freshness + bundled-DB import ----
function Refresh-Freshness {
    try {
        $out = Invoke-Py @((Join-Path $ProjectRoot "scripts\db_status.py"), "--json")
        $j = $null
        try { $j = $out | ConvertFrom-Json } catch {}
        if ($j -and $j.exists) {
            $s = $j.sources
            $freshLabel.Text = ("Databases current as of -> poe2db: {0} ({1}) | wiki: {2} | poe.ninja: {3} | game-data: {4}  [total {5} entries]" -f `
                $s.poe2db.as_of, $s.poe2db.entries, $s.poe2wiki.as_of, $s.poe_ninja.as_of, $s.game_data.as_of, $j.total_entries)
            $freshLabel.ForeColor = $green
        } else {
            $freshLabel.Text = "Databases: none yet (run launchers\Update Database.bat to scrape, or Import bundled DB)."
            $freshLabel.ForeColor = $muted
        }
    } catch { $freshLabel.Text = "Databases: (status unavailable)"; $freshLabel.ForeColor = $muted }
}

function Import-BundledDB {
    $src = Join-Path $ResourcesDir "Database\localized_knowledge.db"
    $dst = Join-Path $ProjectRoot "data_engine\localized_knowledge.db"
    if (-not (Test-Path $src)) {
        Notify "Import bundled DB" "No bundled database found at:`n$src`n`nDrop a scraped localized_knowledge.db there first."
        return
    }
    try {
        Copy-Item $src $dst -Force
        foreach ($cache in @("poe2db_cache.sqlite","poeninja_cache.sqlite")) {
            $cs = Join-Path $ResourcesDir "Database\$cache"
            if (Test-Path $cs) { Copy-Item $cs (Join-Path $ProjectRoot "data_engine\$cache") -Force }
        }
        Log "Imported bundled database into data_engine/."
        Refresh-Freshness
        Notify "Import bundled DB" "Bundled database imported. Freshness updated above."
    } catch { Notify "Import bundled DB" "Failed: $($_.Exception.Message)" }
}

# ---- bottom buttons ----
$verifyBtn = New-Object System.Windows.Forms.Button
$verifyBtn.Text="Verify All (Repair)"; $verifyBtn.Location=New-Object System.Drawing.Point(12,772); $verifyBtn.Size=New-Object System.Drawing.Size(150,32)
$verifyBtn.FlatStyle="Flat"; $verifyBtn.BackColor=$card; $verifyBtn.ForeColor=$fg; $form.Controls.Add($verifyBtn)

$importDbBtn = New-Object System.Windows.Forms.Button
$importDbBtn.Text="Import bundled DB"; $importDbBtn.Location=New-Object System.Drawing.Point(170,772); $importDbBtn.Size=New-Object System.Drawing.Size(160,32)
$importDbBtn.FlatStyle="Flat"; $importDbBtn.BackColor=$card; $importDbBtn.ForeColor=$fg; $form.Controls.Add($importDbBtn)
$importDbBtn.Add_Click({ Import-BundledDB })

$refreshDatesBtn = New-Object System.Windows.Forms.Button
$refreshDatesBtn.Text="Refresh dates"; $refreshDatesBtn.Location=New-Object System.Drawing.Point(338,772); $refreshDatesBtn.Size=New-Object System.Drawing.Size(120,32)
$refreshDatesBtn.FlatStyle="Flat"; $refreshDatesBtn.BackColor=$card; $refreshDatesBtn.ForeColor=$fg; $form.Controls.Add($refreshDatesBtn)
$refreshDatesBtn.Add_Click({ Refresh-Freshness })

$finishBtn = New-Object System.Windows.Forms.Button
$finishBtn.Text="Finish (save & launch)"; $finishBtn.Location=New-Object System.Drawing.Point(520,772); $finishBtn.Size=New-Object System.Drawing.Size(190,32)
$finishBtn.FlatStyle="Flat"; $finishBtn.BackColor=$gold; $finishBtn.ForeColor=[System.Drawing.Color]::Black
$finishBtn.Font=New-Object System.Drawing.Font("Segoe UI",9,[System.Drawing.FontStyle]::Bold)
$form.Controls.Add($finishBtn)

$closeBtn = New-Object System.Windows.Forms.Button
$closeBtn.Text="Close"; $closeBtn.Location=New-Object System.Drawing.Point(720,772); $closeBtn.Size=New-Object System.Drawing.Size(84,32)
$closeBtn.FlatStyle="Flat"; $closeBtn.BackColor=$card; $closeBtn.ForeColor=$fg
$closeBtn.Add_Click({ $form.Close() }); $form.Controls.Add($closeBtn)

$finishBtn.Add_Click({
    try {
        # save profile (same as Save profile)
        $cfg = Read-Config
        if ($acctBox.Text.Trim()) { Write-ConfigValue $cfg "account_name" $acctBox.Text.Trim() }
        if ($leagueBox.Text.Trim()) { Write-ConfigValue $cfg "league" $leagueBox.Text.Trim() }
        if ($brainCombo.SelectedItem) { $bs=[string]$brainCombo.SelectedItem; Write-ConfigValue $cfg "ai_brain" $bs }
        Save-Config $cfg
        Log "Profile saved. Setup finished."
        $launch = [System.Windows.Forms.MessageBox]::Show(
            "Setup saved. Anything you skipped can be added later by re-running this installer.`n`nLaunch Kalandra now?",
            "Finish", [System.Windows.Forms.MessageBoxButtons]::YesNo)
        if ($launch -eq [System.Windows.Forms.DialogResult]::Yes) {
            $bat = Join-Path $ProjectRoot "launchers\Windows Diagnostic Launcher.bat"
            if (Test-Path $bat) { Start-Process -FilePath $bat -WorkingDirectory $ProjectRoot }
        }
        $form.Close()
    } catch { Log "Finish error: $($_.Exception.Message)" }
})

# ---- profile load/save ----
function Load-Profile {
    $cfg = Read-Config
    if ($cfg.PSObject.Properties["account_name"]) { $acctBox.Text = [string]$cfg.account_name }
    $lg = "Standard"; if ($cfg.PSObject.Properties["league"] -and $cfg.league) { $lg = [string]$cfg.league }
    $leagueBox.Text = $lg
    $b = "gemini"; if ($cfg.PSObject.Properties["ai_brain"] -and $cfg.ai_brain) { $b = [string]$cfg.ai_brain }
    $brainCombo.SelectedItem = $b
}
$saveProfBtn.Add_Click({
    try {
        $cfg = Read-Config
        if ($acctBox.Text.Trim()) { Write-ConfigValue $cfg "account_name" $acctBox.Text.Trim() }
        if ($leagueBox.Text.Trim()) { Write-ConfigValue $cfg "league" $leagueBox.Text.Trim() }
        if ($brainCombo.SelectedItem) { $bs=[string]$brainCombo.SelectedItem; Write-ConfigValue $cfg "ai_brain" $bs }
        Save-Config $cfg
        Log "Profile saved to config.json."
        Notify "Profile" "Saved account name, league and AI brain."
    } catch { Log "Save profile failed: $($_.Exception.Message)" }
})

# ---- verify all (repair) ----
$verifyBtn.Add_Click({
    Log "=== Verify All (repair check) ==="
    $cfg = Read-Config
    $pass = 0; $fail = 0
    foreach ($r in $rows) {
        $comp = $r.Comp; $chk = $comp.Check; $st = $r.Status
        if ($chk.Kind -eq "none") { continue }
        $ok = $false; $msg = ""
        try {
            if ($chk.Kind -eq "python") { $ok = [bool](Find-Python); $msg = if($ok){"Python OK"}else{"Python missing"} }
            elseif ($chk.Kind -eq "pip") {
                $o = Invoke-Py @("-c","import PyQt6, requests, bs4, numpy, keyring; print('OK')")
                $ok = ($o -match "OK"); $msg = if($ok){"packages OK"}else{"packages missing"}
            }
            else {
                # file kind: try saved config path, then default locations
                $folder = $null
                if ($cfg.PSObject.Properties[$chk.CfgKey] -and $cfg.($chk.CfgKey)) { $folder = [string]$cfg.($chk.CfgKey) }
                if ($folder -and (Test-Path $folder) -and -not (Get-Item $folder).PSIsContainer) { $folder = Split-Path -Parent $folder }
                if (-not $folder) { $folder = Detect-Default $comp }
                if ($folder) {
                    $res = Test-FileComponent $chk $folder
                    $ok = $res.Ok
                    if ($ok) { Write-ConfigValue $cfg $chk.CfgKey $res.Save; $msg = "found: $($res.Save)" }
                    else { $msg = "not found in $folder" }
                } else { $msg = "no location set" }
            }
        } catch { $msg = "error: $($_.Exception.Message)" }
        if ($ok) { $pass++; $st.Text = "OK: $msg"; $st.ForeColor=$green; Log ("  [OK]   " + $comp.Id + " - " + $msg) }
        else { $fail++; $st.Text = "NEEDS ATTENTION: $msg"; $st.ForeColor=$red; Log ("  [FAIL] " + $comp.Id + " - " + $msg) }
    }
    Save-Config $cfg
    Log "=== Verify complete: $pass OK, $fail need attention ==="
    Notify "Verify All" "$pass OK, $fail need attention. See the log for details."
})

Load-Profile
Refresh-Freshness
Log "Ready. Each row: Install (bundled file in 'Additional Resources' if present, else download)."
Log "Check Location verifies the needed file; Connect Account stores API keys; Import bundled DB"
Log "loads a pre-scraped database. Database 'current as of' dates show up top. Version v$Version."

[void]$form.ShowDialog()
