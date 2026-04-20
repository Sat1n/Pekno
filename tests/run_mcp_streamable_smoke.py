from __future__ import annotations

import argparse
import asyncio
import json
import os

import httpx


DEFAULT_BASE_URL = "http://127.0.0.1:8001/api/mcp/v2/stream"


class MCPStreamableClient:
    def __init__(self, endpoint_url: str, token: str):
        self.endpoint_url = endpoint_url
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.client.aclose()

    async def request(self, payload: dict) -> dict:
        response = await self.client.post(self.endpoint_url, headers=self.headers, json=payload)
        if response.status_code != 200:
            raise RuntimeError(f"Streamable HTTP request failed: {response.status_code} {response.text}")
        return response.json()

    async def initialize(self) -> dict:
        return await self.request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "Pekno-mcp-streamable-smoke", "version": "1.0.0"},
                },
            }
        )

    async def list_tools(self) -> dict:
        return await self.request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            }
        )

    async def call_tool(self, request_id: int, name: str, arguments: dict) -> dict:
        return await self.request(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {
                    "name": name,
                    "arguments": arguments,
                },
            }
        )


def _extract_tool_text(response_payload: dict) -> str:
    try:
        return response_payload["result"]["content"][0]["text"]
    except Exception as exc:
        raise RuntimeError(
            f"Unexpected Streamable HTTP tool payload: {json.dumps(response_payload, ensure_ascii=False, indent=2)}"
        ) from exc


async def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the MCP Streamable HTTP endpoint.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Streamable MCP endpoint")
    parser.add_argument("--token", default=os.getenv("PEKNO_MCP_TOKEN"), help="Bearer token, or set PEKNO_MCP_TOKEN")
    parser.add_argument("--query", default="bilibili", help="Search query for search_knowledge_base")
    parser.add_argument("--limit", type=int, default=3, help="Search result limit")
    parser.add_argument("--source-type", default=None, help="Optional source_type filter")
    args = parser.parse_args()

    if not args.token:
        raise SystemExit("Missing token. Pass --token or set PEKNO_MCP_TOKEN.")

    async with MCPStreamableClient(args.base_url, args.token) as client:
        initialize_response = await client.initialize()
        print("[MCP-V2] Initialize OK")
        print(json.dumps(initialize_response["result"]["serverInfo"], ensure_ascii=False, indent=2))

        tools_response = await client.list_tools()
        tools = tools_response["result"]["tools"]
        print(f"[MCP-V2] Tools exposed: {', '.join(tool['name'] for tool in tools)}")

        search_response = await client.call_tool(
            request_id=3,
            name="search_knowledge_base",
            arguments={
                "query": args.query,
                "limit": args.limit,
                **({"source_type": args.source_type} if args.source_type else {}),
            },
        )
        search_results = json.loads(_extract_tool_text(search_response))
        print("[MCP-V2] search_knowledge_base returned:")
        print(json.dumps(search_results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
