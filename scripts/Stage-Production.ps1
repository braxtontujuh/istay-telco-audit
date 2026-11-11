[CmdletBinding(SupportsShouldProcess, ConfirmImpact='High')]
param(
    [Parameter(Mandatory)][string]$Destination,
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9][a-z0-9._-]+$')][string]$Release,
    [string]$CertificatePython = 'python',
    [switch]$ResumeEmpty
)
$ErrorActionPreference = 'Stop'
$sourceRoot = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent)).TrimEnd('\')
$targetRoot = [IO.Path]::GetFullPath($Destination).TrimEnd('\')
$profileRoot = [Environment]::GetFolderPath('UserProfile').TrimEnd('\')
if (!$targetRoot.StartsWith($profileRoot+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Destination must be a new directory under the current Windows user profile.' }
if ($targetRoot -eq $sourceRoot -or $targetRoot.StartsWith($sourceRoot+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Choose a separate nonsynced production directory.' }
foreach ($syncRoot in @($env:OneDrive,$env:OneDriveCommercial,$env:OneDriveConsumer)) {
    if ($syncRoot -and ($targetRoot -eq $syncRoot -or $targetRoot.StartsWith($syncRoot.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase))) { throw 'Production directory cannot be inside OneDrive.' }
}
$targetExists = Test-Path -LiteralPath $targetRoot
if ($targetExists -and (!$ResumeEmpty -or @(Get-ChildItem -LiteralPath $targetRoot -Force).Count -gt 0)) { throw 'Destination already exists; staging refuses to overwrite a production directory. ResumeEmpty permits only an empty directory from an interrupted attempt.' }
$parent = Split-Path $targetRoot -Parent
while ($parent) {
    if ((Get-Item -LiteralPath $parent -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Destination ancestors cannot be junctions or symlinks.' }
    $parent = Split-Path $parent -Parent
}
$manifestPath = Join-Path $sourceRoot "releases/$Release.json"
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
foreach ($key in @('POSTGRES_IMAGE','API_IMAGE','WEB_IMAGE','BACKUP_IMAGE','CLOUDFLARED_IMAGE')) {
    if (!$manifest.$key -or $manifest.$key -match ':latest$') { throw "Release has no pinned $key" }
}
Push-Location $sourceRoot
try { $files = @(& git ls-files --cached --others --exclude-standard); if ($LASTEXITCODE -ne 0) { throw 'Cannot enumerate reviewed source files.' } }
finally { Pop-Location }
$files = @($files | Where-Object { $_ -notmatch '^(\.git/|\.tools/|\.venv/|secrets/|backups/|node_modules/)' -and ($_ -notmatch '^\.env' -or $_ -match '\.example$') -and $_ -notmatch '(^|/)node_modules/|(^|/)__pycache__/' })
Write-Host "Stage $($files.Count) source files to $targetRoot; new independent credentials and istay-prod_pgdata volume; localhost-only TLS on port 8444."
Write-Host 'No Cloudflare connector, Windows trust, power setting or startup task is changed by this script.'
if (!$PSCmdlet.ShouldProcess($targetRoot,'Create restricted nonsynced production staging directory')) { return }
if (!$targetExists) { New-Item -ItemType Directory -Path $targetRoot | Out-Null }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
# Change only this owned directory's DACL; never request SACL/audit privileges.
& icacls.exe $targetRoot '/inheritance:r' '/grant:r' "*$($identity.Value):(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Cannot restrict the new production directory ACL.' }
foreach ($relative in $files) {
    $from = Join-Path $sourceRoot $relative
    # OneDrive placeholders have ReparsePoint attributes but no link target; copy their hydrated bytes.
    $sourceItem = Get-Item -LiteralPath $from -Force
    if ($sourceItem.LinkType -in @('SymbolicLink','Junction') -or $sourceItem.LinkTarget) { throw "Refusing a symlink source: $relative" }
    $to = [IO.Path]::GetFullPath((Join-Path $targetRoot $relative))
    if (!$to.StartsWith($targetRoot+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Source entry escapes the target.' }
    New-Item -ItemType Directory -Path (Split-Path $to -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $from -Destination $to
}
& (Join-Path $targetRoot 'scripts/New-LocalConfig.ps1') -Environment Production
$production = Get-Content -LiteralPath (Join-Path $targetRoot '.env.prod')
foreach ($key in @('POSTGRES_IMAGE','API_IMAGE','WEB_IMAGE','BACKUP_IMAGE','CLOUDFLARED_IMAGE')) { $production = $production -replace ('^'+$key+'=.*'),($key+'='+$manifest.$key) }
[IO.File]::WriteAllLines((Join-Path $targetRoot '.env.prod'),[string[]]$production)
$local = $production -replace '^APP_ORIGIN=.*','APP_ORIGIN=https://localhost:8444' -replace '^TRUSTED_HOSTS=.*','TRUSTED_HOSTS=localhost,127.0.0.1,api'
[IO.File]::WriteAllLines((Join-Path $targetRoot '.env.local-staging'),[string[]]$local)
& $CertificatePython (Join-Path $targetRoot 'scripts/make-rehearsal-cert.py') --output (Join-Path $targetRoot 'secrets/local-staging-tls')
if ($LASTEXITCODE -ne 0) { throw 'Certificate generation failed; inspect the staged directory before proceeding.' }
@{directory=$targetRoot;release=$Release;mode='LocalStaging';createdUtc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $targetRoot '.deployment.json') -Encoding utf8
Write-Host 'Staging prepared. Production HTTPS origin remains pending; local staging uses an explicitly trusted test client only.'
