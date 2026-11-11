[CmdletBinding()]
param([switch]$LocalOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    $dockerCli = if ($dockerCommand) { $dockerCommand.Source } else { Join-Path $env:LOCALAPPDATA 'Programs/DockerDesktop/resources/bin/docker.exe' }
    if (!(Test-Path -LiteralPath $dockerCli)) { throw 'Docker CLI not found.' }
    $compose = @('compose','--project-name','istay-prod','--env-file','.env.prod','-f','compose.prod.yml')
    if ($LocalOnly) { $compose = @('compose','--project-name','istay-prod','--env-file','.env.local-staging','-f','compose.prod.yml','-f','compose.local-staging.yml') }
    Write-Host 'Create your permanent administrator. Use username admin. Choose the password privately; input is hidden.'
    Write-Host 'Do not send the password in chat. This window does not record a transcript.'
    & $dockerCli @compose exec api python -m app.cli create-admin
    if ($LASTEXITCODE -ne 0) { throw 'Administrator creation did not finish. Read the message above; no existing account is overwritten.' }
} finally { Pop-Location }
