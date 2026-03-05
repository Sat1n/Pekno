# Pekno Web 前端启动脚本
# 使用方法: .\scripts\start-web.ps1

$ErrorActionPreference = "Stop"

$webDir = "web"

if (-not (Test-Path $webDir)) {
    Write-Host "❌ 错误: 未找到 web 目录" -ForegroundColor Red
    exit 1
}

Push-Location $webDir

Write-Host "🚀 启动 Vue 开发服务器..." -ForegroundColor Cyan
npm run dev

Pop-Location
