# Pekno Hub 启动脚本
# 使用方法: .\scripts\start-hub.ps1

. "$PSScriptRoot/_common.ps1"
Import-PeknoEnv
Enable-HubDevReload

Write-Host "🚀 启动 Hub 服务..." -ForegroundColor Cyan

# 启动 FastAPI 服务
uv run python hub/main.py
