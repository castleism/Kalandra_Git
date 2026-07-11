# Registers Kalandra as a proper installed Windows program:
#   1. a Start Menu shortcut  -> makes it findable from the Start/home search
#   2. an Apps & Features entry -> shows up in "Installed apps" with an
#      uninstall option, exactly like any other program
#   3. a Desktop shortcut       -> the familiar double-click icon
# All three launch the overlay silently (pythonw) with the orb icon, then we
# refresh the Windows icon cache so the new icon shows immediately.
#
# Everything here is per-user (HKCU + the user's own Start Menu/Desktop), so it
# needs NO administrator rights. Run it again any time to repair the entries.

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

# --- Resolve the silent Python launcher --------------------------------------
$pyw = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\pythonw.exe"
if (-not (Test-Path $pyw)) {
    $found = (Get-Command pythonw.exe -ErrorAction SilentlyContinue |
              Select-Object -First 1)
    $pyw = if ($found) { $found.Source } else { "pythonw.exe" }
}

$mainPy = Join-Path $ProjectRoot "main.py"
$ico    = Join-Path $ProjectRoot "gui_overlay\assets\kalandra.ico"
$hasIco = Test-Path $ico

# --- Read the version so Apps & Features shows the right number ---------------
$version = "0.1.0"
try {
    $vLine = Select-String -Path (Join-Path $ProjectRoot "version.py") `
        -Pattern 'KALANDRA_VERSION\s*=\s*"([^"]+)"' -ErrorAction Stop |
        Select-Object -First 1
    if ($vLine) { $version = $vLine.Matches[0].Groups[1].Value }
} catch { }

$ws = New-Object -ComObject WScript.Shell

function New-KalandraShortcut([string]$LnkPath) {
    if (Test-Path $LnkPath) {
        Remove-Item $LnkPath -Force -ErrorAction SilentlyContinue
    }
    $parent = Split-Path -Parent $LnkPath
    if (-not (Test-Path $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    $s = $ws.CreateShortcut($LnkPath)
    $s.TargetPath       = $pyw
    $s.Arguments        = '"' + $mainPy + '"'
    $s.WorkingDirectory = $ProjectRoot
    if ($hasIco) { $s.IconLocation = "$ico,0" }
    $s.Description      = "Kalandra - Path of Exile 2 overlay companion"
    $s.WindowStyle      = 7            # start minimized; the overlay is frameless
    $s.Save()
}

# --- 1. Start Menu shortcut (this is what Start/home search indexes) ---------
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$startLnk  = Join-Path $startMenu "Kalandra.lnk"
New-KalandraShortcut $startLnk
Write-Host "Created Start Menu shortcut: $startLnk"

# --- 2. Desktop shortcut -----------------------------------------------------
$desktop    = [Environment]::GetFolderPath('Desktop')
$desktopLnk = Join-Path $desktop "Kalandra.lnk"
New-KalandraShortcut $desktopLnk
Write-Host "Created Desktop shortcut: $desktopLnk"

# --- 3. Apps & Features (Add/Remove Programs) registration -------------------
# HKCU so no admin is needed; this is the entry that makes Windows treat
# Kalandra as an installed program you can find and uninstall in Settings.
try {
    $uninstKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Kalandra"
    New-Item -Path $uninstKey -Force | Out-Null
    $uninstScript = Join-Path $ProjectRoot "installer\Kalandra-Uninstall.ps1"
    $uninstCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$uninstScript`""
    $props = @{
        DisplayName     = "Kalandra"
        DisplayVersion  = $version
        Publisher       = "Kalandra (free community tool)"
        InstallLocation = $ProjectRoot
        DisplayIcon     = $(if ($hasIco) { $ico } else { $pyw })
        UninstallString = $uninstCmd
        URLInfoAbout    = "https://github.com/castleism/Kalandra_Git"
        NoModify        = 1
        NoRepair        = 1
    }
    foreach ($k in $props.Keys) {
        $type = if ($props[$k] -is [int]) { 'DWord' } else { 'String' }
        Set-ItemProperty -Path $uninstKey -Name $k -Value $props[$k] -Type $type
    }
    Write-Host "Registered in Apps & Features as 'Kalandra' v$version"
} catch {
    Write-Host "Apps & Features registration skipped: $($_.Exception.Message)"
}

# --- HKCU marker so Setup/the wizard can always find this copy ---------------
try {
    New-Item -Path "HKCU:\Software\Kalandra" -Force | Out-Null
    Set-ItemProperty -Path "HKCU:\Software\Kalandra" -Name "InstallPath" `
        -Value $ProjectRoot
    Set-ItemProperty -Path "HKCU:\Software\Kalandra" -Name "Version" `
        -Value $version
} catch { }

# --- Force a Windows icon-cache refresh so the new icon appears now ----------
try {
    Add-Type -Namespace Win32 -Name IconRefresh -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("shell32.dll")]
public static extern void SHChangeNotify(int eventId, int flags, System.IntPtr item1, System.IntPtr item2);
'@ -ErrorAction SilentlyContinue
    # SHCNE_ASSOCCHANGED (0x08000000): the shell re-reads icons/associations.
    [Win32.IconRefresh]::SHChangeNotify(0x08000000, 0x0000, `
        [System.IntPtr]::Zero, [System.IntPtr]::Zero)
} catch { }
try { Start-Process -WindowStyle Hidden -FilePath "ie4uinit.exe" -ArgumentList "-show" -ErrorAction SilentlyContinue } catch { }
try { Start-Process -WindowStyle Hidden -FilePath "ie4uinit.exe" -ArgumentList "-ClearIconCache" -ErrorAction SilentlyContinue } catch { }

Write-Host ""
Write-Host "Done. Kalandra is now a searchable installed program:"
Write-Host "  * Press the Start/home button and type 'Kalandra' to launch it."
Write-Host "  * It also appears in Settings > Apps > Installed apps."
Write-Host "If search doesn't find it within a minute, sign out and back in once"
Write-Host "(Windows rebuilds its search index on login)."
