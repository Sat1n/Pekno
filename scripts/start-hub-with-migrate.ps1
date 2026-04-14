# Pekno Hub startup script with smart migrations
# Usage: .\scripts\start-hub-with-migrate.ps1

$ErrorActionPreference = "Stop"

$env:PYTHONPATH = "."

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
    Write-Host "✓ Loaded .env configuration file" -ForegroundColor Green
}

Write-Host "🛠️ Running smart database migrations..." -ForegroundColor Cyan
uv run python scripts/smart_migrate.py

Write-Host "🚀 Starting Hub service..." -ForegroundColor Cyan
uv run python hub/main.py
