<#
.SYNOPSIS
    Start FinAlly in Docker (Windows). Safe to run repeatedly.
.DESCRIPTION
    Builds the 'finally' image if it is missing (or with -Build), creates .env from
    .env.example if needed, runs the container with the 'finally-data' volume, waits
    for it to become healthy and opens the browser.
.PARAMETER Build
    Rebuild the image and replace a running container with the new one.
.PARAMETER NoOpen
    Don't open the browser.
.PARAMETER Port
    Host port, bound to 127.0.0.1 only. Default: $env:PORT, else 8000.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\start_windows.ps1 -Build
#>
[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$NoOpen,
    [int]$Port = 0
)

# Native commands are checked through $LASTEXITCODE. 'Stop' is avoided on purpose: Windows
# PowerShell 5.1 can turn docker's stderr progress output into terminating errors.
$ErrorActionPreference = 'Continue'

$Image = 'finally'
$Container = 'finally'
$Volume = 'finally-data'
# Seconds 'docker stop' waits before SIGKILL. Some Docker installs default to 1 s, which kills
# the app before it saves its state (uvicorn needs ~4 s with an open price stream).
$StopTimeout = 10
if ($Port -eq 0) {
    if ($env:PORT) { $Port = [int]$env:PORT } else { $Port = 8000 }
}

$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root '.env'

# Runs docker with stderr discarded and returns its stdout. Check $LASTEXITCODE afterwards.
function Invoke-DockerQuiet {
    $ErrorActionPreference = 'SilentlyContinue'
    & docker @args 2>$null
}

function Exit-WithError([string]$Message) {
    Write-Host "Error: $Message" -ForegroundColor Red
    exit 1
}

Invoke-DockerQuiet info | Out-Null
if ($LASTEXITCODE -ne 0) { Exit-WithError 'Docker is not running. Start Docker Desktop and try again.' }

if (-not (Test-Path -LiteralPath $EnvFile)) {
    $example = Join-Path $Root '.env.example'
    if (Test-Path -LiteralPath $example) {
        Copy-Item -LiteralPath $example -Destination $EnvFile -ErrorAction Stop
    } else {
        New-Item -ItemType File -Path $EnvFile -ErrorAction Stop | Out-Null
    }
    Write-Warning "No .env found; created $EnvFile from .env.example."
    Write-Warning 'Set OPENROUTER_API_KEY there to enable AI chat (or LLM_MOCK=true for mock replies).'
}

$rebuilt = $false
Invoke-DockerQuiet image inspect $Image | Out-Null
if ($Build -or $LASTEXITCODE -ne 0) {
    Write-Host "Building image '$Image'..."
    & docker build -t $Image $Root
    if ($LASTEXITCODE -ne 0) { Exit-WithError 'docker build failed.' }
    $rebuilt = $true
}

$running = "$(Invoke-DockerQuiet container inspect -f '{{.State.Running}}' $Container)".Trim()
$exists = ($LASTEXITCODE -eq 0)
if ($exists -and $running -eq 'true' -and -not $rebuilt) {
    Write-Host 'FinAlly is already running.'
} else {
    if ($exists) {
        Write-Host "Replacing existing container '$Container'..."
        Invoke-DockerQuiet stop -t $StopTimeout $Container | Out-Null
        Invoke-DockerQuiet rm $Container | Out-Null
    }
    Write-Host "Starting container '$Container'..."
    & docker run -d --name $Container --stop-timeout $StopTimeout -v "${Volume}:/app/db" -p "127.0.0.1:${Port}:8000" --env-file $EnvFile $Image | Out-Null
    if ($LASTEXITCODE -ne 0) { Exit-WithError 'docker run failed (is the port already in use? Try -Port 8001).' }
}

# The actual host port (it differs from $Port if an already-running container used another).
$hostPort = $Port
$mapped = Invoke-DockerQuiet port $Container 8000/tcp | Select-Object -First 1
if ("$mapped" -match ':(\d+)\s*$') { $hostPort = $Matches[1] }
$url = "http://localhost:$hostPort"

Write-Host -NoNewline 'Waiting for FinAlly to become healthy'
$status = ''
for ($i = 0; $i -lt 60; $i++) {
    $status = "$(Invoke-DockerQuiet container inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $Container)".Trim()
    if ($LASTEXITCODE -ne 0) { $status = 'missing' }
    if ($status -in 'healthy', 'exited', 'dead', 'missing') { break }
    Write-Host -NoNewline '.'
    Start-Sleep -Seconds 1
}
Write-Host ''

if ($status -ne 'healthy') {
    Write-Host "FinAlly did not become healthy (status: $status). Recent logs:" -ForegroundColor Red
    & docker logs --tail 40 $Container
    exit 1
}

Write-Host "FinAlly is running at $url" -ForegroundColor Green
Write-Host "Stop it with: scripts\stop_windows.ps1 (your data is kept in the '$Volume' volume)"

if (-not $NoOpen) { Start-Process $url }
exit 0
