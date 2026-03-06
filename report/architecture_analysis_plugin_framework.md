# 插件化重构 (Plugin Framework) —— 核心架构代码现状盘点

为了将系统重构为标准化的插件底座 (Plugin Framework)，以下是系统中 4 个核心链路的现状代码提取与结构分析。

---

## 1. 数据库模型 (Database Schema)
**文件**: [hub/core/database_models.py](file:///f:/Cardinal/Pekno/hub/core/database_models.py)

### 数据存储表 ([ItemORM](file:///f:/Cardinal/Pekno/hub/core/database_models.py#11-39))
**现状分析**：
- **通用设计已具备**：我们在表结构级别**没有硬编码**诸如 `github_repo_name` 的字段。而是通过 `source_type` (如 `"github_star"`) 区分来源，通过 JSON 类型的 `metadata_extra` 存储属于插件私有的扩展数据（也就是 GitHub 的 `lang`, [stars](file:///f:/Cardinal/Pekno/worker/plugins/github/task.py#8-171), `pushed_at`, `readme_sha` 等），这是一个非常棒的插件化底座基础。
- **依赖关联**：提供了统一的 `raw_link` 和 `embedding` 向量槽。
```python
class ItemORM(Base):
    """这是 Iris 的物理存储结构"""
    __tablename__ = "items"

    # 基础字段
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    embedding: Mapped[Optional[Vector]] = mapped_column(Vector(768))
    source_type: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    raw_link: Mapped[str] = mapped_column(String)
    intent: Mapped[str] = mapped_column(String)
    
    # 扩展字段
    content_text: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    
    # 【插件私有数据核心锚点】
    metadata_extra: Mapped[dict] = mapped_column(JSON, default={})
```

### 插件配置表 ([ConfigORM](file:///f:/Cardinal/Pekno/hub/core/database_models.py#41-60))
**现状分析**：
- **键值对结构**：采用 `key` -> `value` 存储模式，非常通用。
- **耦合点**：目前全服共用一张扁平的 KV 表。依靠人工规范 `key` 的前缀（如 `GITHUB_TOKEN`）来区分不同插件。在插件化架构中，可能需要引入 `namespace` 或 `plugin_id` 列来进行配置隔离。
```python
class ConfigORM(Base):
    """用户配置存储表（加密存储敏感信息）"""
    __tablename__ = "configs"

    # 配置键，如 "github_token", "sync_limit" 等
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text)  # 加密后的值
```

---

## 2. 核心业务流 (Core Pipeline & Workflow)
**文件**: [worker/plugins/github/task.py](file:///f:/Cardinal/Pekno/worker/plugins/github/task.py)

### 抓取 (Fetch) 与 查重逻辑 (SHA)
**现状分析**：
- 此过程由 Celery/TaskIQ 后台任务执行。拉取目标对象的列表后，循环检查数据库中存下的 `metadata_extra.get('readme_sha')`。
- 如果 SHA 相同，则认为没有变动触发 **Cache Hit 拦截**；如果不同，重新装配完整的 `metadata_extra`，并丢入消息队列下游等待入库处理。
```python
# --- 抓取与前置处理 ---
readme_content, readme_sha = await client.get_repo_readme(owner, repo_name_only)

# --- 去重检查：对比存储的 sha ---
async with AsyncSessionLocal() as session:
    existing_item = await session.execute(
        select(ItemORM.metadata_extra).where(ItemORM.id == item_id)
    )
    record = existing_item.scalar_one_or_none()
    metadata_extra = record if record is not None else {}
    
    # 核心拦截逻辑
    if record is not None and metadata_extra.get('readme_sha') == readme_sha:
        worker_log.info(f"⏭️ 仓库 README 无更新，触发 Cache Hit 直接跳过: {repo_name}")
        continue

# 重新覆盖并抹除之前的 AI 总结标识
metadata_extra["readme_sha"] = readme_sha
metadata_extra["has_long_summary"] = False
```

### AI 总结逻辑 (Summarize)
**现状分析**：
- 作为独立 Task 执行。调用大模型结束后，利用 SQLAlchemy 的 [update()](file:///f:/Cardinal/Pekno/web/src/store/usePluginStore.ts#27-31) 显式地将大模型的输出填入 [summary](file:///f:/Cardinal/Pekno/hub/core/llm/providers/ollama_adapter.py#13-28)，并给 `metadata_extra` 打上 `has_long_summary: True` 印记。
```python
# 这里调用长文本总结 Prompt
summary = await ai.llm.provider.generate_summary(text_to_summarize, length="long")

# 重新构建 metadata_extra，修改总结状态
new_metadata_extra = dict(metadata_extra)
new_metadata_extra["has_long_summary"] = True

# 提交到 PostgreSQL
await session.execute(
    ItemORM.__table__.update()
    .where(ItemORM.id == item_id)
    .values(
        summary=summary,
        metadata_extra=new_metadata_extra
    )
)
```

---

## 3. API 路由与控制器 (API Routers)
**文件**: [hub/main.py](file:///f:/Cardinal/Pekno/hub/main.py)

**现状分析**：
- 目前 API 路由中存在非常严重的**路径硬绑定**（Hardcoding routing）。像 `/api/sync/github`，`/api/config/github` 是直接把功能点写死在主应用里。
- 未来重构需要将这些改造为如 `/api/plugins/{plugin_id}/sync` 的动态透传路由或利用 FastAPI 的 SubRouter 去做解耦注册。
```python
# 硬编码启动同步的路由
@app.post("/api/sync/github")
async def trigger_github_sync(req: SyncRequest):
    from worker.plugins.github.task import sync_github_stars_task
    await sync_github_stars_task.kiq(limit=req.limit if req.limit else 10)
    return {"status": "accepted"}

# 硬编码特定的 GitHub 配置请求定义
class GitHubConfigRequest(BaseModel):
    token: Optional[str] = None
    sync_limit: int = 100
    auto_sync: bool = False
    
@app.post("/api/config/github")
async def save_github_config(config: GitHubConfigRequest):
    ...
```

---

## 4. 前端状态流 (Frontend State & Types)
**文件**: [web/src/lib/api.ts](file:///f:/Cardinal/Pekno/web/src/lib/api.ts)

**现状分析**：
- 作为卡片流的核心，现在的 [SearchResult](file:///f:/Cardinal/Pekno/web/src/lib/api.ts#13-25) 数据结构非常扁平化（Flat structure）。
- 通用元数据（`title`、`cover_url`），追踪数据（[time](file:///f:/Cardinal/Pekno/hub/main.py#486-512)、`score`），以及特定的功能数据（`has_long_summary`）全挤在一级对象里。
- 缺少专门接管底层 JSON（`metadata_extra`）的对应接口类型。未来的标准化 `IrisItem` 可以把底层数据原样透传给前端，前端让不同的插件组件决定怎么渲染这部分扩展元数据。
```typescript
// 搜索结果的接口定义 (高度扁平化)
export interface SearchResult {
  id: string
  title: string
  summary: string             // 存储段落或 AI 最终结果
  has_long_summary: boolean   // 专门用于控制是否显示/触发 AI 长总结
  cover_url?: string
  score: number               // 混合检索分数
  source: string              // 如 "github_star"，前端依据此渲染 Icon
  tags: string[]
  time: string
}
```
