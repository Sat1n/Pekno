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

        from hub.core.database import AsyncSessionLocal
        from hub.core.database_models import ItemORM
        from sqlalchemy import select

        for repo in repos:
            repo_name = repo['full_name']
            owner = repo['owner']['login']
            repo_name_only = repo['name']
            
            item_id = f"gh_{repo['id']}"
            
            # --- 去重检查 ---
            async with AsyncSessionLocal() as session:
                existing_item = await session.execute(
                    select(ItemORM.id).where(ItemORM.id == item_id)
                )
                if existing_item.scalar_one_or_none():
                    worker_log.info(f"⏭️ 仓库已存在，跳过处理: {repo_name}")
                    continue
            
            # Fetch README to extract cover image sequentially to respect rate limits
            cover_url = None
            readme_content = None
            try:
                readme_content = await client.get_repo_readme(owner, repo_name_only)
            except Exception as e:
                pass
                
            if readme_content:
                def to_absolute(url):
                    if not url: return None
                    url = url.split()[0]
                    if url.startswith(("http://", "https://")): return url
                    url = url.lstrip("./")
                    return f"https://raw.githubusercontent.com/{owner}/{repo_name_only}/HEAD/{url}"
                    
                def is_valid_img(url):
                    if not url: return False
                    lower_url = url.lower()
                    if any(b in lower_url for b in ["shields.io", "badge", "action", "sonarcloud", "codecov", "travis"]): return False
                    return True

                import re
                picture_blocks = re.findall(r'<picture\b[^>]*>(.*?)</picture>', readme_content, re.IGNORECASE | re.DOTALL)
                for block in picture_blocks:
                    sources = re.findall(r'<source\b([^>]+)>', block, re.IGNORECASE)
                    best_candidate = None
                    any_candidate = None
                    for source_attrs in sources:
                        srcset_match = re.search(r'srcset=["\']([^"\']+)["\']', source_attrs, re.IGNORECASE)
                        media_match = re.search(r'media=["\']([^"\']+)["\']', source_attrs, re.IGNORECASE)
                        if srcset_match:
                            url = srcset_match.group(1)
                            any_candidate = url
                            if media_match and ('light' in media_match.group(1).lower() or 'no-preference' in media_match.group(1).lower()):
                                best_candidate = url
                                break
                    
                    url = best_candidate or any_candidate
                    if not url:
                        img_match = re.search(r'<img\b[^>]*src=["\']([^"\']+)["\']', block, re.IGNORECASE)
                        if img_match: url = img_match.group(1)
                    
                    abs_url = to_absolute(url)
                    if is_valid_img(abs_url):
                        cover_url = abs_url
                        break
                
                if not cover_url:
                    img_urls = re.findall(r'!\[.*?\]\((.*?)\)|<img\b[^>]*src=["\'](.*?)["\']', readme_content, re.IGNORECASE)
                    for md_url, html_url in img_urls:
                        url = md_url or html_url
                        if url:
                            match = re.match(r'([^\s]+)', url)
                            if match:
                                abs_url = to_absolute(match.group(1))
                                if is_valid_img(abs_url):
                                    cover_url = abs_url
                                    break
            
            metadata_extra = {
                "lang": repo.get("language"),
                "stars": repo.get("stargazers_count"),
                "pushed_at": repo.get("pushed_at")
            }
            if cover_url:
                metadata_extra["cover_url"] = cover_url

            item = UniversalItem(
                id=f"gh_{repo['id']}",
                title=repo_name,
                source_type="github_star",
                raw_link=repo['html_url'],
                content_text=repo['description'] or "",
                intent=ItemIntent.article,
                retention_days=-1,
                capabilities=["summarize"] if repo['description'] else [],
                metadata_extra=metadata_extra
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
            worker_log.info(f"🤖 调用 LLM 总结 {repo_name} (长格式)")
            
            from hub.core.llm.service import LLMManager
            ai = LLMManager()
            
            text_to_summarize = readme_content if readme_content else content_text
            # 这里调用长文本总结 Prompt
            summary = await ai.llm.provider.generate_summary(text_to_summarize, length="long")

            # 6. 将结果存回数据库
            worker_log.info(f"💾 保存 AI 最终汇总结果到数据库")
            
            if item:
                await session.execute(
                    ItemORM.__table__.update()
                    .where(ItemORM.id == item_id)
                    .values(summary=summary)
                )
                await session.commit()
            else:
                worker_log.error(f"❌ 错误：在数据库中未找到目标记录 {item_id}。放弃更新...")
                
            worker_log.info(f"✅ AI 总结任务完成: {task_id}")
            
    except Exception as e:
        worker_log.error(f"❌ AI 总结任务失败: {e}")
        raise