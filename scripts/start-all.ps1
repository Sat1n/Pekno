# Pekno 完整启动脚本
# 使用方法: .\scripts\start-all.ps1
# 注意: 需要打开 3 个终端分别运行 Hub、Worker、Web

$ErrorActionPreference = "Stop"

Write-Host @"
╔═══════════════════════════════════════════════════════════╗
║                    Pekno 启动脚本                          ║
╠═══════════════════════════════════════════════════════════╣
║  请在 3 个不同的终端中运行以下命令:                         ║
║                                                            ║
║  终端 1: .\scripts\start-hub.ps1    (Hub API 服务)          ║
║  终端 2: .\scripts\start-worker.ps1 (Worker 任务服务)      ║
║  终端 3: .\scripts\start-web.ps1    (Vue 前端)             ║
║                                                            ║
║  或者使用 PowerShell 后台运行:                              ║
║   Start-Process powershell -ArgumentList '-NoExit', '-Command', '.\scripts\start-hub.ps1'    -WorkingDirectory 'F:\Cardinal\Pekno'     ║
║   Start-Process powershell -ArgumentList '-NoExit', '-Command', '.\scripts\start-worker.ps1' -WorkingDirectory 'F:\Cardinal\Pekno'     ║
║   Start-Process powershell -ArgumentList '-NoExit', '-Command', '.\scripts\start-web.ps1'    -WorkingDirectory 'F:\Cardinal\Pekno\web'  ║
╚═══════════════════════════════════════════════════════════╝
"@ -ForegroundColor Cyan
