# =====================================================================
#  Kalandra - Repair / Uninstall (run via launchers\"Uninstall Kalandra.bat"
#  or Setup.bat's [R]/[U] offer).
#  Uninstall walks each bundled add-on (Keep / Move out / Delete), your
#  data, then the app itself. Nothing is deleted without an explicit
#  answer, and a git DEVELOPMENT REPO is never deleted by this script.
# =====================================================================
$ErrorActionPreference = "Continue"
$Root = $null
try { $Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) } catch { }
if (-not $Root -or -not (Test-Path (Join-Path $Root "version.py"))) {
    $Root = (Get-Location).Path
}
Set-Location $Root
$IsRepo = Test-Path (Join-Path $Root ".git")
Write-Host "=== KALANDRA REPAIR / UNINSTALL ===" -ForegroundColor Yellow
Write-Host "Kalandra folder: $Root"
if ($IsRepo) {
    Write-Host "NOTE: this folder is a GIT REPOSITORY (development copy)." -ForegroundColor Cyan
    Write-Host "The final 'delete program folder' step is DISABLED for repos" -ForegroundColor Cyan
    Write-Host "so your project history and uncommitted work stay safe." -ForegroundColor Cyan
}
Write-Host ""

function Ask($prompt, $choices) {
    while ($true) {
        $a = (Read-Host "$prompt $choices")
        if ($a) { return $a.Trim().ToUpper()[0] }
    }
}

function Resolve-Python {
    # The REAL interpreter, or $null. Never trusts the Microsoft Store
    # redirector stub (a fake python.exe every Windows has, Python installed
    # or not) - trusting it made cleanup steps silently do nothing.
    foreach ($k in @((Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
                     "C:\Python312\python.exe")) {
        if (Test-Path $k) { return $k }
    }
    foreach ($c in @("py","python")) {
        try {
            $src = (Get-Command $c -ErrorAction Stop).Source
            if ($src -and $src -match "\\WindowsApps\\") { continue }
            $v = & $c --version 2>$null
            if ($LASTEXITCODE -eq 0 -and "$v" -match "Python 3") { return $c }
        } catch { }
    }
    return $null
}

# --- 0. Mode ------------------------------------------------------------
$mode = Ask "Repair Kalandra, or Uninstall it?" "[R/U]"
if ($mode -eq "R") {
    Write-Host ""
    Write-Host "=== REPAIR MODE ===" -ForegroundColor Green
    $py = Resolve-Python
    if (-not $py) {
        Write-Host "No real Python found (Windows' Store stub does not count)." -ForegroundColor Red
        Write-Host "Run Setup.bat and install Python first - nothing to repair with." -ForegroundColor Red
        exit 1
    }
    Write-Host "[1/5] Reinstalling Python dependencies..."
    & $py -m pip install -r (Join-Path $Root "requirements.txt") --quiet
    Write-Host "[2/5] Checking data_engine\config.json..."
    $cfg = Join-Path $Root "data_engine\config.json"
    if (Test-Path $cfg) {
        try { Get-Content $cfg -Raw | ConvertFrom-Json | Out-Null
              Write-Host "      config parses OK" }
        catch { Copy-Item $cfg "$cfg.corrupt.bak" -Force
                Remove-Item $cfg -Force
                Write-Host "      config was CORRUPT - backed up; defaults rebuild on next launch" -ForegroundColor Yellow }
    }
    Write-Host "[3/5] Checking configured tool paths..."
    if (Test-Path $cfg) {
        try {
            $c = Get-Content $cfg -Raw | ConvertFrom-Json
            foreach ($k in @("pob_exe","pob_install_dir","pob_builds_dir","overlay2_exe")) {
                $v = $c.$k
                if ($v -and -not (Test-Path $v)) {
                    Write-Host "      MISSING: $k -> $v" -ForegroundColor Red
                }
            }
        } catch { }
    }
    Write-Host "[4/5] Clearing stale __pycache__..."
    Get-ChildItem $Root -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch "\\tools\\" } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "[5/5] Recreating the desktop shortcut..."
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "installer\Make-Shortcut.ps1")
    if ((Ask "Run the self-test suite now?" "[Y/N]") -eq "Y") {
        & $py (Join-Path $Root "tests\stress_test.py")
    }
    Write-Host ""
    Write-Host "Repair finished."
    exit 0
}

# --- 1. Bundled add-ons ---------------------------------------------------
$toolsDir = Join-Path $Root "tools"
$dest = $null
if ($env:LOCALAPPDATA) { $dest = Join-Path $env:LOCALAPPDATA "Programs" }
if (Test-Path $toolsDir) {
    $addons = @(Get-ChildItem -LiteralPath $toolsDir -Directory -ErrorAction SilentlyContinue)
    foreach ($a in $addons) {
        try {
            $name = $a.Name
            $sizeMB = 0
            try {
                $m = Get-ChildItem -LiteralPath $a.FullName -Recurse -File -ErrorAction SilentlyContinue |
                     Measure-Object Length -Sum
                if ($m -and $m.Sum) { $sizeMB = [math]::Round($m.Sum / 1MB) }
            } catch { }
            Write-Host ""
            Write-Host "Add-on: $name ($sizeMB MB)" -ForegroundColor Cyan
            $c = Ask "  Keep here, Move out, or Delete?" "[K/M/D]"
            if ($c -eq "M") {
                if (-not $dest) {
                    Write-Host "  ! LOCALAPPDATA unavailable - keeping in place." -ForegroundColor Red
                } else {
                    $to = Join-Path $dest $name
                    if (Test-Path $to) {
                        Write-Host "  ! $to already exists - keeping in place." -ForegroundColor Red
                    } else {
                        New-Item -ItemType Directory -Force -Path $dest | Out-Null
                        Move-Item -LiteralPath $a.FullName -Destination $to
                        Write-Host "  -> moved to $to" -ForegroundColor Green
                    }
                }
            } elseif ($c -eq "D") {
                Remove-Item -LiteralPath $a.FullName -Recurse -Force
                Write-Host "  -> deleted" -ForegroundColor Green
            } else {
                Write-Host "  -> kept in place"
            }
        } catch {
            Write-Host "  ! Skipped ($($_.Exception.Message))" -ForegroundColor Red
        }
    }
} else {
    Write-Host "No tools\ folder found - nothing bundled to remove."
}

# --- 2. Your data -----------------------------------------------------------
$dataDir = Join-Path $Root "data_engine"
if (Test-Path $dataDir) {
    Write-Host ""
    Write-Host "Your data (data_engine): builds, ledgers, chats, folios, DB." -ForegroundColor Cyan
    if ((Ask "  Keep (move to Documents\Kalandra-Data), or Delete?" "[K/D]") -eq "D") {
        Remove-Item -LiteralPath $dataDir -Recurse -Force
        Write-Host "  -> data deleted"
    } else {
        $keep = Join-Path ([Environment]::GetFolderPath('MyDocuments')) "Kalandra-Data"
        if (-not (Test-Path $keep)) {
            Move-Item -LiteralPath $dataDir -Destination $keep
            Write-Host "  -> data preserved at $keep" -ForegroundColor Green
        } else {
            Write-Host "  ! $keep exists - data left in place." -ForegroundColor Red
        }
    }
}

# --- 2b. MACHINE-LEVEL dependencies (2026-07-04: verify-fresh-install) -------
# Everything Kalandra put OUTSIDE this folder: pip packages, stored
# credentials, optionally Python itself. Cleaning these is what makes a
# fresh-install test honest.
Write-Host ""
Write-Host "Machine-level cleanup (pip packages, stored credentials, Python)" -ForegroundColor Cyan
if ((Ask "  Clean machine-level dependencies too?" "[Y/N]") -eq "Y") {
    $py = Resolve-Python
    if (-not $py) {
        Write-Host "  No real Python found (only the Store stub). The credential and" -ForegroundColor Yellow
        Write-Host "  pip steps need Python to run, so they will be skipped." -ForegroundColor Yellow
    }
    # a) Stored credentials FIRST (needs the keyring package still present).
    if ($py -and (Ask "  Remove Kalandra's stored credentials from Windows Credential Manager?" "[Y/N]") -eq "Y") {
        $pyCode = @'
import keyring
SVC = "KalandraOverlay"
ids = ["pathofexile","poeninja","poe2_forums","email","youtube","github",
       "elevenlabs","openai","gemini","anthropic","deepseek","mistral","xai",
       "email_oauth_google","pathofbuilding","maxroll","mobalytics"]
n = 0
for i in ids:
    try:
        if keyring.get_password(SVC, i) is not None:
            keyring.delete_password(SVC, i); n += 1
    except Exception:
        pass
print(f"removed {n} stored secrets")
'@
        & $py -c $pyCode
    }
    # b) pip packages (requirements + the optional extras setup can add).
    if ($py -and (Ask "  Uninstall Kalandra's Python packages (pip)?" "[Y/N]") -eq "Y") {
        $req = Join-Path $Root "requirements.txt"
        if (Test-Path $req) { & $py -m pip uninstall -y -r $req }
        foreach ($extra in @("PyQt6-WebEngine","faster-whisper","sounddevice",
                             "soundfile","pyttsx3","mss","opencv-python",
                             "openai","google-genai","pytesseract",
                             "requests-cache","keyring","websocket-client")) {
            & $py -m pip uninstall -y $extra 2>$null
        }
        Write-Host "  -> pip packages removed (errors above just mean 'was not installed')"
    }
    # c) Python 3.12 itself (per-user install the setup created). Optional —
    # other tools on the machine may use it.
    if ((Ask "  Uninstall per-user Python 3.12 itself? (only if nothing else uses it)" "[Y/N]") -eq "Y") {
        winget uninstall -e --id Python.Python.3.12 --silent
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  ! winget exit code $LASTEXITCODE - Python may NOT have been removed." -ForegroundColor Red
            Write-Host "    If it still shows in Settings > Apps > Installed apps, remove it there." -ForegroundColor Red
        }
        # The MSI uninstall leaves pip-installed files behind, and leftovers
        # make the NEXT install check look "already installed" when it isn't.
        $left = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312"
        if (Test-Path $left) {
            if ((Ask "  Leftover files remain at $left - delete them?" "[Y/N]") -eq "Y") {
                Remove-Item -LiteralPath $left -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        $still = Resolve-Python
        if ($still) {
            Write-Host "  ! A Python is STILL detectable: $still" -ForegroundColor Yellow
            Write-Host "    If that is another project's Python, the installer will (correctly) see it." -ForegroundColor Yellow
        } else {
            Write-Host "  Python no longer detectable - a fresh-install test is now honest." -ForegroundColor Green
        }
    }
    Write-Host "Machine-level cleanup done." -ForegroundColor Green
}

# --- 3. Shortcut + the app itself --------------------------------------------
$lnk = Join-Path ([Environment]::GetFolderPath('Desktop')) "Kalandra.lnk"
if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host "Desktop shortcut removed." }
try { Remove-Item -Path "HKCU:\Software\Kalandra" -Recurse -Force -ErrorAction SilentlyContinue; Write-Host "Install registration removed." } catch { }

Write-Host ""
if ($IsRepo) {
    Write-Host "Program folder NOT deleted: this is a git repository (your" -ForegroundColor Cyan
    Write-Host "project source). Delete it manually only if you truly mean to." -ForegroundColor Cyan
    Write-Host "Uninstall of add-ons/data finished."
} elseif ((Ask "Delete the Kalandra program folder itself? (final step)" "[Y/N]") -eq "Y") {
    $cmd = "ping -n 3 127.0.0.1 >nul & rmdir /s /q `"$Root`""
    Write-Host "A console window will open to remove the folder - that is us, not malware."
    Start-Process cmd.exe -ArgumentList "/c", $cmd -WindowStyle Normal
    Write-Host "Removing $Root... Goodbye, exile." -ForegroundColor Yellow
} else {
    Write-Host "Program folder kept. Uninstall finished."
}
