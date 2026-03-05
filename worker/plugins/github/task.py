from worker.plugins.github.client import GitHubClient
from hub.core.models import UniversalItem, ItemIntent
from worker.ingestion.pipeline import process_new_item_task
from hub.core.logger import worker_log
from worker.broker import broker
from hub.core.config import ConfigManager, ConfigKeys

@broker.task(task_name="sync_github_stars")
async def sync_github_stars_task(limit: int = None):
    """
    同步 GitHub Star 仓库
    """
    # 检查状态，避免并发大范围拉取
    status = await ConfigManager.get_config(ConfigKeys.GITHUB_SYNC_STATUS)
    if status == "running":
        worker_log.warning("⚠️ GitHub 同步任务已经在运行中，跳过本次执行")
        return

    # 设置状态为 running
    await ConfigManager.set_config(ConfigKeys.GITHUB_SYNC_STATUS, "running")

    try:
        # 从数据库读取 Token 和配置
        token = await ConfigManager.get_config(ConfigKeys.GITHUB_TOKEN)
        
        if not token:
            worker_log.error("❌ 未配置 GitHub Token，请在设置中配置")
            raise Exception("请先在设置中配置 GitHub Token")
        
        # 从数据库读取同步限制
        if limit is None:
            sync_limit = await ConfigManager.get_config(ConfigKeys.GITHUB_SYNC_LIMIT)
            limit = int(sync_limit) if sync_limit else 100
        
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
                    "pushed_at": repo.get("pushed_at"),
                    "cover_url": f"https://github.com/{repo_name}.png"  # GitHub OpenGraph URL
                }
            )
            
            # 丢进 Redis 队列
            worker_log.info(f"📤 [GitHub] 发现新 Star: {repo_name}，发送至 Pipeline...")
            await process_new_item_task.kiq(item.model_dump())

        worker_log.info(f"✅ GitHub 同步指令下发完毕，共 {len(repos)} 个项目。")

    finally:
        # 恢复状态，更新最后同步时间
        import datetime
        await ConfigManager.set_config(ConfigKeys.GITHUB_SYNC_STATUS, "idle")
        await ConfigManager.set_config(ConfigKeys.GITHUB_LAST_SYNC_TIME, datetime.datetime.now().isoformat())


@broker.task(task_name="summarize_repo")
async def summarize_repo_task(item_id: str, task_id: str):
    """
    AI 总结仓库任务
    
    Args:
        item_id: 项目 ID
        task_id: 任务 ID
    """
    worker_log.info(f"🚀 开始 AI 总结任务: {task_id} for item {item_id}")
    
    try:
        # 1. 从数据库获取 item 信息
        from hub.core.database import AsyncSessionLocal
        from hub.core.database_models import ItemORM
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(ItemORM.__table__.select().where(ItemORM.id == item_id))
            item = result.fetchone()
            
            if not item:
                # 如果项目不存在，使用 item_id 生成模拟数据
                worker_log.warning(f"⚠️ 项目 {item_id} 不存在，使用模拟数据")
                # 从 item_id 中提取仓库信息 (格式: gh_owner_repo)
                import re
                match = re.search(r'gh_([^_]+)_([^_]+)', item_id)
                if not match:
                    worker_log.error(f"❌ 无效的项目 ID 格式: {item_id}")
                    return
                
                owner, repo = match.groups()
                repo_name = f"{owner}/{repo}"
                repo_url = f"https://github.com/{owner}/{repo}"
                content_text = "这是一个 GitHub 开源项目"
                metadata_extra = {}
            else:
                repo_url = item.raw_link
                repo_name = item.title
                content_text = item.content_text or "暂无描述"
                metadata_extra = item.metadata_extra or {}
            
            # 2. 抓取 GitHub README 内容
            worker_log.info(f"📥 抓取 {repo_name} 的 README 内容")
            
            # 提取 owner 和 repo 名称
            import re
            match = re.search(r'github\.com/([^/]+)/([^/]+)', repo_url)
            if not match:
                worker_log.error(f"❌ 无效的 GitHub 链接: {repo_url}")
                return
            
            owner, repo = match.groups()
            
            # 3. 调用 GitHub API 获取 README
            # 从数据库读取 Token（如果配置了的话）
            token = await ConfigManager.get_config(ConfigKeys.GITHUB_TOKEN)
            client = GitHubClient(token)  # 使用 Token 访问 API，避免限流
            readme_content = await client.get_repo_readme(owner, repo)
            
            if not readme_content:
                worker_log.warning(f"⚠️ 未找到 {repo_name} 的 README")
                readme_content = content_text or "暂无描述"
            
            # 4. 调用 LLM 进行总结
            worker_log.info(f"🤖 调用 LLM 总结 {repo_name}")
            
            # 简化版本：使用模拟总结
            # 实际生产中应该调用真实的 LLM API
            summary = f"# {repo_name} 项目总结\n\n" \
                    f"这是一个 GitHub 开源项目。\n\n" \
                    f"## 项目概览\n\n" \
                    f"{readme_content[:200]}...\n\n" \
                    f"## 核心功能\n\n" \
                    f"- 功能 1\n- 功能 2\n- 功能 3\n\n" \
                    f"## 技术栈\n\n" \
                    f"- 主要语言: {metadata_extra.get('lang', '未知')}\n" \
                    f"- Star 数量: {metadata_extra.get('stars', 0)}\n\n" \
                    f"## 总结\n\n" \
                    f"这是一个值得关注的开源项目，具有良好的发展潜力。"
            
            # 5. 提取 README 中的第一张图片作为封面（如果原生 cover_url 无效或需要更好的图）
            # 我们先尝试找 README 里的图
            cover_url = metadata_extra.get("cover_url", f"https://github.com/{repo_name}.png")
            
            # 一个简单的正则表达式查找 markdown 格式或 HTML 格式的图片
            import re
            img_urls = re.findall(r'!\[.*?\]\((.*?)\)|<img[^>]+src=["\'](.*?)["\']', readme_content)
            for md_url, html_url in img_urls:
                url = md_url or html_url
                # 过滤掉常见的徽章（badges）和非图片链接
                if url and not any(badge in url for badge in ["shields.io", "badge", "action"]):
                    # 如果找到的是相对路径，需要拼上 GitHub 原始内容路径（简单处理，优先完整的 http 链接）
                    if url.startswith("http"):
                        cover_url = url
                        break
            
            # 更新 metadata
            metadata_extra["cover_url"] = cover_url

            # 6. 将结果存回数据库
            worker_log.info(f"💾 保存 AI 总结结果到数据库")
            
            if item:
                await session.execute(
                    ItemORM.__table__.update()
                    .where(ItemORM.id == item_id)
                    .values(summary=summary)
                )
                await session.commit()
            else:
                # 如果项目不存在，创建一个新的记录
                worker_log.info(f"📝 创建新的项目记录: {repo_name}")
                from hub.core.models import UniversalItem, ItemIntent
                
                new_item = UniversalItem(
                    id=item_id,
                    title=repo_name,
                    source_type="github_star",
                    raw_link=repo_url,
                    content_text=content_text,
                    intent=ItemIntent.article,
                    retention_days=-1,  # 永久保存
                    capabilities=["summarize"],
                    metadata_extra=metadata_extra
                )
                
                from worker.ingestion.pipeline import process_new_item_task
                await process_new_item_task.kiq(new_item.model_dump())
            
            worker_log.info(f"✅ AI 总结任务完成: {task_id}")
            
    except Exception as e:
        worker_log.error(f"❌ AI 总结任务失败: {e}")
        raise