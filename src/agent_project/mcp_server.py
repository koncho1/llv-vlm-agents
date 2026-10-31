"""Local stdio MCP server exposing the agent's tools through the same gate.

delete_saved_outfit is deliberately not exposed: this server cannot verify that
a real user approved a call, so a remote client could never pass the gate.
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

from agent_project.policy import execute_tool
from agent_project.tools import Category, Formality

mcp = FastMCP("outfit-planner")


@mcp.tool()
def get_weather_profile(condition: str) -> dict[str, Any]:
    """Look up temperature, precipitation, wind, and wardrobe tags for a condition."""
    return execute_tool("get_weather_profile", {"condition": condition})


@mcp.tool()
def search_wardrobe(
    category: Category | None = None,
    weather_tags: list[str] | None = None,
    max_formality: Formality | None = None,
    exclude_colors: list[str] | None = None,
    exclude_items: list[str] | None = None,
) -> dict[str, Any]:
    """Search the wardrobe by category, weather tags, formality, and exclusions."""
    return execute_tool(
        "search_wardrobe",
        {
            "category": category,
            "weather_tags": weather_tags or [],
            "max_formality": max_formality,
            "exclude_colors": exclude_colors or [],
            "exclude_items": exclude_items or [],
        },
    )


@mcp.tool()
def save_outfit(name: str, item_ids: list[str]) -> dict[str, Any]:
    """Save a new outfit under a unique name; never changes an existing outfit."""
    return execute_tool("save_outfit", {"name": name, "item_ids": item_ids})


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
