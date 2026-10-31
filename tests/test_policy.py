import json

from agent_project import delete_saved_outfit, execute_tool, save_outfit

OUTFIT = ["w05", "w06", "w11"]


def _saved(path) -> list[str]:
    return [o["name"] for o in json.loads(path.read_text(encoding="utf-8"))]


def test_save_outfit_stores_and_returns_item_names(saved_outfits_path) -> None:
    result = save_outfit("commute", OUTFIT)
    assert result["status"] == "saved"
    assert "Black Waterproof Boots" in result["items"]
    assert _saved(saved_outfits_path) == ["commute"]


def test_save_outfit_never_overwrites_existing_name(saved_outfits_path) -> None:
    save_outfit("commute", OUTFIT)
    result = save_outfit("COMMUTE", ["w01", "w08", "w10"])
    assert result["status"] == "already_exists"
    assert result["outfit"]["item_ids"] == OUTFIT
    assert _saved(saved_outfits_path) == ["commute"]


def test_save_outfit_rejects_unknown_items(saved_outfits_path) -> None:
    result = save_outfit("commute", ["w05", "w06", "w99"])
    assert result == {"status": "not_found", "unknown_item_ids": ["w99"]}
    assert not saved_outfits_path.exists()


def test_save_outfit_rejects_incomplete_or_repeated_categories() -> None:
    assert save_outfit("a", ["w05", "w06"])["missing_categories"] == ["shoes"]
    result = save_outfit("b", ["w05", "w01", "w06", "w11"])
    assert result["repeated_categories"] == ["top"]


def test_delete_saved_outfit_can_undo_a_save(saved_outfits_path) -> None:
    save_outfit("commute", OUTFIT)
    assert delete_saved_outfit("commute")["status"] == "deleted"
    assert _saved(saved_outfits_path) == []


def test_gate_rejects_unknown_tool_and_bad_arguments() -> None:
    assert execute_tool("rm_rf", {})["status"] == "rejected"
    assert execute_tool("save_outfit", "{not json")["status"] == "rejected"
    assert execute_tool("save_outfit", "[1, 2]")["status"] == "rejected"
    result = execute_tool("save_outfit", {"name": "   ", "item_ids": OUTFIT})
    assert "Invalid arguments" in result["error"]
    json.dumps(result)  # must be serializable to reach the model


def test_sensitive_tool_without_confirm_channel_changes_nothing(
    saved_outfits_path,
) -> None:
    save_outfit("commute", OUTFIT)
    result = execute_tool("delete_saved_outfit", {"name": "commute"})
    assert result["status"] == "confirmation_required"
    assert _saved(saved_outfits_path) == ["commute"]


def test_model_cannot_claim_confirmation(saved_outfits_path) -> None:
    save_outfit("commute", OUTFIT)
    asked = []
    result = execute_tool(
        "delete_saved_outfit",
        '{"name": "commute", "confirmed": true}',
        confirm=lambda *call: asked.append(call) or True,
    )
    assert result["status"] == "rejected"
    assert asked == []  # invalid requests never reach the user
    assert _saved(saved_outfits_path) == ["commute"]


def test_denied_confirmation_changes_nothing(saved_outfits_path) -> None:
    save_outfit("commute", OUTFIT)
    result = execute_tool(
        "delete_saved_outfit", {"name": "commute"}, confirm=lambda *_: False
    )
    assert result["status"] == "confirmation_denied"
    assert _saved(saved_outfits_path) == ["commute"]


def test_approved_confirmation_shows_real_target_and_runs_once(
    saved_outfits_path,
) -> None:
    save_outfit("commute", OUTFIT)
    previews = []

    def approve(name, preview):
        previews.append((name, preview))
        return True

    result = execute_tool("delete_saved_outfit", {"name": "commute"}, confirm=approve)
    assert result["status"] == "deleted"
    assert previews[0][0] == "delete_saved_outfit"
    assert previews[0][1]["outfit"]["item_ids"] == OUTFIT
    assert _saved(saved_outfits_path) == []


def test_deleting_missing_outfit_does_not_ask_the_user() -> None:
    asked = []
    result = execute_tool(
        "delete_saved_outfit",
        {"name": "ghost"},
        confirm=lambda *call: asked.append(call) or True,
    )
    assert result["status"] == "not_found"
    assert asked == []


def test_corrupt_store_is_reported_not_raised(saved_outfits_path) -> None:
    saved_outfits_path.write_text("{broken", encoding="utf-8")
    result = execute_tool("save_outfit", {"name": "commute", "item_ids": OUTFIT})
    assert result["status"] == "failed"
