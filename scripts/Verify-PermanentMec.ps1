param([string]$SshConfig = '', [string]$HostAlias = 'alivemap-mec')
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
if(-not $SshConfig){$SshConfig=Join-Path $repoRoot '.local/ssh_config'}
$Host.UI.RawUI.WindowTitle='AliveMap - verify permanent API recovery'
$OutputEncoding=[Text.UTF8Encoding]::new($false)
Write-Host 'Tests a controlled crash/restart of ONLY alivemap-playground.service.' -ForegroundColor Cyan
Write-Host 'Requires zero active experiments. Checks stored incident recovery and preservation of existing services.'
Write-Host 'Enter MEC sudo password first, then both SSH passwords. Input is hidden.'
$taskSecure=Read-Host 'MEC sudo password' -AsSecureString
$taskPointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($taskSecure)
try {
    $taskInput=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($taskPointer)+"`n"+[IO.File]::ReadAllText((Join-Path $repoRoot 'deployment/verify_permanent.py'))+"`n"
    $taskInput | & ssh -T -F $SshConfig -o ConnectTimeout=60 -o ServerAliveInterval=15 $HostAlias "sudo -S -p '' /usr/bin/python3 -I -" |
        Tee-Object -FilePath (Join-Path $repoRoot '.local/permanent-recovery-result.json')
    if($LASTEXITCODE -ne 0){throw 'Recovery verification failed; inspect the error above.'}
    Write-Host 'PERMANENT_RECOVERY_VERIFIED. Return to Codex.' -ForegroundColor Green
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($taskPointer)
    $taskSecure.Dispose()
    Remove-Variable taskInput -ErrorAction SilentlyContinue
}
