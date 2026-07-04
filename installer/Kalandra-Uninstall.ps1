# =====================================================================
#  Kalandra - clean uninstaller (run via "Uninstall Kalandra.bat").
#
#  Walks through every bundled add-on under tools\ and asks, per tool:
#    [K]eep here   - leave it inside the Kalandra folder
#    [M]ove out    - relocate it to %LOCALAPPDATA%\Programs\<name> (the
#                    standard per-user install spot) so it survives
#                    Kalandra's removal
#    [D]elete      - remove it with Kalandra
#  Then asks about your data (data_engine: builds, ledgers, chat threads,
#  character folios) and finally about the Kalandra program itself.
#  Nothing is deleted without an explicit answer.
# =====================================================================
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
Write-Host "=== KALANDRA UNINSTALLER ===" -ForegroundColor Yellow
Write-Host "Kalandra folder: $Root"
Write-Host ""

function Ask($prompt, $choices) {
    while ($true) {
        $a = (Read-Host "$prompt $choices").Trim().ToUpper()
        if ($a) { return $a[0] }
    }
}

# --- 0. Mode: this tool doubles as REPAIR -------------------------------
switch (Ask "Repair Kalandra, or Uninstall it?" "[R/U]") {
    "R" {
        Write-Host ""
        Write-Host "=== REPAIR MODE ===" -ForegroundColor Green
        # a) Python deps
        $py = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
        if (-not (Test-Path $py)) { $py = "python" }
        Write-Host "[1/5] Reinstalling Python dependencies (requirements.txt)..."
        & $py -m pip install -r (Join-Path $Root "requirements.txt") --quiet
        # b) Config sanity
        Write-Host "[2/5] Checking data_engine\config.json..."
        $cfg = Join-Path $Root "data_engine\config.json"
        if (Test-Path $cfg) {
            try { Get-Content $cfg -Raw | ConvertFrom-Json | Out-Null
                  Write-Host "      config parses OK" }
            catch { Copy-Item $cfg "$cfg.corrupt.bak" -Force
                    Remove-Item $cfg -Force
                    Write-Host "      config was CORRUPT - backed up to config.json.corrupt.bak; Kalandra will rebuild defaults on next launch" -ForegroundColor Yellow }
        }
        # c) Configured tool paths still exist?
        Write-Host "[3/5] Checking configured tool paths..."
        if (Test-Path $cfg) {
            $c = Get-Content $cfg -Raw | ConvertFrom-Json
            foreach ($k in @("pob_exe","pob_install_dir","pob_builds_dir","overlay2_exe")) {
                $v = $c.$k
                if ($v -and -not (Test-Path $v)) {
                    Write-Host "      MISSING: $k -> $v  (re-point it in Settings)" -ForegroundColor Red
                }
            }
        }
        # d) Stale bytecode
        Write-Host "[4/5] Clearing stale __pycache__..."
        Get-ChildItem $Root -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch "\\tools\\" } |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        # e) Shortcut + self-test
        Write-Host "[5/5] Recreating the desktop shortcut..."
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "installer\Make-Shortcut.ps1")
        switch (Ask "Run the self-test suite now?" "[Y/N]") {
            "Y" { & $py (Join-Path $Root "tests\stress_test.py") }
        }
        Write-Host ""
        Write-Host "Repair finished. If the overlay still misbehaves, run"
        Write-Host "launchers\'Windows Diagnostic Launcher.bat' and read the console."
        exit 0
    }
}

# --- 1. Bundled add-ons -------------------------------------------------
$toolsDir = Join-Path $Root "tools"
$dest = Join-Path $env:LOCALAPPDATA "Programs"
if (Test-Path $toolsDir) {
    Get-ChildItem $toolsDir -Directory | ForEach-Object {
        $name = $_.Name
        $size = "{0:N0} MB" -f ((Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue |
                                 Measure-Object Length -Sum).Sum / 1MB)
        Write-Host ""
        Write-Host "Add-on: $name ($size)" -ForegroundColor Cyan
        switch (Ask "  Keep here, Move out, or Delete?" "[K/M/D]") {
            "M" {
                $to = Join-Path $dest $name
                if (Test-Path $to) {
                    Write-Host "  ! $to already exists - keeping in place." -ForegroundColor Red
                } else {
                    New-Item -ItemType Directory -Force -Path $dest | Out-Null
                    Move-Item $_.FullName $to
                    Write-Host "  -> moved to $to" -ForegroundColor Green
                    Write-Host "     (re-point any shortcuts/paths at the new location)"
                }
            }
            "D" {
                Remove-Item $_.FullName -Recurse -Force
                Write-Host "  -> deleted" -ForegroundColor Green
            }
            default { Write-Host "  -> kept in place" }
        }
    }
}

# --- 2. Your data -------------------------------------------------------
$dataDir = Join-Path $Root "data_engine"
if (Test-Path $dataDir) {
    Write-Host ""
    Write-Host "Your data (data_engine): saved builds, price ledger, grind logs,"
    Write-Host "chat threads, character folios, knowledge DB." -ForegroundColor Cyan
    switch (Ask "  Keep (move to Documents\Kalandra-Data), or Delete?" "[K/D]") {
        "D" { Remove-Item $dataDir -Recurse -Force; Write-Host "  -> data deleted" }
        default {
            $keep = Join-Path ([Environment]::GetFolderPath('MyDocuments')) "Kalandra-Data"
            if (-not (Test-Path $keep)) { Move-Item $dataDir $keep
                Write-Host "  -> data preserved at $keep" -ForegroundColor Green }
            else { Write-Host "  ! $keep exists - data left in place." -ForegroundColor Red }
        }
    }
}

# --- 3. Shortcut + the app itself ----------------------------------------
$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) "Kalandra.lnk"
if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host "Desktop shortcut removed." }

Write-Host ""
switch (Ask "Delete the Kalandra program folder itself? (final step)" "[Y/N]") {
    "Y" {
        Write-Host "Removing $Root after this window closes..."
        # Self-delete via a detached cmd (a running script can't delete itself).
        $cmd = "ping -n 3 127.0.0.1 >nul & rmdir /s /q `"$Root`""
        Start-Process cmd.exe -ArgumentList "/c", $cmd -WindowStyle Hidden
        Write-Host "Goodbye, exile." -ForegroundColor Yellow
    }
    default { Write-Host "Program folder kept. Uninstall finished." }
}
