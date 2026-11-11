[CmdletBinding(SupportsShouldProcess, ConfirmImpact='High')]
param([switch]$Tunnel, [switch]$LocalOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$scriptPath = Join-Path $PSScriptRoot 'Start-Production.ps1'
if ($LocalOnly -and $Tunnel) { throw 'Local-only recovery cannot enable a tunnel.' }
if ($LocalOnly) { $argumentsMode = ' -LocalOnly' } else { $argumentsMode = '' }
if ($PSCmdlet.ShouldProcess('Windows Task Scheduler: IStay-Production-AtLogon', 'Register current-user logon recovery task')) {
    $arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -File "' + $scriptPath + '" -StartDockerDesktop' + $argumentsMode
    if ($Tunnel) { $arguments += ' -Tunnel' }
    if ($LocalOnly) {
        $launcher = Join-Path $PSScriptRoot 'Start-Local-Staging.cmd'
        $action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\cmd.exe" -Argument ('/d /q /c ""'+$launcher+'""') -WorkingDirectory $projectRoot
    } else {
        $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments -WorkingDirectory $projectRoot
    }
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
    $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
    $taskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 2) -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
    Register-ScheduledTask -TaskName 'IStay-Production-AtLogon' -Action $action -Trigger $trigger -Principal $principal -Settings $taskSettings -Description 'Start Docker Desktop and I-Stay production after this user signs in.' -Force | Out-Null
    Write-Host 'Recovery task registered. This requires a Windows sign-in after reboot; it does not enable automatic login.'
}
