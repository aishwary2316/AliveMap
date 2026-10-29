param(
    [string]$SshConfig = '',
    [string]$HostAlias = 'alivemap-mec',
    [ValidateRange(1024, 65535)][int]$LocalPort = 18767,
    [switch]$RecoverBaseline
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
if (-not $SshConfig) { $SshConfig = Join-Path $repoRoot '.local/ssh_config' }
if (-not (Test-Path -LiteralPath $SshConfig -PathType Leaf)) {
    throw 'Create your private SSH host/jump-host configuration first; see docs/playground.md.'
}
$taskPython = Join-Path $repoRoot '.venv/Scripts/python.exe'
$taskPackageArgs = @((Join-Path $PSScriptRoot 'package_playground.py'))
if ($RecoverBaseline) { $taskPackageArgs += '--recover-baseline' }
& $taskPython @taskPackageArgs
if ($LASTEXITCODE -ne 0) { throw 'Deployment preparation failed.' }
$Host.UI.RawUI.WindowTitle = 'AliveMap - Playground MEC (passwords; keep open)'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Write-Host 'Enter both SSH passwords. Keep this window open after Uvicorn starts.' -ForegroundColor Cyan
Write-Host 'Adds loopback service 8767; original API 8765 and view 8766 are preserved.'
if ($RecoverBaseline) { Write-Host 'If the reviewed original API is absent, starts its unchanged source. No existing process is stopped.' -ForegroundColor Yellow }
$taskForward = "127.0.0.1:${LocalPort}:127.0.0.1:8767"
Get-Content -LiteralPath (Join-Path $repoRoot '.local/deploy-playground.sh') -Raw -Encoding UTF8 |
    & ssh -T -F $SshConfig -o ConnectTimeout=600 -o ExitOnForwardFailure=yes -L $taskForward $HostAlias 'bash -s'
if ($LASTEXITCODE -ne 0) { throw 'SSH/deployment ended with an error. Read the message above; no existing listener is stopped.' }
