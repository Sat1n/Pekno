# Pekno Hub startup script with smart migrations
# Usage: .\scripts\start-hub-with-migrate.ps1

. "$PSScriptRoot/_common.ps1"
Import-PeknoEnv
Enable-HubDevReload

Write-Host "🛠️ Running smart database migrations..." -ForegroundColor Cyan
uv run python scripts/smart_migrate.py

Write-Host "🚀 Starting Hub service..." -ForegroundColor Cyan
uv run python hub/main.py
