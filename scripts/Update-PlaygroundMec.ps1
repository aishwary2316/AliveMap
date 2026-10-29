param([string]$SshConfig='', [string]$HostAlias='alivemap-mec')
$ErrorActionPreference='Stop'
$repoRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
if(-not $SshConfig){$SshConfig=Join-Path $repoRoot '.local/ssh_config'}
$Host.UI.RawUI.WindowTitle='AliveMap - update managed MEC API'
& (Join-Path $repoRoot '.venv/Scripts/python.exe') -m scripts.package_playground_update
if($LASTEXITCODE -ne 0){throw 'Update preparation failed; nothing deployed.'}
$OutputEncoding=[Text.UTF8Encoding]::new($false)
Write-Host 'Updates ONLY the managed AliveMap API; stored experiments and network configuration are preserved.' -ForegroundColor Cyan
Write-Host 'Enter MEC sudo password here, then the SSH password(s) for the selected host. No credentials go to chat.'
$secure=Read-Host 'MEC sudo password' -AsSecureString
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $inputText=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)+"`n"+[IO.File]::ReadAllText((Join-Path $repoRoot '.local/playground-update-command.py'))+"`n"
    $inputText | & ssh -T -F $SshConfig -o ConnectTimeout=60 -o ServerAliveInterval=15 $HostAlias "sudo -S -p '' /usr/bin/python3 -I -" | Tee-Object -FilePath (Join-Path $repoRoot '.local/playground-update-result.json')
    if($LASTEXITCODE -ne 0){throw 'API update did not complete. Inspect the error; existing configuration is guarded.'}
    Write-Host 'ALIVEMAP_API_UPDATED. Return to Codex.' -ForegroundColor Green
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $secure.Dispose()
    Remove-Variable inputText -ErrorAction SilentlyContinue
}
