import httpx
import pytest

from worker.plugins.github.client import GitHubClient


@pytest.mark.asyncio
async def test_get_starred_repos_latest_fetches_only_first_page(monkeypatch):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[{"id": 1}],
            headers={
                "Link": '<https://api.github.com/user/starred?page=2>; rel="next"',
            },
        )

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "worker.plugins.github.client.httpx.AsyncClient",
        lambda *args, **kwargs: original_async_client(transport=transport),
    )

    repos = await GitHubClient("token").get_starred_repos(mode="latest")

    assert repos == [{"id": 1}]
    assert len(requests) == 1
    assert requests[0].url.params["per_page"] == "100"


@pytest.mark.asyncio
async def test_get_starred_repos_full_follows_next_links(monkeypatch):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=[{"id": 1}],
                headers={
                    "Link": '<https://api.github.com/user/starred?page=2>; rel="next"',
                },
            )
        return httpx.Response(200, json=[{"id": 2}])

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "worker.plugins.github.client.httpx.AsyncClient",
        lambda *args, **kwargs: original_async_client(transport=transport),
    )

    repos = await GitHubClient("token").get_starred_repos(mode="full")

    assert repos == [{"id": 1}, {"id": 2}]
    assert len(requests) == 2
    assert requests[0].url.params["per_page"] == "100"
    assert requests[1].url.params["page"] == "2"
