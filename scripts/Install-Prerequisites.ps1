[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'High')]
param(
    [ValidateSet('WSL','Docker')][string]$Component,
    [ValidateSet('PerUser','AllUsers')][string]$DockerMode = 'PerUser'
)
$ErrorActionPreference = 'Stop'
if (!$Component) { throw 'Choose -Component WSL or -Component Docker. Run only after explicit operator approval.' }
if ($Component -eq 'WSL') {
    if ($PSCmdlet.ShouldProcess('Windows optional features, WSL2 and Ubuntu 24.04', 'Install (no automatic reboot)')) {
        & wsl.exe --install -d Ubuntu-24.04 --no-launch
        if ($LASTEXITCODE -notin @(0,3010)) { throw "WSL installer returned $LASTEXITCODE" }
        Write-Host 'Inspect installation result. Restart manually only after saving work and approving a reboot.'
        Write-Host 'After restart launch Ubuntu-24.04 and create your Linux username and password.'
    }
} else {
    if ($PSCmdlet.ShouldProcess("Docker Desktop ($DockerMode)", 'Install interactively using winget; review license and WSL2 selection')) {
        $installerArguments = 'install --backend=wsl-2 --no-windows-containers'
        if ($DockerMode -eq 'PerUser') { $installerArguments += ' --user' }
        & winget.exe install --id Docker.DockerDesktop --exact --source winget --interactive --override $installerArguments
        if ($LASTEXITCODE -ne 0) { throw "Docker installer returned $LASTEXITCODE" }
        Write-Host 'Launch Docker Desktop, review its terms, select WSL2/Linux containers, and enable Ubuntu integration.'
    }
}
