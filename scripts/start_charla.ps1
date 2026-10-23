<#
.SYNOPSIS
    Open everything Elkin needs on stage for the live talk ("charla"). Safe to run repeatedly.
.DESCRIPTION
    1. Starts the agent monitor (http://localhost:4800) in its own window, unless it already
       answers /api/health.
    2. Checks the public Railway app's /api/health and warns if it does not answer.
    3. Opens the presenter panel (<public URL>/charla/presentador/) and the monitor's
       Agentes page in the default browser.
.PARAMETER PublicUrl
    The Railway app's origin, e.g. https://ia-revolutions-charla.up.railway.app.
    Default: $env:CHARLA_PUBLIC_URL.
.PARAMETER MonitorDir
    The agent-monitor project folder. Default: C:\Users\elkin\projects\agent-monitor.
.PARAMETER MonitorPort
    The agent monitor's port. Default: 4800.
.PARAMETER NoOpen
    Start the monitor and run the checks, but don't open the browser.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\start_charla.ps1 -PublicUrl https://ia-revolutions-charla.up.railway.app
#>
[CmdletBinding()]
param(
    [string]$PublicUrl = $env:CHARLA_PUBLIC_URL,
    [string]$MonitorDir = 'C:\Users\elkin\projects\agent-monitor',
    [int]$MonitorPort = 4800,
    [switch]$NoOpen
)

# Native commands and web calls are checked explicitly; 'Stop' is avoided on purpose (see
# start_windows.ps1: Windows PowerShell 5.1 turns some stderr output into terminating errors).
$ErrorActionPreference = 'Continue'

# Windows PowerShell 5.1 may default to TLS 1.0; Railway's edge needs TLS 1.2.
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$MonitorBase = "http://localhost:$MonitorPort"

function Exit-WithError([string]$Message) {
    Write-Host "Error: $Message" -ForegroundColor Red
    exit 1
}

# True when GET <Url> answers 200 within $TimeoutSec seconds.
function Test-Health([string]$Url, [int]$TimeoutSec = 3) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec -ErrorAction Stop
        return ($response.StatusCode -eq 200)
    } catch {
        return $false
    }
}

# --- Public URL ---------------------------------------------------------------------------------
if (-not $PublicUrl) {
    Exit-WithError 'No public URL. Pass -PublicUrl https://<app>.up.railway.app or set $env:CHARLA_PUBLIC_URL.'
}
$PublicUrl = $PublicUrl.Trim().TrimEnd('/')
if ($PublicUrl -notmatch '^https?://') { $PublicUrl = "https://$PublicUrl" }
$PresenterUrl = "$PublicUrl/charla/presentador/"

# --- 1. Agent monitor ---------------------------------------------------------------------------
if (Test-Health "$MonitorBase/api/health") {
    Write-Host "Agent monitor is already running at $MonitorBase."
} else {
    if (-not (Test-Path -LiteralPath $MonitorDir)) { Exit-WithError "Agent monitor folder not found: $MonitorDir" }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Exit-WithError "'uv' is not on PATH; it is needed to start the agent monitor." }

    Write-Host "Starting the agent monitor in a new window ($MonitorDir)..."
    # -NoExit keeps the window open, so its logs (or an error) stay visible during the talk.
    $command = "`$host.UI.RawUI.WindowTitle = 'Agent monitor :$MonitorPort'; uv run python -m monitor --port $MonitorPort"
    Start-Process -FilePath 'powershell.exe' -WorkingDirectory $MonitorDir -ArgumentList @('-NoExit', '-NoProfile', '-Command', $command) | Out-Null

    Write-Host -NoNewline 'Waiting for the agent monitor'
    $monitorUp = $false
    for ($i = 0; $i -lt 45; $i++) {
        if (Test-Health "$MonitorBase/api/health" 2) { $monitorUp = $true; break }
        Write-Host -NoNewline '.'
        Start-Sleep -Seconds 1
    }
    Write-Host ''
    if ($monitorUp) {
        Write-Host "Agent monitor is running at $MonitorBase." -ForegroundColor Green
    } else {
        Write-Warning "The agent monitor did not answer within 45 s. Check its window for errors."
    }
}

# --- 2. Public app ------------------------------------------------------------------------------
if (Test-Health "$PublicUrl/api/health" 10) {
    Write-Host "Charla app is healthy at $PublicUrl." -ForegroundColor Green
} else {
    Write-Warning "$PublicUrl/api/health did not answer. Check the Railway deploy (railway logs) before going on stage."
}

# --- 3. Browser ---------------------------------------------------------------------------------
Write-Host "Presenter: $PresenterUrl"
Write-Host "Agents:    $MonitorBase/Agentes.dc.html"
if (-not $NoOpen) {
    Start-Process $PresenterUrl
    Start-Process "$MonitorBase/Agentes.dc.html"
}
exit 0
