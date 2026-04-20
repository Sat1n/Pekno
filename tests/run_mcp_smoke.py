from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx


DEFAULT_BASE_URL = "http://127.0.0.1:8001/api/mcp"


@dataclass
class SSEEvent:
    event: str | None
    data: str


class MCPDemoClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}
        self._sse_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=None))
        self._post_client = httpx.AsyncClient(timeout=30.0)
        self._stream_context = None
        self._stream_response: httpx.Response | None = None
        self._line_iterator = None
        self._message_url: str | None = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def connect(self) -> None:
        sse_url = f"{self.base_url}/sse"
        self._stream_context = self._sse_client.stream("GET", sse_url, headers=self.headers)
        self._stream_response = await self._stream_context.__aenter__()
        if self._stream_response.status_code != 200:
            body = await self._stream_response.aread()
            raise RuntimeError(f"SSE connect failed: {self._stream_response.status_code} {body.decode('utf-8', errors='ignore')}")

        self._line_iterator = self._stream_response.aiter_lines()
        endpoint_event = await self.next_event()
        if endpoint_event.event != "endpoint":
            raise RuntimeError(f"Unexpected first SSE event: {endpoint_event.event!r}")

        origin = _origin_from_url(self.base_url)
        self._message_url = urljoin(f"{origin}/", endpoint_event.data.lstrip("/"))
        print(f"[MCP] SSE connected")
        print(f"[MCP] Message endpoint: {self._message_url}")

    async def close(self) -> None:
        if self._stream_context is not None:
            await self._stream_context.__aexit__(None, None, None)
            self._stream_context = None
            self._stream_response = None
        await self._sse_client.aclose()
        await self._post_client.aclose()

    async def next_event(self) -> SSEEvent:
        if self._line_iterator is None:
            raise RuntimeError("SSE stream is not connected.")

        event_name: str | None = None
        data_lines: list[str] = []

        async for line in self._line_iterator:
            if line.startswith(":"):
                continue
            if line == "":
                if event_name or data_lines:
                    return SSEEvent(event=event_name, data="\n".join(data_lines))
                continue
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())

        raise RuntimeError("SSE stream closed before receiving a complete event.")

    async def send_message(self, payload: dict[str, Any]) -> None:
        if not self._message_url:
            raise RuntimeError("Message endpoint is not available.")

        response = await self._post_client.post(
            self._message_url,
            headers={**self.headers, "Content-Type": "application/json"},
            json=payload,
        )
        if response.status_code != 202:
            raise RuntimeError(f"MCP POST failed: {response.status_code} {response.text}")

    async def request(self, payload: dict[str, Any], expect_id: int | str) -> dict[str, Any]:
        await self.send_message(payload)
        while True:
            try:
                event = await self.next_event()
            except httpx.ReadError as exc:
                raise RuntimeError("SSE stream disconnected while waiting for an MCP response.") from exc
            if event.event != "message":
                continue
            data = json.loads(event.data)
            if data.get("id") == expect_id:
                return data

    async def initialize(self) -> dict[str, Any]:
        initialize_response = await self.request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "Pekno-mcp-smoke", "version": "1.0.0"},
                },
            },
            expect_id=1,
        )
        await self.send_message(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }
        )
        return initialize_response

    async def list_tools(self) -> dict[str, Any]:
        return await self.request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
            expect_id=2,
        )

    async def call_tool(self, request_id: int, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self.request(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {
                    "name": name,
                    "arguments": arguments,
                },
            },
            expect_id=request_id,
        )


def _origin_from_url(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError(f"Invalid base URL: {url}")
    return f"{parsed.scheme}://{parsed.netloc}"


def _extract_tool_text(response_payload: dict[str, Any]) -> str:
    try:
        return response_payload["result"]["content"][0]["text"]
    except Exception as exc:
        raise RuntimeError(f"Unexpected MCP tool payload: {json.dumps(response_payload, ensure_ascii=False, indent=2)}") from exc


async def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the mounted Pekno MCP SSE server.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base MCP URL, default: http://127.0.0.1:8001/api/mcp")
    parser.add_argument("--token", default=os.getenv("PEKNO_MCP_TOKEN"), help="Bearer token. You can also set PEKNO_MCP_TOKEN.")
    parser.add_argument("--query", default="bilibili", help="Search query for search_knowledge_base")
    parser.add_argument("--limit", type=int, default=3, help="Search result limit")
    parser.add_argument("--source-type", default=None, help="Optional source_type filter")
    parser.add_argument("--item-id", default=None, help="Optional explicit item_id for read_item_content")
    parser.add_argument("--read-first-result", action="store_true", help="If no --item-id is provided, read the first search result")
    args = parser.parse_args()

    if not args.token:
        raise SystemExit("Missing token. Pass --token or set PEKNO_MCP_TOKEN.")

    async with MCPDemoClient(args.base_url, args.token) as client:
        initialize_response = await client.initialize()
        print("[MCP] Initialize OK")
        print(json.dumps(initialize_response["result"]["serverInfo"], ensure_ascii=False, indent=2))

        tools_response = await client.list_tools()
        tools = tools_response["result"]["tools"]
        print(f"[MCP] Tools exposed: {', '.join(tool['name'] for tool in tools)}")

        search_response = await client.call_tool(
            request_id=3,
            name="search_knowledge_base",
            arguments={
                "query": args.query,
                "limit": args.limit,
                **({"source_type": args.source_type} if args.source_type else {}),
            },
        )
        search_text = _extract_tool_text(search_response)
        search_results = json.loads(search_text)
        print("[MCP] search_knowledge_base returned:")
        print(json.dumps(search_results, ensure_ascii=False, indent=2))

        target_item_id = args.item_id
        if not target_item_id and args.read_first_result and search_results:
            target_item_id = search_results[0]["id"]

        if target_item_id:
            read_response = await client.call_tool(
                request_id=4,
                name="read_item_content",
                arguments={"item_id": target_item_id},
            )
            read_text = _extract_tool_text(read_response)
            print(f"[MCP] read_item_content for {target_item_id}:")
            print(read_text[:4000])
        else:
            print("[MCP] Skip read_item_content. Pass --item-id or add --read-first-result.")


if __name__ == "__main__":
    asyncio.run(main())
