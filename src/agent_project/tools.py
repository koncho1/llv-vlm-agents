"""Tools over the local wardrobe, weather, and saved-outfit data.

Read-only: get_weather_profile, search_wardrobe.
Reversible write: save_outfit (only adds, never changes an existing outfit).
Sensitive: delete_saved_outfit (destroys data; see policy.py for the gate).
"""

import json
import os
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

Category = Literal["top", "bottom", "outerwear", "shoes", "accessory"]
Formality = Literal["casual", "smart_casual", "formal"]
OutfitName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)
]
_FORMALITY_RANK = {"casual": 0, "smart_casual": 1, "formal": 2}
_REQUIRED_CATEGORIES = {"top", "bottom", "shoes"}


class WeatherQueryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition: str = Field(
        description=(
            "Weather condition keyword, e.g. 'rainy', 'sunny', 'cold', 'hot', "
            "'snowy', 'windy', or 'mild'."
        )
    )


class WardrobeQueryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


class SaveOutfitArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: OutfitName = Field(description="Unique name for the saved outfit.")
    item_ids: list[str] = Field(
        min_length=1,
        max_length=8,
        description="Wardrobe item ids, e.g. ['w05', 'w06', 'w11'].",
    )


class DeleteOutfitArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: OutfitName = Field(description="Name of the saved outfit to delete.")


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


def _saved_outfits_path() -> Path:
    return Path(os.getenv("SAVED_OUTFITS_PATH") or DATA_DIR / "saved_outfits.json")


def _load_saved_outfits() -> list[dict[str, Any]]:
    path = _saved_outfits_path()
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _write_saved_outfits(outfits: list[dict[str, Any]]) -> None:
    path = _saved_outfits_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(json.dumps(outfits, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _find_outfit(outfits: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    key = name.casefold()
    return next((o for o in outfits if o["name"].casefold() == key), None)


def find_saved_outfit(name: str) -> dict[str, Any]:
    args = DeleteOutfitArgs(name=name)
    outfits = _load_saved_outfits()
    outfit = _find_outfit(outfits, args.name)
    if outfit is None:
        return {
            "status": "not_found",
            "name": args.name,
            "saved_names": [o["name"] for o in outfits],
        }
    return {"status": "found", "outfit": outfit}


def save_outfit(name: str, item_ids: list[str]) -> dict[str, Any]:
    args = SaveOutfitArgs(name=name, item_ids=item_ids)
    outfits = _load_saved_outfits()
    existing = _find_outfit(outfits, args.name)
    if existing is not None:
        return {"status": "already_exists", "outfit": existing}

    wardrobe = {item["id"]: item for item in _load_json("wardrobe.json")}
    unknown = [item_id for item_id in args.item_ids if item_id not in wardrobe]
    if unknown:
        return {"status": "not_found", "unknown_item_ids": unknown}

    categories = [wardrobe[item_id]["category"] for item_id in args.item_ids]
    missing = sorted(_REQUIRED_CATEGORIES - set(categories))
    repeated = sorted(
        {c for c in categories if c != "accessory" and categories.count(c) > 1}
    )
    if missing or repeated or len(set(args.item_ids)) != len(args.item_ids):
        return {
            "status": "invalid_outfit",
            "missing_categories": missing,
            "repeated_categories": repeated,
        }

    outfit = {"name": args.name, "item_ids": args.item_ids}
    _write_saved_outfits([*outfits, outfit])
    if _find_outfit(_load_saved_outfits(), args.name) != outfit:
        return {"status": "failed", "error": "Outfit was not stored correctly"}
    return {
        "status": "saved",
        "outfit": outfit,
        "items": [wardrobe[item_id]["name"] for item_id in args.item_ids],
    }


def delete_saved_outfit(name: str) -> dict[str, Any]:
    args = DeleteOutfitArgs(name=name)
    outfits = _load_saved_outfits()
    outfit = _find_outfit(outfits, args.name)
    if outfit is None:
        return {"status": "not_found", "name": args.name}
    _write_saved_outfits([o for o in outfits if o is not outfit])
    return {"status": "deleted", "outfit": outfit}


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
    {
        "type": "function",
        "function": {
            "name": "save_outfit",
            "description": (
                "Save a new outfit under a unique name. Needs one top, bottom, and "
                "shoes. Never changes an existing outfit: returns status "
                "'already_exists' if the name is taken."
            ),
            "parameters": SaveOutfitArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_saved_outfit",
            "description": (
                "Permanently delete a saved outfit. The application asks the user "
                "to confirm before anything is deleted."
            ),
            "parameters": DeleteOutfitArgs.model_json_schema(),
        },
    },
]

TOOL_FUNCTIONS = {
    "get_weather_profile": get_weather_profile,
    "search_wardrobe": search_wardrobe,
    "save_outfit": save_outfit,
    "delete_saved_outfit": delete_saved_outfit,
}

TOOL_ARGS: dict[str, type[BaseModel]] = {
    "get_weather_profile": WeatherQueryArgs,
    "search_wardrobe": WardrobeQueryArgs,
    "save_outfit": SaveOutfitArgs,
    "delete_saved_outfit": DeleteOutfitArgs,
}
