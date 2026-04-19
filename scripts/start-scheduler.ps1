# Pekno Scheduler 启动脚本
# 使用方法: .\scripts\start-scheduler.ps1

. "$PSScriptRoot/_common.ps1"
Import-PeknoEnv

Write-Host "🫀 启动 TaskIQ Scheduler..." -ForegroundColor Cyan

# 启动时先执行一次 bootstrap，保证立即入队系统任务
uv run python scripts/scheduler_bootstrap.py

# 启动 TaskIQ Scheduler
uv run taskiq scheduler worker.main:scheduler
