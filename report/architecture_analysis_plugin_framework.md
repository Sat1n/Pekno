# 插件框架现状总览

## 当前已经落地的能力

- 插件配置由 `shared/plugins/manager.py` 统一注入通用字段。
- 插件作者通过 `framework_defaults` 声明这些通用字段的默认值。
- `UniversalItem` 已包含 `intent`、`auto_short_summary`、`retention_hours`。
- Worker 侧已经拆成抓取、短总结、标签、向量化四段。
- 自动同步不再是每插件一个定时器，而是集中式 `system_heartbeat_task`。
- TTL 回收不再是手动函数，而是集中式 `system_ttl_cleanup_task`。
- 向量当前存储在 PostgreSQL 的 `ItemORM.embedding` 中，由 `pgvector` 扩展支持。

## 通用配置注入

框架当前统一注入以下 `settings_schema` 字段：

- `auto_short_summary`
- `retention_hours`
- `sync_limit`
- `auto_sync`
- `auto_sync_interval`

插件不应自行声明这些字段。如果需要覆盖默认值，应使用：

```json
{
  "framework_defaults": {
    "retention_hours": 24,
    "auto_short_summary": false
  }
}
```

当前内置插件默认值：

- GitHub Stars: `retention_hours = -1`
- Bilibili: `retention_hours = 24`

## 调度架构

### 自动同步心跳

`worker/maintenance.py` 中的 `system_heartbeat_task` 每 5 分钟执行一次：

- 读取所有启用插件
- 检查 `auto_sync`
- 检查 `last_sync_time`
- 检查 `sync_status == running` 锁
- 到期时投递 `run_plugin_pipeline_task`

### TTL 垃圾回收

`worker/maintenance.py` 中的 `system_ttl_cleanup_task` 每 5 分钟执行一次：

- 扫描 `retention_days > 0` 且未 pin 的数据
- 使用 `created_at + retention_hours < now` 判断过期
- 批量删除过期 `ItemORM`

由于向量与业务数据当前共存于 PostgreSQL 中，删除 `ItemORM` 记录即可释放对应 embedding。若未来切换到 Qdrant/Milvus/Chroma，可在 `_delete_from_vector_store(...)` 中接入外部删除。

## 增量熔断

`worker/plugins/pipeline.py` 已实现连续命中历史数据熔断：

- 同步过程中连续 3 条命中旧数据时，直接提前结束
- 适合按时间倒序抓取的数据源
- 显著减少 Bilibili 等短流插件的无效数据库查询

## 时间与日志

- 应用时间基准由 `.env` 中的 `APP_TIMEZONE` 控制，当前开发默认 `Asia/Shanghai`
- `APP_ENV=dev` 默认输出 DEBUG
- `APP_ENV=prod` 默认输出 INFO
- Windows/uv 环境若缺少 IANA 时区数据库，需要安装 `tzdata`

```powershell
uv add tzdata
```
