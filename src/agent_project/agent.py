"""Agent loop: the model alternates between tool calls and a final outfit answer."""

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agent_project.llm import ModelClient
from agent_project.tools import TOOL_FUNCTIONS, TOOLS
from agent_project.tracing import append_trace

MAX_STEPS = 12
MAX_COST_USD = 0.10

SYSTEM_PROMPT = """You are an outfit-planning assistant.

You have two read-only tools:
- get_weather_profile(condition): resolves a weather keyword into temperature, \
precipitation, wind, and recommended wardrobe tags.
- search_wardrobe(category, weather_tags, max_formality, exclude_colors, \
exclude_items): searches the user's wardrobe inventory.

Process:
1. Call get_weather_profile for the weather mentioned in the request before \
searching the wardrobe. You may request independent tool calls together in \
the same turn.
2. Use the recommended tags from the weather result to search_wardrobe for \
each needed category (top, bottom, shoes, and outerwear when precipitation \
or cold warrants it).
3. If a search returns no items, or only items the user excluded, adjust the \
filters (drop a tag, try another category) and search again rather than \
inventing an item.
4. Respect every exclusion the user states (banned items, colors) exactly; \
never include an excluded item or color in the final outfit.
5. When you have enough information, reply with the final outfit as plain \
text (one item per category, briefly justified by the weather) and do not \
call any more tools.
"""


def run_agent(
    client: ModelClient,
    request: str,
    trace_path: Path | None = None,
    max_steps: int = MAX_STEPS,
    max_cost: float = MAX_COST_USD,
) -> dict[str, Any]:
    """Run the agent loop. `max_steps`/`max_cost` default to the course budget
    but can be tightened to reliably exercise the step_limit/cost_limit path."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": request},
    ]
    total_cost = 0.0

    for step in range(1, max_steps + 1):
        result = client.complete(messages, tools=TOOLS)
        usage = result.get("usage") or {}
        total_cost += usage.get("cost") or 0.0
        if trace_path:
            append_trace(trace_path, "model_response", {"step": step, **result})

        tool_calls = result.get("tool_calls") or []
        if not tool_calls:
            if trace_path:
                append_trace(
                    trace_path, "run_complete", {"step": step, "total_cost": total_cost}
                )
            return {
                "status": "success",
                "answer": result.get("text"),
                "steps": step,
                "cost": total_cost,
            }

        messages.append(
            {
                "role": "assistant",
                "content": result.get("text"),
                "tool_calls": [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": call["arguments"],
                        },
                    }
                    for call in tool_calls
                ],
            }
        )

        for call in tool_calls:
            tool_result = _run_tool(call["name"], call["arguments"])
            if trace_path:
                append_trace(
                    trace_path,
                    "tool_call",
                    {
                        "step": step,
                        "name": call["name"],
                        "arguments": call["arguments"],
                        "result": tool_result,
                    },
                )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(tool_result),
                }
            )

        if total_cost > max_cost:
            if trace_path:
                append_trace(
                    trace_path,
                    "run_failed",
                    {"reason": "cost_limit", "step": step, "total_cost": total_cost},
                )
            return {
                "status": "error",
                "reason": "cost_limit",
                "steps": step,
                "cost": total_cost,
            }

    if trace_path:
        append_trace(
            trace_path,
            "run_failed",
            {"reason": "step_limit", "steps": max_steps, "total_cost": total_cost},
        )
    return {
        "status": "error",
        "reason": "step_limit",
        "steps": max_steps,
        "cost": total_cost,
    }


def _run_tool(name: str, arguments: str) -> dict[str, Any]:
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return {"error": f"Unknown tool '{name}'"}
    try:
        parsed = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError:
        return {"error": "Malformed JSON arguments"}
    try:
        return func(**parsed)
    except ValidationError as exc:
        return {"error": f"Invalid arguments: {exc.errors()}"}
    except TypeError as exc:
        return {"error": f"Invalid arguments: {exc}"}
