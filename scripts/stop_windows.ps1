<#
.SYNOPSIS
    Stop FinAlly (Windows). Safe to run repeatedly.
.DESCRIPTION
    Stops and removes the 'finally' container. Never removes the 'finally-data' volume,
    so your portfolio is kept.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\stop_windows.ps1
#>
[CmdletBinding()]
param()

# Native commands are checked through $LASTEXITCODE (see start_windows.ps1).
$ErrorActionPreference = 'Continue'

$Container = 'finally'

# Runs docker with stderr discarded and returns its stdout. Check $LASTEXITCODE afterwards.
function Invoke-DockerQuiet {
    $ErrorActionPreference = 'SilentlyContinue'
    & docker @args 2>$null
}

Invoke-DockerQuiet info | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Error: Docker is not running.' -ForegroundColor Red
    exit 1
}

Invoke-DockerQuiet container inspect $Container | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Stopping FinAlly...'
    # Give the app time to shut down cleanly (some Docker installs default to 1 s).
    Invoke-DockerQuiet stop -t 10 $Container | Out-Null
    Invoke-DockerQuiet rm $Container | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: could not remove container '$Container'." -ForegroundColor Red
        exit 1
    }
    Write-Host "Stopped. Data is kept in the 'finally-data' volume."
} else {
    Write-Host 'FinAlly is not running.'
}
exit 0
