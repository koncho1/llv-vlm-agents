"""Read-only tools over the local wardrobe and weather data."""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

Category = Literal["top", "bottom", "outerwear", "shoes", "accessory"]
Formality = Literal["casual", "smart_casual", "formal"]
_FORMALITY_RANK = {"casual": 0, "smart_casual": 1, "formal": 2}


class WeatherQueryArgs(BaseModel):
    condition: str = Field(
        description=(
            "Weather condition keyword, e.g. 'rainy', 'sunny', 'cold', 'hot', "
            "'snowy', 'windy', or 'mild'."
        )
    )


class WardrobeQueryArgs(BaseModel):
    category: Category | None = Field(
        default=None, description="Clothing category to search within."
    )
    weather_tags: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Weather tags an item must all support, e.g. ['rain'].",
    )
    max_formality: Formality | None = Field(
        default=None,
        description="Most formal level allowed (casual < smart_casual < formal).",
    )
    exclude_colors: list[str] = Field(default_factory=list, max_length=10)
    exclude_items: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Item names, ids, or keywords to exclude, e.g. 'white sneakers'.",
    )


def _load_json(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def get_weather_profile(condition: str) -> dict[str, Any]:
    args = WeatherQueryArgs(condition=condition)
    profiles = _load_json("weather_profiles.json")
    key = args.condition.strip().lower()
    profile = profiles.get(key)
    if profile is None:
        return {
            "error": f"Unknown condition '{condition}'",
            "known_conditions": sorted(profiles),
        }
    return {"condition": key, **profile}


def search_wardrobe(**kwargs: Any) -> dict[str, Any]:
    args = WardrobeQueryArgs(**kwargs)
    items = _load_json("wardrobe.json")
    excluded_colors = {c.lower() for c in args.exclude_colors}
    excluded_terms = {i.lower() for i in args.exclude_items}
    required_tags = set(args.weather_tags)
    max_rank = _FORMALITY_RANK[args.max_formality] if args.max_formality else None

    matches = []
    for item in items:
        if args.category and item["category"] != args.category:
            continue
        if item["color"].lower() in excluded_colors:
            continue
        name_words = set(item["name"].lower().split())
        if any(
            term == item["id"] or set(term.split()).issubset(name_words)
            for term in excluded_terms
        ):
            continue
        if required_tags and not required_tags.issubset(set(item["weather_tags"])):
            continue
        if max_rank is not None and _FORMALITY_RANK[item["formality"]] > max_rank:
            continue
        matches.append(item)

    return {"count": len(matches), "items": matches}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather_profile",
            "description": (
                "Look up temperature range, precipitation, wind, and recommended "
                "wardrobe tags for a weather condition keyword."
            ),
            "parameters": WeatherQueryArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_wardrobe",
            "description": (
                "Search the wardrobe inventory for items matching a category, "
                "weather tags, and a maximum formality, excluding given colors "
                "or items."
            ),
            "parameters": WardrobeQueryArgs.model_json_schema(),
        },
    },
]

TOOL_FUNCTIONS = {
    "get_weather_profile": get_weather_profile,
    "search_wardrobe": search_wardrobe,
}
