param(
    [string]$PythonExe = '',
    [switch]$AllMaps,
    [switch]$Terrain,
    [switch]$RefreshMaps,
    [switch]$Dev,
    [switch]$NoLaunch,
    [switch]$SkipCheck
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = $null
$taskPrefix = @()
if ($PythonExe) {
    & $PythonExe -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else 1)'
    if ($LASTEXITCODE -ne 0) { throw '-PythonExe must point to Python 3.12.' }
    $taskPython = $PythonExe
}
$taskCandidates = @((Join-Path $PSScriptRoot '.venv/Scripts/python.exe'), 'py', 'python', 'python3')
foreach ($taskCandidate in $taskCandidates) {
    if ($taskPython) { break }
    if (-not (Get-Command $taskCandidate -ErrorAction SilentlyContinue)) { continue }
    $taskProbePrefix = @()
    if ($taskCandidate -eq 'py') { $taskProbePrefix = @('-3.12') }
    try {
        & $taskCandidate @taskProbePrefix -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else 1)' 2>$null
    } catch { continue }
    if ($LASTEXITCODE -eq 0) { $taskPython = $taskCandidate; $taskPrefix = $taskProbePrefix; break }
}
if (-not $taskPython) {
    throw 'Python 3.12 is required. Install it from python.org with Tcl/Tk and the Python launcher, then rerun Setup.ps1.'
}
$taskArguments = @('scripts/setup_local.py')
if ($AllMaps) { $taskArguments += @('--maps', 'all') }
if ($Terrain) { $taskArguments += '--terrain' }
if ($RefreshMaps) { $taskArguments += '--refresh-maps' }
if ($Dev) { $taskArguments += '--dev' }
if ($SkipCheck) { $taskArguments += '--skip-check' }
if (-not $NoLaunch) { $taskArguments += '--launch' }
& $taskPython @taskPrefix @taskArguments
if ($LASTEXITCODE -ne 0) { throw 'Setup failed. Read the step error above, then rerun the same command.' }
