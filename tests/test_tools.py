import pytest
from pydantic import ValidationError

from agent_project.tools import get_weather_profile, search_wardrobe


def test_get_weather_profile_known_condition() -> None:
    profile = get_weather_profile("Rainy")
    assert profile["condition"] == "rainy"
    assert profile["recommended_tags"] == ["rain"]
    assert profile["precipitation"] == "high"


def test_get_weather_profile_unknown_condition() -> None:
    profile = get_weather_profile("tornado")
    assert "error" in profile
    assert "rainy" in profile["known_conditions"]


def test_search_wardrobe_filters_by_category_and_tags() -> None:
    result = search_wardrobe(category="outerwear", weather_tags=["rain"])
    names = {item["name"] for item in result["items"]}
    assert "Navy Waterproof Rain Jacket" in names
    assert "Beige Trench Coat" in names
    assert all(item["category"] == "outerwear" for item in result["items"])


def test_search_wardrobe_excludes_items_by_keyword() -> None:
    result = search_wardrobe(
        category="shoes", weather_tags=["mild"], exclude_items=["white sneakers"]
    )
    names = {item["name"] for item in result["items"]}
    assert "White Canvas Sneakers" not in names
    assert "Grey Running Shoes" in names


def test_search_wardrobe_excludes_colors() -> None:
    result = search_wardrobe(category="top", exclude_colors=["white"])
    assert all(item["color"] != "white" for item in result["items"])


def test_search_wardrobe_respects_max_formality() -> None:
    result = search_wardrobe(category="bottom", max_formality="casual")
    assert all(item["formality"] == "casual" for item in result["items"])


def test_search_wardrobe_rejects_unknown_category() -> None:
    with pytest.raises(ValidationError):
        search_wardrobe(category="hat")
