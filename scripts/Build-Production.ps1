[CmdletBinding()]
param([Parameter(Mandatory)][ValidatePattern('^[a-z0-9][a-z0-9._-]+$')][string]$Release)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    function Pin-Image([string]$Reference) {
        & docker pull $Reference | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Cannot pull $Reference" }
        $digest = & docker image inspect --format '{{index .RepoDigests 0}}' $Reference
        if ($LASTEXITCODE -ne 0 -or $digest -notmatch '@sha256:[a-f0-9]{64}$') { throw "Cannot pin $Reference" }
        return $digest
    }
    # These tag selectors are resolved to immutable digests before the build.
    $postgres = Pin-Image 'postgres:17-alpine'
    $python = Pin-Image 'python:3.12-slim'
    $node = Pin-Image 'node:24-alpine'
    $nginx = Pin-Image 'nginxinc/nginx-unprivileged:stable-alpine'
    $cloudflared = Pin-Image 'cloudflare/cloudflared:latest'
    foreach ($image in @("istay-api:$Release", "istay-web:$Release", "istay-backup:$Release")) {
        & docker image inspect $image *> $null
        if ($LASTEXITCODE -eq 0) { throw "Release already exists: $image. Choose a new release tag." }
    }
    & docker build --build-arg "PYTHON_IMAGE=$python" -t "istay-api:$Release" ./backend
    if ($LASTEXITCODE -ne 0) { throw 'API build failed' }
    & docker build --target production --build-arg "NODE_IMAGE=$node" --build-arg "NGINX_IMAGE=$nginx" -t "istay-web:$Release" ./frontend
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
    & docker build --build-arg "POSTGRES_IMAGE=$postgres" -t "istay-backup:$Release" ./ops/backup
    if ($LASTEXITCODE -ne 0) { throw 'Backup build failed' }
    $manifest = [ordered]@{
        POSTGRES_IMAGE=$postgres; API_IMAGE="istay-api:$Release"; WEB_IMAGE="istay-web:$Release";
        BACKUP_IMAGE="istay-backup:$Release"; CLOUDFLARED_IMAGE=$cloudflared;
        bases=@{python=$python; node=$node; nginx=$nginx}; createdUtc=[DateTime]::UtcNow.ToString('o')
    }
    New-Item -ItemType Directory -Path 'releases' -Force | Out-Null
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "releases/$Release.json" -Encoding utf8
    Write-Host 'Images built. Copy the five image references from the release manifest to .env.prod. No deployment was started.'
} finally { Pop-Location }
