[CmdletBinding()]
param([switch]$Tunnel, [switch]$StartDockerDesktop, [switch]$LocalOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    $dockerCli = if ($dockerCommand) { $dockerCommand.Source } else {
        @("$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe", 'C:\Program Files\Docker\Docker\resources\bin\docker.exe') | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (!$dockerCli) { throw 'Docker CLI is not installed at a known location. Open a new PowerShell session after installation.' }
    if ($StartDockerDesktop) {
        $dockerDesktopPath = @("$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe", 'C:\Program Files\Docker\Docker\Docker Desktop.exe') | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if (!$dockerDesktopPath) { throw 'Docker Desktop is not installed at a known location.' }
        Start-Process -FilePath $dockerDesktopPath -WindowStyle Hidden
    }
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        & $dockerCli info *> $null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 10
    }
    if ($LASTEXITCODE -ne 0) { throw 'Docker engine unavailable after 10 minutes.' }
    $compose = @('compose','--project-name','istay-prod','--env-file','.env.prod','-f','compose.prod.yml')
    if ($LocalOnly) {
        if ($Tunnel) { throw 'Local-only staging cannot enable a tunnel.' }
        $deployment = Get-Content -LiteralPath '.deployment.json' -Raw | ConvertFrom-Json
        if ($deployment.mode -ne 'LocalStaging' -or $deployment.directory.TrimEnd('\') -ne $projectRoot.TrimEnd('\')) { throw 'This directory is not a staged local deployment.' }
        $cert = [Security.Cryptography.X509Certificates.X509Certificate2]::new((Join-Path $projectRoot 'secrets/local-staging-tls/server.crt'))
        if ($cert.NotAfter -lt [DateTime]::Now) { throw 'Local staging certificate expired. Configure the final HTTPS origin or renew local test certificates deliberately.' }
        $compose = @('compose','--project-name','istay-prod','--env-file','.env.local-staging','-f','compose.prod.yml','-f','compose.local-staging.yml')
    }
    if ($Tunnel) { $compose += @('--profile','tunnel') }
    $rendered = & $dockerCli @compose config --format json
    if ($LASTEXITCODE -ne 0) { throw 'Production configuration is incomplete.' }
    $config = ($rendered -join "`n") | ConvertFrom-Json
    foreach ($name in @('db','api','web','backup')) {
        if (!$config.services.$name.image -or $config.services.$name.image -match ':latest$') { throw "Set pinned image for $name" }
    }
    if ($Tunnel -and $config.services.tunnel.image -notmatch '@sha256:[a-f0-9]{64}$') { throw 'Pin cloudflared by digest before enabling tunnel.' }
    if ($config.services.api.environment.APP_ORIGIN -match '\.example/?$') { throw 'Set a real HTTPS origin before production startup.' }
    & $dockerCli @compose up -d --no-build --remove-orphans
    if ($LASTEXITCODE -ne 0) { throw 'Production startup failed. Inspect compose ps/logs.' }
    if ($LocalOnly) { Write-Host 'Local-only staging started on loopback 8444. Test certificates are not browser-trusted; external deployment remains pending.' }
    else { Write-Host 'Start requested. Verify health, authentication, persistence, backup restore, external HTTPS and Android offline sync before declaring deployment complete.' }
} finally { Pop-Location }
