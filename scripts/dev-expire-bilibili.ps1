# 开发环境辅助脚本：将 Bilibili 数据批量标记为“已过期”
# 使用方法: .\scripts\dev-expire-bilibili.ps1

$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "未找到 docker 命令，请先确认 Docker Desktop 正在运行。"
}

$containerName = "iris-db"
$dbUser = "pekno"
$dbName = "pekno_iris"

$sql = @"
WITH updated AS (
    UPDATE items
    SET
        retention_days = 1,
        created_at = NOW() - INTERVAL '2 hours',
        updated_at = NOW()
    WHERE source_type = 'bilibili'
    RETURNING id
)
SELECT COUNT(*) AS updated_count FROM updated;
"@

Write-Host "🧪 正在将 Bilibili 数据标记为可立即过期..." -ForegroundColor Cyan
docker exec -i $containerName psql -U $dbUser -d $dbName -c $sql

Write-Host "✅ 已完成。等待下一次 TTL 心跳，或手动触发清理任务进行验证。" -ForegroundColor Green
