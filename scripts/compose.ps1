$ErrorActionPreference = "Stop"

. "$PSScriptRoot/_common.ps1"
Import-PeknoEnv

$accelerator = if ($env:PEKNO_ACCELERATOR) { $env:PEKNO_ACCELERATOR.ToLowerInvariant() } else { "cpu" }
$composeFiles = @("-f", "docker-compose.yaml")

switch ($accelerator) {
    "cpu" { }
    "cuda" { $composeFiles += @("-f", "docker-compose.accel.cuda.yaml") }
    default {
        throw "Unsupported PEKNO_ACCELERATOR: $accelerator. Supported values: cpu, cuda"
    }
}

Write-Host "Using accelerator profile: $accelerator" -ForegroundColor Green
Write-Host "Running: docker compose $($composeFiles -join ' ') $($args -join ' ')" -ForegroundColor Cyan

& docker compose @composeFiles @args
