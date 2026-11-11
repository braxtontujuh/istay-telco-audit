[CmdletBinding()]
param([ValidateSet('Development','Production')][string]$Environment = 'Development')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
function New-RandomSecret {
    $bytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return ([Convert]::ToBase64String($bytes)).TrimEnd('=')
}
if ($Environment -eq 'Development') {
    $destination = Join-Path $projectRoot '.env.dev'
    if (Test-Path -LiteralPath $destination) { throw 'Development config exists; refusing to replace credentials.' }
    $content = (Get-Content -LiteralPath (Join-Path $projectRoot '.env.dev.example') -Raw).Replace('replace-with-random-development-password', (New-RandomSecret))
    [System.IO.File]::WriteAllText($destination, $content)
    Write-Host 'Created .env.dev with a random password. Values were not printed.'
} else {
    $config = Join-Path $projectRoot '.env.prod'
    if (!(Test-Path -LiteralPath $config)) { Copy-Item -LiteralPath (Join-Path $projectRoot '.env.prod.example') -Destination $config }
    $secretDir = Join-Path $projectRoot 'secrets/production'
    New-Item -ItemType Directory -Path $secretDir -Force | Out-Null
    foreach ($name in @('db_password.txt','db_admin_password.txt')) {
        $path = Join-Path $secretDir $name
        if (!(Test-Path -LiteralPath $path)) { [System.IO.File]::WriteAllText($path, (New-RandomSecret)) }
    }
    New-Item -ItemType Directory -Path (Join-Path $projectRoot 'backups/production') -Force | Out-Null
    Write-Host 'Created missing production template/secrets only; existing credentials preserved.'
    Write-Host 'Set real image references and hostname, protect files with Windows ACLs, and supply tunnel_token.txt before enabling tunnel.'
}
