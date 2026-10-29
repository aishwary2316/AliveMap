param([string]$SshConfig = '', [string]$HostAlias = 'alivemap-mec')
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
if (-not $SshConfig) { $SshConfig = Join-Path $repoRoot '.local/ssh_config' }
$private = Join-Path $repoRoot '.local'
$Host.UI.RawUI.WindowTitle = 'AliveMap - install independent permanent services'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
function Reveal-Once([Security.SecureString]$SecureValue) {
    $taskPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($taskPointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($taskPointer) }
}
if (-not (Test-Path -LiteralPath (Join-Path $private 'alivemap-tunnel.token'))) {
    Write-Host 'In the NEW alivemap-mec tunnel page, copy the manual Linux run command.' -ForegroundColor Cyan
    Write-Host 'Paste that command or its token below. Input is hidden; do not paste it into chat.'
    $taskSecureToken = Read-Host 'New AliveMap tunnel command/token' -AsSecureString
    try {
        $taskCopied = Reveal-Once $taskSecureToken
        $taskToken = [regex]::Match($taskCopied, 'eyJ[A-Za-z0-9_+/=-]+').Value
        if (-not $taskToken) { throw 'No Cloudflare token found in the pasted command.' }
        [IO.File]::WriteAllText((Join-Path $private 'alivemap-tunnel.token'), $taskToken)
    } finally {
        $taskSecureToken.Dispose()
        Remove-Variable taskCopied,taskToken -ErrorAction SilentlyContinue
    }
}
& (Join-Path $repoRoot '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'package_permanent.py')
if ($LASTEXITCODE -ne 0) { throw 'Private payload preparation failed; no server changes made.' }
$taskOwnerSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
foreach ($taskFile in @('alivemap-tunnel.token','mec-endpoint.pending.json','permanent-payload.txt')) {
    & icacls (Join-Path $private $taskFile) /inheritance:r /grant:r "*${taskOwnerSid}:(F)" > $null
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict private configuration permissions.' }
}
Write-Host 'Next enter the MEC sudo password (masked), then both SSH login passwords.' -ForegroundColor Cyan
Write-Host 'Installs only alivemap-* services. Existing cloudflared service and routes are preserved.'
$taskSecureSudo = Read-Host 'MEC sudo password' -AsSecureString
try {
    $taskDigest = (Get-Content -LiteralPath (Join-Path $private 'permanent-payload.sha256') -Raw).Trim()
    $taskBlob = (Get-Content -LiteralPath (Join-Path $private 'permanent-payload.txt') -Raw).Trim()
    $taskProgram = 'import base64,gzip,hashlib,json;b=base64.b64decode("' + $taskBlob + '");assert hashlib.sha256(b).hexdigest()=="' + $taskDigest + '";p=json.loads(gzip.decompress(b));s=p.pop("installer");exec(compile(s,"alivemap-install","exec"),{"__name__":"__main__","PAYLOAD":p})'
    # sudo consumes its password line; Python reads the remaining program from
    # stdin. No credential or nested Python quoting appears in process arguments.
    $taskRemote = "sudo -S -p '' /usr/bin/python3 -I -"
    $taskInput = (Reveal-Once $taskSecureSudo) + "`n" + $taskProgram + "`n"
    $taskInput | & ssh -T -F $SshConfig -o ConnectTimeout=60 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 $HostAlias $taskRemote |
        Tee-Object -FilePath (Join-Path $private 'permanent-install-result.json')
    if ($LASTEXITCODE -ne 0) { throw 'Installation failed. Read the error above; keep the original application windows open.' }
    Write-Host 'PERMANENT_SERVICES_INSTALLED. Return to Codex for endpoint checks.' -ForegroundColor Green
} finally {
    $taskSecureSudo.Dispose()
    Remove-Variable taskInput,taskBlob,taskProgram -ErrorAction SilentlyContinue
}
