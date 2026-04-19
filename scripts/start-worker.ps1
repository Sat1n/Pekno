# Pekno Worker 启动脚本
# 使用方法: .\scripts\start-worker.ps1

. "$PSScriptRoot/_common.ps1"
Import-PeknoEnv

Write-Host "🚀 启动 Worker 服务..." -ForegroundColor Cyan

# 启动 TaskIQ Worker
uv run taskiq worker worker.main:broker
