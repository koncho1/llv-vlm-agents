import json

from agent_project import MockClient, run_agent


def _tool_call(call_id: str, name: str, arguments: dict) -> dict:
    call = {"id": call_id, "name": name, "arguments": json.dumps(arguments)}
    return {"text": None, "tool_calls": [call], "usage": {"cost": 0.001}}


def _final_answer(text: str) -> dict:
    return {"text": text, "tool_calls": [], "usage": {"cost": 0.001}}


def _events(trace_path) -> list[dict]:
    return [json.loads(line) for line in trace_path.read_text().splitlines()]


def test_successful_run_resolves_weather_then_wardrobe(tmp_path) -> None:
    client = MockClient(
        [
            _tool_call("1", "get_weather_profile", {"condition": "rainy"}),
            _tool_call(
                "2",
                "search_wardrobe",
                {
                    "category": "shoes",
                    "weather_tags": ["rain"],
                    "exclude_items": ["white sneakers"],
                },
            ),
            _final_answer("Navy rain jacket, dark jeans, and black waterproof boots."),
        ]
    )

    trace_path = tmp_path / "success.jsonl"
    request = "Suggest a casual outfit for rainy weather. No white sneakers."
    result = run_agent(client, request, trace_path)

    assert result["status"] == "success"
    assert "boots" in result["answer"]
    assert result["steps"] == 3

    event_names = [event["event"] for event in _events(trace_path)]
    assert event_names == [
        "model_response",
        "tool_call",
        "model_response",
        "tool_call",
        "model_response",
        "run_complete",
    ]


def test_unsuccessful_run_hits_step_limit(tmp_path) -> None:
    looping_call = _tool_call("1", "get_weather_profile", {"condition": "mild"})
    client = MockClient([looping_call] * 12)

    trace_path = tmp_path / "failure.jsonl"
    result = run_agent(client, "Suggest an outfit.", trace_path)

    assert result["status"] == "error"
    assert result["reason"] == "step_limit"
    assert result["steps"] == 12

    last_event = _events(trace_path)[-1]
    assert last_event["event"] == "run_failed"
    assert last_event["payload"]["reason"] == "step_limit"


def test_max_steps_override_tightens_the_budget(tmp_path) -> None:
    looping_call = _tool_call("1", "get_weather_profile", {"condition": "mild"})
    client = MockClient([looping_call] * 3)

    trace_path = tmp_path / "tight_budget.jsonl"
    result = run_agent(client, "Suggest an outfit.", trace_path, max_steps=3)

    assert result["status"] == "error"
    assert result["reason"] == "step_limit"
    assert result["steps"] == 3


def test_unknown_tool_name_reports_error_without_crashing(tmp_path) -> None:
    client = MockClient(
        [
            _tool_call("1", "lookup_horoscope", {}),
            _final_answer("Fallback outfit: grey t-shirt, jeans, running shoes."),
        ]
    )

    trace_path = tmp_path / "unknown_tool.jsonl"
    result = run_agent(client, "Suggest an outfit.", trace_path)

    assert result["status"] == "success"
    tool_event = next(e for e in _events(trace_path) if e["event"] == "tool_call")
    assert "error" in tool_event["payload"]["result"]


def test_invalid_tool_arguments_report_validation_error(tmp_path) -> None:
    client = MockClient(
        [
            _tool_call("1", "search_wardrobe", {"category": "hat"}),
            _final_answer("Here is an outfit despite the earlier bad filter."),
        ]
    )

    trace_path = tmp_path / "invalid_args.jsonl"
    result = run_agent(client, "Suggest an outfit.", trace_path)

    assert result["status"] == "success"
    tool_event = next(e for e in _events(trace_path) if e["event"] == "tool_call")
    assert "Invalid arguments" in tool_event["payload"]["result"]["error"]
