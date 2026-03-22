"""
Iris Hub MCP Server Test Script
Usage: python scripts/test_mcp.py
"""
import asyncio
import json
import sys
import io

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

MCP_URL = "http://localhost:8001/api/mcp/sse"
PAT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJTYXRpbiIsInJvbGUiOiJzdXBlcl9hZG1pbiIsInVpZCI6ImJiZjdhZDgyLTE5ZmMtNDE3Zi04MzdkLTU4ZWM3ZDg2OWE4ZSIsInR5cGUiOiJwYXQiLCJqdGkiOiI2MjJmNzVhNi1mZGEwLTRlMmYtOGViOC0wYTI4ZDZmNTU2YWEiLCJleHAiOjQ5Mjc2MjczNDZ9.sSgW-3epZmp3-LLrkILBOLqSR-86PXsa0293JqIYKAw"

HEADERS = {"Authorization": f"Bearer {PAT_TOKEN}"}

async def main():
    print("=" * 60)
    print("[TEST] Iris Hub MCP Server Connection Test")
    print("=" * 60)

    print(f"\n[INFO] Connecting to: {MCP_URL}")
    
    async with sse_client(MCP_URL, headers=HEADERS) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # 1. Initialize handshake
            await session.initialize()
            print("[OK] SSE handshake successful! MCP session established.\n")

            # 2. List available tools
            print("-" * 40)
            print("[INFO] Registered MCP Tools:")
            print("-" * 40)
            tools_result = await session.list_tools()
            for tool in tools_result.tools:
                print(f"  * {tool.name}")
                if tool.description:
                    print(f"    Desc: {tool.description}")
                if tool.inputSchema and tool.inputSchema.get("properties"):
                    params = ", ".join(tool.inputSchema["properties"].keys())
                    print(f"    Params: {params}")
                print()

            # 3. Test Tool 1: get_recent_items
            print("=" * 40)
            print("[TEST 1] get_recent_items(hours_ago=48)")
            print("=" * 40)
            items_data = []
            try:
                result = await session.call_tool("get_recent_items", {"hours_ago": 48})
                content_text = result.content[0].text if result.content else "[]"
                items_data = json.loads(content_text)
                print(f"[OK] Returned {len(items_data)} items")
                for item in items_data[:3]:
                    title = item.get("title", "Untitled")[:60]
                    source = item.get("source", "?")
                    print(f"   [{source}] {title}")
                if len(items_data) > 3:
                    print(f"   ... and {len(items_data) - 3} more")
            except Exception as e:
                print(f"[FAIL] Error: {e}")

            # 4. Test Tool 2: fetch_item_content
            print(f"\n{'=' * 40}")
            print("[TEST 2] fetch_item_content")
            print("=" * 40)
            try:
                if items_data:
                    test_id = items_data[0]["id"]
                    result = await session.call_tool("fetch_item_content", {
                        "item_id": test_id,
                        "request_server_summary": True,
                    })
                    text = result.content[0].text if result.content else "(empty)"
                    print(f"[OK] Content fetched (item_id={test_id[:16]}...)")
                    preview = text[:150].replace("\n", " ")
                    print(f"   Preview: {preview}...")
                else:
                    print("[SKIP] No items available to test")
            except Exception as e:
                print(f"[FAIL] Error: {e}")

            # 5. Test Tool 3: add_to_watch_later
            print(f"\n{'=' * 40}")
            print("[TEST 3] add_to_watch_later")
            print("=" * 40)
            try:
                if items_data:
                    test_id = items_data[0]["id"]
                    result = await session.call_tool("add_to_watch_later", {
                        "item_id": test_id,
                    })
                    text = result.content[0].text if result.content else "(empty)"
                    print(f"[OK] Result: {text}")
                else:
                    print("[SKIP] No items available to test")
            except Exception as e:
                print(f"[FAIL] Error: {e}")

            print(f"\n{'=' * 60}")
            print("[DONE] All tests completed!")
            print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
