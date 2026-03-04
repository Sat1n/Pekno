import httpx
from typing import List, Dict, Any
from hub.core.logger import worker_log

class GitHubClient:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        self.base_url = "https://api.github.com"

    async def get_starred_repos(self, limit: int = 30) -> List[Dict[str, Any]]:
        """获取最近 Star 的仓库"""
        url = f"{self.base_url}/user/starred"
        params = {"per_page": limit, "sort": "created", "direction": "desc"}
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                worker_log.error(f"❌ GitHub API 请求失败: {e}")
                return []