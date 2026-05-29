from __future__ import annotations

import argparse
import asyncio
import json
import os

from run_mcp_smoke import MCPDemoClient


DEFAULT_BASE_URL = "http://127.0.0.1:8001/api/mcp"
DEFAULT_PLUGIN_NAME = "github_star"
DEFAULT_SYNC_LIMIT = 100


async def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the admin-only MCP tool update_plugin_config.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base MCP URL")
    parser.add_argument("--token", default=os.getenv("PEKNO_MCP_TOKEN"), help="Admin PAT token, or set PEKNO_MCP_TOKEN")
    parser.add_argument("--plugin-name", default=DEFAULT_PLUGIN_NAME, help="Plugin ID, default: github_star")
    parser.add_argument("--sync-limit", type=int, default=DEFAULT_SYNC_LIMIT, help="New sync_limit value, default: 100")
    args = parser.parse_args()

    if not args.token:
        raise SystemExit("Missing token. Pass --token or set PEKNO_MCP_TOKEN.")

    config_payload = {
        "sync_limit": args.sync_limit,
    }

    async with MCPDemoClient(args.base_url, args.token) as client:
        initialize_response = await client.initialize()
        print("[MCP-ADMIN] Initialize OK")
        print(json.dumps(initialize_response["result"]["serverInfo"], ensure_ascii=False, indent=2))
        print("[MCP-ADMIN] 注意：此工具现在要求 PAT 同时满足 is_admin=true 且 scopes 包含 write:system_config。")

        tools_response = await client.list_tools()
        tool_names = [tool["name"] for tool in tools_response["result"]["tools"]]
        print(f"[MCP-ADMIN] Tools exposed: {', '.join(tool_names)}")

        if "update_plugin_config" not in tool_names:
            raise SystemExit("Tool update_plugin_config is not exposed by the MCP server.")

        response = await client.call_tool(
            request_id=3,
            name="update_plugin_config",
            arguments={
                "plugin_name": args.plugin_name,
                "config_json_str": json.dumps(config_payload, ensure_ascii=False),
            },
        )

        result_text = response["result"]["content"][0]["text"]
        print(f"[MCP-ADMIN] update_plugin_config({args.plugin_name}) returned:")
        print(result_text)

        if "Success:" not in result_text:
            raise SystemExit("Admin MCP tool did not report success.")


if __name__ == "__main__":
    asyncio.run(main())
