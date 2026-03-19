import re
from typing import List, Dict, Any
from shared.plugins.base import BasePlugin, PluginContext

class GitHubStarsPlugin(BasePlugin):
    """
    GitHub Star 插件
    负责同步用户的 Star 仓库并交给 Pipeline 处理
    """
    def __init__(self):
        super().__init__()
        self._manifest = {
            "id": "github_stars",
            "name": "GitHub Stars",
            "description": "同步你 Star 的 GitHub 仓库",
            "version": "1.0.0",
            "auto_sync_supported": True,
            "framework_defaults": {
                "retention_hours": -1,
                "auto_short_summary": True,
            },
            "settings_schema": {
                "token": {"type": "string", "secret": True, "label": "Personal Access Token"}
            }
        }

    async def fetch_data(self, ctx: PluginContext) -> List[Dict[str, Any]]:
        """获取目标列表数据 (GitHub API)"""
        limit = ctx.config.get('sync_limit', 100)
        
        ctx.log.info(f"📥 [GitHub] 开始获取 Star 仓库列表 (Limit: {limit})")
        
        # ctx.http 目前是我们在外部初始化好传进来的 GitHubClient
        # 对应 ctx.http = GitHubClient(token)
        repos = await ctx.http.get_starred_repos(limit)
        
        if not repos:
            ctx.log.warning("⚠️ 未找到任何 Star 仓库，请检查 Token 权限。")
            return []
            
        return repos

    def normalize_item(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """清洗原始 JSON 数据为 Iris 标准化模型字典"""
        repo_name = raw_data.get('full_name', '')
        repo_name_only = raw_data.get('name', '')
        owner = raw_data.get('owner', {}).get('login', '')
        repo_id = raw_data.get('id', '')
        html_url = raw_data.get('html_url', '')
        description = raw_data.get('description') or ""

        return {
            "id": f"gh_{repo_id}",
            "title": repo_name,
            "raw_link": html_url,
            "source_type": "github_star",
            "content_text": description,
            "metadata_extra": {
                "lang": raw_data.get("language"),
                "stars": raw_data.get("stargazers_count"),
                "pushed_at": raw_data.get("pushed_at"),
                "owner": owner,
                "repo": repo_name_only
            }
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
            
            return readme_content if readme_content else raw_data.get('description', '')
        except Exception as e:
            ctx.log.warning(f"⚠️ 无法获取 {owner}/{repo_name_only} 的 README: {e}")
            return raw_data.get('description', '')

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
