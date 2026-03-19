# Pekno Scheduler 启动脚本
# 使用方法: .\scripts\start-scheduler.ps1

$ErrorActionPreference = "Stop"

# 设置环境变量
$env:PYTHONPATH = "."

# 加载 .env 文件（如果存在）
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^([^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
    Write-Host "✓ 已加载 .env 配置文件" -ForegroundColor Green
}

Write-Host "🫀 启动 TaskIQ Scheduler..." -ForegroundColor Cyan

# 启动 TaskIQ Scheduler
uv run taskiq scheduler worker.main:scheduler
