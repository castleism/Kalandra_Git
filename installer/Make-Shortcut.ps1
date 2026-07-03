# Creates a "Kalandra" shortcut on the Desktop that launches the overlay
# silently (pythonw) with the orb icon, then forces Windows to refresh its
# icon cache so the new icon shows immediately (Explorer otherwise keeps
# serving the OLD cached icon even after the shortcut points to the new file).
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$desktop = [Environment]::GetFolderPath('Desktop')
$pyw = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = "pythonw.exe" }
$lnk = Join-Path $desktop "Kalandra.lnk"

# Recreate the shortcut from scratch so Explorer treats it as new.
if (Test-Path $lnk) { Remove-Item $lnk -Force -ErrorAction SilentlyContinue }

$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = $pyw
$s.Arguments = '"' + (Join-Path $ProjectRoot "main.py") + '"'
$s.WorkingDirectory = $ProjectRoot
$ico = Join-Path $ProjectRoot "gui_overlay\assets\kalandra.ico"
if (Test-Path $ico) { $s.IconLocation = "$ico,0" }
$s.Description = "Kalandra - Path of Exile 2 overlay companion"
$s.Save()
Write-Host "Created Desktop shortcut: $lnk"

# --- Force a Windows icon-cache refresh so the new icon appears now ---
try {
    Add-Type -Namespace Win32 -Name IconRefresh -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("shell32.dll")]
public static extern void SHChangeNotify(int eventId, int flags, System.IntPtr item1, System.IntPtr item2);
'@ -ErrorAction SilentlyContinue
    # SHCNE_ASSOCCHANGED (0x08000000) tells the shell icons/associations changed.
    [Win32.IconRefresh]::SHChangeNotify(0x08000000, 0x0000, [System.IntPtr]::Zero, [System.IntPtr]::Zero)
} catch { }

# Rebuild the per-user icon cache (works on Windows 10/11; harmless otherwise).
try { Start-Process -WindowStyle Hidden -FilePath "ie4uinit.exe" -ArgumentList "-show" -ErrorAction SilentlyContinue } catch { }
try { Start-Process -WindowStyle Hidden -FilePath "ie4uinit.exe" -ArgumentList "-ClearIconCache" -ErrorAction SilentlyContinue } catch { }

Write-Host "Requested an icon-cache refresh. If the desktop still shows the old"
Write-Host "icon, press F5 on the desktop, or sign out/in once."
