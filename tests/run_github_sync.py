import asyncio
import os

from worker.plugins.github.client import GitHubClient


async def test_sync():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("Set GITHUB_TOKEN in your shell before running this smoke test.")

    client = GitHubClient(token)
    repos = await client.get_starred_repos(limit=5)
    for repo in repos:
        owner = (repo.get("owner") or {}).get("login", "unknown")
        print(f"{owner}/{repo.get('name', 'unknown')}")


if __name__ == "__main__":
    asyncio.run(test_sync())
