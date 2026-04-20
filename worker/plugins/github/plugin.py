import re
from typing import List, Dict, Any
import httpx
from shared.plugins.base import BasePlugin, PluginContext

class GitHubStarsPlugin(BasePlugin):
    """
    GitHub stars plugin.
    Syncs starred repositories and hands them off to the ingestion pipeline.
    """
    def __init__(self):
        super().__init__()
        self._manifest = {
            "id": "github_stars",
            "name": "GitHub Stars",
            "source_type": "github_star",
            "description": "Sync the repositories you starred on GitHub.",
            "version": "1.0.0",
            "required_credentials": ["github"],
            "auto_sync_supported": True,
            "framework_defaults": {
                "retention_hours": -1,
                "auto_short_summary": True,
                "auto_sync": True,
                "auto_sync_interval": 5,
            },
            "settings_schema": {}
        }

    async def fetch_data(self, ctx: PluginContext) -> List[Dict[str, Any]]:
        """Fetch starred repositories from the GitHub API."""
        limit = ctx.config.get('sync_limit', 100)
        
        ctx.log.info(f"📥 [GitHub] Fetching starred repositories (limit: {limit})")
        
        # ctx.http 目前是我们在外部初始化好传进来的 GitHubClient
        # 对应 ctx.http = GitHubClient(token)
        repos = await ctx.http.get_starred_repos(limit)
        
        if not repos:
            ctx.log.warning("⚠️ No starred repositories were returned. Please verify the token permissions.")
            return []
            
        return repos

    def normalize_item(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw GitHub API data into the universal item format."""
        repo_id = raw_data.get('id', '')
        owner = raw_data.get('owner', {}).get('login', '')
        repo = raw_data.get('name', '') # Assuming 'repo' refers to the repository name only
        uid = f"gh_{repo_id}"
        tags = [] # Assuming tags should be an empty list or derived elsewhere if needed

        metadata_extra = {
            "stars": raw_data.get("stargazers_count", 0),
            "owner": owner,
            "repo": repo,
            "pushed_at": raw_data.get("pushed_at"),
            "lang": raw_data.get("language")
        }

        # Retrieve any previously computed hover blocks during fetch
        hover_blocks = raw_data.get("metadata_extra", {}).get("hover_blocks")
        if hover_blocks is not None:
            metadata_extra["hover_blocks"] = hover_blocks

        return {
            "id": uid,
            "title": f"{owner}/{repo}",
            "source_type": "github_star",
            "raw_link": raw_data.get("html_url", ""),
            "content_text": raw_data.get("description", ""),
            "intent": "article",
            "tags": tags,
            "metadata_extra": metadata_extra
        }

    async def extract_text_for_ai(self, ctx: PluginContext, raw_data: Dict[str, Any]) -> str:
        """为 AI 准备提取的素材 (如 GitHub README)"""
        owner = raw_data.get('metadata_extra', {}).get('owner') or raw_data.get('owner', {}).get('login')
        repo_name_only = raw_data.get('metadata_extra', {}).get('repo') or raw_data.get('name')
        
        if not owner or not repo_name_only:
            return raw_data.get('description') or ""
            
        try:
            # 抓取 README (content, sha)
            readme_content, readme_sha = await ctx.http.get_repo_readme(owner, repo_name_only)
            
            # 将 README sha 和获取到的封面图片放回 raw_data 的 metadata_extra 里 (以备 Task/Pipeline 后续检查)
            if 'metadata_extra' not in raw_data:
                raw_data['metadata_extra'] = {}
                
            raw_data['metadata_extra']['readme_sha'] = readme_sha
            
            # 提取封面 URL
            cover_url = self._extract_cover_url(readme_content, owner, repo_name_only)
            if cover_url:
                raw_data['metadata_extra']['cover_url'] = cover_url
                
            # ✨ 新增：预计算 Hover Blocks
            try:
                lang_data = await ctx.http.get_repo_languages(owner, repo_name_only)
                blocks = []
                kv_block = {
                    "block_type": "kv",
                    "kv_data": {
                        "Stars": raw_data.get("stargazers_count", raw_data.get("metadata_extra", {}).get("stars", 0)),
                        "Forks": raw_data.get("forks_count", 0),
                        "Issues": raw_data.get("open_issues_count", 0)
                    }
                }
                blocks.append(kv_block)
                if lang_data:
                    total_bytes = sum(lang_data.values())
                    if total_bytes > 0:
                        progress_items = []
                        for lang, bytes_count in sorted(lang_data.items(), key=lambda x: x[1], reverse=True):
                            percentage = (bytes_count / total_bytes) * 100
                            if percentage >= 1.0:
                                progress_items.append({"label": lang, "value": percentage})
                        if progress_items:
                            blocks.append({"block_type": "progress", "items": progress_items})
                
                raw_data['metadata_extra']['hover_blocks'] = blocks
            except Exception as e:
                ctx.log.warning(f"⚠️ 预计算 Hover Block 发生错误: {e}")
            
            return readme_content if readme_content else raw_data.get('description', '')
        except Exception as e:
            ctx.log.warning(f"⚠️ 无法获取 {owner}/{repo_name_only} 的 README: {e}")
            return raw_data.get('description', '')

    async def parse_single_item(self, url: str, ctx: PluginContext | None = None) -> Dict[str, Any]:
        match = re.search(r'github\.com/([^/]+)/([^/?#]+)', url)
        if not match:
            raise ValueError("请提供有效的 GitHub 仓库链接")

        owner = match.group(1)
        repo = match.group(2).removesuffix(".git")
        api_url = f"https://api.github.com/repos/{owner}/{repo}"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Pekno-Hub/1.0",
        }
        if ctx and ctx.config.get("token"):
            headers["Authorization"] = f"Bearer {ctx.config['token']}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(api_url, headers=headers)
            response.raise_for_status()
            repo_data = response.json()

        normalized = self.normalize_item(repo_data)
        normalized["_pipeline_raw_data"] = repo_data
        return normalized

    def _extract_cover_url(self, readme_content: str, owner: str, repo: str):
        """内部方法: 从 README 提取首图"""
        if not readme_content:
            return None
            
        def to_absolute(url):
            if not url: return None
            url = url.split()[0]
            if url.startswith(("http://", "https://")): return url
            url = url.lstrip("./")
            return f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{url}"
            
        def is_valid_img(url):
            if not url: return False
            lower_url = url.lower()
            if any(b in lower_url for b in ["shields.io", "badge", "action", "sonarcloud", "codecov", "travis"]): return False
            return True

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
                return abs_url
        
        img_urls = re.findall(r'!\[.*?\]\((.*?)\)|<img\b[^>]*src=["\'](.*?)["\']', readme_content, re.IGNORECASE)
        for md_url, html_url in img_urls:
            url = md_url or html_url
            if url:
                match = re.match(r'([^\s]+)', url)
                if match:
                    abs_url = to_absolute(match.group(1))
                    if is_valid_img(abs_url):
                        return abs_url
        return None

    async def get_hover_blocks(self, item_url: str, user_config: dict) -> list[dict]:
        """为 GitHub 仓库生成动态 Hover SDUI 数据"""
        match = re.search(r'github\.com/([^/]+)/([^/]+)', item_url)
        if not match:
            return []
            
        owner = match.group(1)
        repo = match.group(2).rstrip('/')
        
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Pekno-Hub/1.0'
        }
        token = user_config.get('token')
        if token:
            headers['Authorization'] = f'Bearer {token}'
            
        async with httpx.AsyncClient() as client:
            # 1. Fetch Repository Details
            repo_res = await client.get(f'https://api.github.com/repos/{owner}/{repo}', headers=headers)
            if repo_res.status_code != 200:
                self._log_warning(f"获取 GitHub Repo 失败: {repo_res.status_code}")
                return []
            repo_data = repo_res.json()
            
            # 2. Fetch Languages
            lang_res = await client.get(f'https://api.github.com/repos/{owner}/{repo}/languages', headers=headers)
            lang_data = lang_res.json() if lang_res.status_code == 200 else {}
            
        blocks = []
        
        # Assemble KVBlock
        kv_block = {
            "block_type": "kv",
            "kv_data": {
                "Stars": repo_data.get("stargazers_count", 0),
                "Forks": repo_data.get("forks_count", 0),
                "Issues": repo_data.get("open_issues_count", 0)
            }
        }
        blocks.append(kv_block)
        
        # Assemble ProgressBlock
        if lang_data:
            total_bytes = sum(lang_data.values())
            progress_items = []
            if total_bytes > 0:
                for lang, bytes_count in sorted(lang_data.items(), key=lambda x: x[1], reverse=True):
                    percentage = (bytes_count / total_bytes) * 100
                    if percentage >= 1.0: # Filter out < 1%
                        progress_items.append({
                            "label": lang,
                            "value": percentage
                        })
                
                if progress_items:
                    progress_block = {
                        "block_type": "progress",
                        "items": progress_items
                    }
                    blocks.append(progress_block)
                    
        return blocks
        
    def _log_warning(self, msg: str):
        # A simple fallback logger since we don't have ctx here
        import logging
        logging.getLogger("uvicorn.error").warning(msg)
