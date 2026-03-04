from worker.plugins.github.client import GitHubClient
from hub.core.models import UniversalItem, ItemIntent
from worker.ingestion.pipeline import process_new_item_task
from hub.core.logger import worker_log

async def sync_github_stars_task(token: str, limit: int = 10):
    client = GitHubClient(token)
    repos = await client.get_starred_repos(limit)
    
    if not repos:
        worker_log.warning("⚠️ 未找到任何 Star 仓库，请检查 Token 权限。")
        return

    for repo in repos:
        repo_name = repo['full_name']
        # 构造通用模型
        item = UniversalItem(
            id=f"gh_{repo['id']}",
            title=repo_name,
            source_type="github_star",
            raw_link=repo['html_url'],
            content_text=repo['description'] or "",
            intent=ItemIntent.article,
            # --- 你的冷热分离策略 ---
            retention_days=-1,  # GitHub Star 默认永久保存
            # --- 智能开关：只有当 description 不为空时才值得 AI 总结 ---
            capabilities=["summarize"] if repo['description'] else [],
            metadata_extra={
                "lang": repo.get("language"),
                "stars": repo.get("stargazers_count"),
                "pushed_at": repo.get("pushed_at")
            }
        )
        
        # 丢进 Redis 队列
        worker_log.info(f"📤 [GitHub] 发现新 Star: {repo_name}，发送至 Pipeline...")
        await process_new_item_task.kiq(item.model_dump())

    worker_log.info(f"✅ GitHub 同步指令下发完毕，共 {len(repos)} 个项目。")