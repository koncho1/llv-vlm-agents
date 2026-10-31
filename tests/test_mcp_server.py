import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def _session_calls(calls: list[tuple[str, dict]]):
    """Talk to the real server over stdio, as any MCP client would."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agent_project.mcp_server"],
        env=dict(os.environ),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            results = [await session.call_tool(n, a) for n, a in calls]
    return {tool.name for tool in listed.tools}, results


def test_server_exposes_only_tools_it_can_safely_gate() -> None:
    names, _ = asyncio.run(_session_calls([]))
    assert names == {"get_weather_profile", "search_wardrobe", "save_outfit"}


def test_server_runs_shared_tools_and_reports_observations(saved_outfits_path) -> None:
    save = {"name": "commute", "item_ids": ["w05", "w06", "w11"]}
    _, results = asyncio.run(
        _session_calls(
            [
                ("search_wardrobe", {"category": "shoes", "weather_tags": ["rain"]}),
                ("save_outfit", save),
                ("save_outfit", save),
                ("save_outfit", {"name": "other", "item_ids": ["w99"]}),
            ]
        )
    )
    search, saved, duplicate, unknown = [r.structuredContent for r in results]

    assert [item["id"] for item in search["items"]] == ["w11"]
    assert saved["status"] == "saved"
    assert duplicate["status"] == "already_exists"
    assert unknown["status"] == "not_found"
    stored = json.loads(saved_outfits_path.read_text(encoding="utf-8"))
    assert [o["name"] for o in stored] == ["commute"]
