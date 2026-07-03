# =====================================================================
#  Build-Offline-Bundle.ps1
#  Run this ONCE on any internet-connected Windows PC to assemble an
#  offline copy of everything the installer needs, into  installer\bundled\ .
#  After that, Kalandra-Setup.ps1 can run on a brand-new, OFFLINE machine:
#  it prefers files in bundled\ over downloading.
#
#  What it gathers:
#    - The Python 3.12 Windows installer (python.org).
#    - All pip wheels for requirements.txt (python -m pip download).
#  (Companion APPS are still fetched at install time, since you choose which
#   to include; re-run with -Apps to also pre-download their latest releases.)
#
#  Usage:   powershell -ExecutionPolicy Bypass -File installer\Build-Offline-Bundle.ps1
#           ...add  -Apps  to also bundle PoB2 / Exiled Exchange 2 / Xiletrade / Lailloken.
# =====================================================================
param([switch]$Apps)

$ErrorActionPreference = "Stop"
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12

$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
# Populate the user-facing "Additional Resources" tree so the installer finds
# these offline (it prefers a bundled file there over downloading).
$ResDir      = Join-Path $ProjectRoot "Additional Resources"
$BundledDir  = Join-Path $ResDir "Python"
$WheelsDir   = Join-Path $ResDir "Python Packages (wheels)"
$AppsRoot    = $ResDir
$PythonUrl   = "https://www.python.org/ftp/python/3.12.13/python-3.12.13-amd64.exe"

New-Item -ItemType Directory -Force -Path $BundledDir,$WheelsDir | Out-Null

Write-Host "1) Python installer ..."
$pyExe = Join-Path $BundledDir "python-3.12.13-amd64.exe"
if (-not (Test-Path $pyExe)) {
    Invoke-WebRequest -Uri $PythonUrl -OutFile $pyExe -UseBasicParsing
}
Write-Host "   -> $pyExe"

Write-Host "2) pip wheels for requirements.txt ..."
$req = Join-Path $ProjectRoot "requirements.txt"
$py = $null
foreach ($c in @("py -3.12","py -3","python")) {
    try { $p=$c.Split(" "); & $p[0] $p[1..($p.Length-1)] --version 2>$null; if ($LASTEXITCODE -eq 0){ $py=$c; break } } catch {}
}
if ($py) {
    $p = $py.Split(" ")
    & $p[0] $p[1..($p.Length-1)] -m pip download -r $req -d $WheelsDir
    Write-Host "   -> wheels in $WheelsDir"
} else {
    Write-Host "   (Python not on this PC yet - install it, then re-run to gather wheels.)"
}

function Get-LatestAsset($owner,$repo,$patterns){
    $rels = Invoke-RestMethod -Uri "https://api.github.com/repos/$owner/$repo/releases?per_page=10" -Headers @{ "User-Agent"="Kalandra" }
    foreach($rel in $rels){ foreach($pat in $patterns){ foreach($a in $rel.assets){ if($a.name -match $pat){ return @($a.name,$a.browser_download_url) } } } }
    return $null
}

if ($Apps) {
    Write-Host "3) Companion app installers (into Additional Resources) ..."
    # owner, repo, patterns, Additional Resources subfolder
    $apps = @(
        @("PathOfBuildingCommunity","PathOfBuilding-PoE2", @("setup.*\.exe$","\.exe$","win.*\.zip$"), "Path of Building 2"),
        @("Kvan7","Exiled-Exchange-2", @("Setup.*\.exe$","\.exe$"), "Exiled Exchange 2"),
        @("maxensas","xiletrade", @("win.*Setup.*\.exe$","Setup.*\.exe$","\.zip$"), "Xiletrade"),
        @("Lailloken","Exile-UI", @("\.zip$","\.exe$"), "Lailloken Exile-UI")
    )
    foreach($a in $apps){
        try {
            $sub = Join-Path $AppsRoot $a[3]
            New-Item -ItemType Directory -Force -Path $sub | Out-Null
            $res = Get-LatestAsset $a[0] $a[1] $a[2]
            if ($res) {
                $dest = Join-Path $sub $res[0]
                if (-not (Test-Path $dest)) { Invoke-WebRequest -Uri $res[1] -OutFile $dest -UseBasicParsing }
                Write-Host "   -> $($a[3]): $($res[0])"
            } else { Write-Host "   -> $($a[3]): no matching asset" }
        } catch { Write-Host "   -> $($a[3]): $($_.Exception.Message)" }
    }
}

Write-Host ""
Write-Host "Offline resources assembled under: $ResDir"
Write-Host "To bundle your database too, copy data_engine\localized_knowledge.db into"
Write-Host "  'Additional Resources\Database\'. Then copy the WHOLE Kalandra folder to the"
Write-Host "offline PC and run Setup.bat (each Install button uses the local file)."
