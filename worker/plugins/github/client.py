import httpx
from typing import List, Dict, Any
from shared.logger import worker_log

class GitHubClient:
    def __init__(self, token: str = None):
        self.token = token
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if token:
            self.headers["Authorization"] = f"token {self.token}"
        self.base_url = "https://api.github.com"

    async def test_connection(self) -> Dict[str, Any]:
        """
        测试 Token 是否有效（轻量级，只获取用户信息）
        
        Returns:
            包含用户信息的字典
        """
        if not self.token:
            return {"valid": False, "error": "No token provided"}
        
        url = f"{self.base_url}/user"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                user_data = response.json()
                return {
                    "valid": True,
                    "username": user_data.get("login"),
                    "name": user_data.get("name"),
                    "avatar_url": user_data.get("avatar_url"),
                }
            except httpx.HTTPStatusError as e:
                return {"valid": False, "error": f"HTTP {e.response.status_code}"}
            except Exception as e:
                return {"valid": False, "error": str(e)}

    async def get_starred_repos(self, limit: int = 30) -> List[Dict[str, Any]]:
        """获取最近 Star 的仓库"""
        if not self.token:
            worker_log.warning("⚠️ 无 Token，无法获取 Star 仓库")
            return []
            
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

    async def get_repo_readme(self, owner: str, repo: str) -> tuple[str, str]:
        """
        获取仓库的 README 内容
        
        Args:
            owner: 仓库所有者
            repo: 仓库名称
            
        Returns:
            (README 内容, SHA 值)
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/readme"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                
                import base64
                data = response.json()
                content = data.get("content", "")
                sha = data.get("sha", "")
                
                if content:
                    # 解码 base64 内容
                    return base64.b64decode(content).decode('utf-8'), sha
                return "", sha
            except Exception as e:
                worker_log.warning(f"❌ 获取 README 失败: {e}")
                return "", ""

    async def get_repo_languages(self, owner: str, repo: str) -> Dict[str, int]:
        """获取仓库语言分布"""
        url = f"{self.base_url}/repos/{owner}/{repo}/languages"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                worker_log.warning(f"❌ 获取 Languages 失败: {e}")
                return {}