param(
    [int]$PerPage = 15,
    [ValidateSet("all", "inc-ransom", "html-leak-sites", "api-leak-sites", "javascript-leak-sites")]
    [string]$StartAt = "all"
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendRoot = Join-Path $projectRoot "darkwolf-backend"
$python = Join-Path $backendRoot ".venv\Scripts\python.exe"
$previousTorSocksPort = $env:TOR_SOCKS_PORT
$torPortOverrideApplied = $false

if (-not (Test-Path -LiteralPath $python)) {
    throw "Backend Python environment not found: $python"
}
if ($PerPage -lt 1) {
    throw "PerPage must be at least 1."
}

Push-Location $backendRoot
try {
    Write-Host "Checking MongoDB and Tor SOCKS before starting the scrape cycle..."
    $preflight = @'
import socket
import sys

from app.core.config import settings
from app.db.mongodb import client

failures = []
try:
    client.admin.command("ping")
    print("MongoDB: ready")
except Exception as exc:
    failures.append(f"MongoDB: {type(exc).__name__}: {exc}")

working_tor_port = None
tor_errors = []
ports = list(dict.fromkeys([settings.tor_socks_port, 9050, 9150]))
for port in ports:
    try:
        with socket.create_connection((settings.tor_host, port), timeout=4) as sock:
            sock.sendall(b"\x05\x01\x00")
            response = sock.recv(2)
            if response != b"\x05\x00":
                raise RuntimeError(f"SOCKS5 no-auth handshake returned {response!r}")
        working_tor_port = port
        break
    except Exception as exc:
        tor_errors.append(f"{port}: {type(exc).__name__}: {exc}")

if working_tor_port is None:
    failures.append("Tor SOCKS unavailable on ports " + "; ".join(tor_errors))
else:
    print(f"Tor SOCKS: ready ({settings.tor_host}:{working_tor_port})")
    print(f"TOR_SOCKS_PORT={working_tor_port}")

if failures:
    for failure in failures:
        print(f"ERROR: {failure}", file=sys.stderr)
    sys.exit(1)
'@

    $preflightOutput = @($preflight | & $python - 2>&1)
    $preflightExitCode = $LASTEXITCODE
    foreach ($line in $preflightOutput) {
        if ([string]$line -notmatch '^TOR_SOCKS_PORT=') {
            Write-Host $line
        }
    }
    if ($preflightExitCode -ne 0) {
        throw "Preflight failed. Start MongoDB and a Tor SOCKS listener, then retry. No scrape stages were started."
    }
    $torPortLine = $preflightOutput | Where-Object { [string]$_ -match '^TOR_SOCKS_PORT=' } | Select-Object -First 1
    if (-not $torPortLine) {
        throw "Preflight did not return a Tor SOCKS port. No scrape stages were started."
    }
    $env:TOR_SOCKS_PORT = ([string]$torPortLine -replace '^TOR_SOCKS_PORT=', '').Trim()
    $torPortOverrideApplied = $true

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $logDirectory = Join-Path $backendRoot "logs\full-scrape-$timestamp"
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

    $stages = @(
        @{ Name = "inc-ransom"; Source = "inc-ransom" },
        @{ Name = "html-leak-sites"; Source = "ransomware-sites" },
        @{ Name = "api-leak-sites"; Source = "api-leak-sites" },
        @{ Name = "javascript-leak-sites"; Source = "javascript-leak-sites" }
    )
    $results = @()
    $startAtIndex = 0
    if ($StartAt -ne "all") {
        for ($index = 0; $index -lt $stages.Count; $index++) {
            if ($stages[$index].Name -eq $StartAt) {
                $startAtIndex = $index
                break
            }
        }
    }

    for ($stageIndex = $startAtIndex; $stageIndex -lt $stages.Count; $stageIndex++) {
        $stage = $stages[$stageIndex]
        $logPath = Join-Path $logDirectory "$($stage.Name).log"
        Write-Host "Starting $($stage.Name) (live)..."

        if ($stage.Source -eq "inc-ransom") {
            & $python -m app.cli collect $stage.Source --mode live --per-page $PerPage 2>&1 |
                Tee-Object -FilePath $logPath
        }
        else {
            & $python -m app.cli collect $stage.Source --mode live 2>&1 |
                Tee-Object -FilePath $logPath
        }

        $stageExitCode = $LASTEXITCODE
        $reportedErrors = 0
        if ($stageExitCode -eq 0 -and $stage.Source -ne "inc-ransom") {
            $outputText = Get-Content -LiteralPath $logPath -Raw
            $jsonStarts = [regex]::Matches($outputText, '(?m)^\{')
            if ($jsonStarts.Count -gt 0) {
                try {
                    $report = $outputText.Substring($jsonStarts[$jsonStarts.Count - 1].Index) | ConvertFrom-Json
                    $errorsProperty = $report.PSObject.Properties["errors"]
                    if ($null -ne $errorsProperty) {
                        $reportedErrors = @($errorsProperty.Value | Where-Object { $null -ne $_ }).Count
                    }
                    if ($reportedErrors -gt 0) {
                        $stageExitCode = 2
                    }
                }
                catch {
                    Write-Warning "Could not parse the $($stage.Name) summary; see its log."
                }
            }
        }
        $results += [pscustomobject]@{
            Stage = $stage.Name
            ExitCode = $stageExitCode
            ReportedErrors = $reportedErrors
            Log = $logPath
        }
        if ($stageExitCode -eq 0) {
            Write-Host "Completed $($stage.Name)."
        }
        else {
            Write-Warning "$($stage.Name) reported failure(s) (exit code $stageExitCode, reported errors $reportedErrors); continuing with remaining stages."
        }
    }

    Write-Host ""
    Write-Host "Scrape cycle summary:"
    $results | Format-Table -AutoSize
    Write-Host "Logs: $logDirectory"

    if ($results | Where-Object { $_.ExitCode -ne 0 }) {
        exit 1
    }
}
finally {
    if ($torPortOverrideApplied) {
        if ($null -eq $previousTorSocksPort) {
            Remove-Item Env:TOR_SOCKS_PORT -ErrorAction SilentlyContinue
        }
        else {
            $env:TOR_SOCKS_PORT = $previousTorSocksPort
        }
    }
    Pop-Location
}
