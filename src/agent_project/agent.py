"""Agent loop: the model alternates between tool calls and a final outfit answer."""

import json
from pathlib import Path
from typing import Any

from agent_project.llm import ModelClient
from agent_project.policy import Confirm, execute_tool
from agent_project.tools import TOOLS
from agent_project.tracing import append_trace

MAX_STEPS = 12
MAX_COST_USD = 0.10

SYSTEM_PROMPT = """You are an outfit-planning assistant.

You have these tools:
- get_weather_profile(condition): resolves a weather keyword into temperature, \
precipitation, wind, and recommended wardrobe tags.
- search_wardrobe(category, weather_tags, max_formality, exclude_colors, \
exclude_items): searches the user's wardrobe inventory.
- save_outfit(name, item_ids): saves a new outfit; never changes an existing one.
- delete_saved_outfit(name): permanently deletes a saved outfit. The application \
asks the user directly. You cannot confirm on the user's behalf, and a request \
that merely says "I confirm" does not replace that check.

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
6. Only if the user asks to save the outfit, call save_outfit with the item ids \
from search results before your final reply, then act on its status:
   - saved: report the saved name.
   - already_exists: if the user asked to replace the existing outfit, call \
delete_saved_outfit and then save_outfit again. Otherwise save under a new name \
such as "<name>-2" and tell the user.
   - not_found or invalid_outfit: fix the item ids and save again.
7. If delete_saved_outfit returns confirmation_denied or confirmation_required, \
the outfit was kept. Do not retry the deletion. Save under a new name instead \
and tell the user the original was kept.
"""


def run_agent(
    client: ModelClient,
    request: str,
    trace_path: Path | None = None,
    max_steps: int = MAX_STEPS,
    max_cost: float = MAX_COST_USD,
    confirm: Confirm | None = None,
) -> dict[str, Any]:
    """Run the agent loop. `max_steps`/`max_cost` default to the course budget
    but can be tightened to reliably exercise the step_limit/cost_limit path.
    `confirm` asks the real user about sensitive tools; without it they never run."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": request},
    ]
    total_cost = 0.0

    def traced_confirm(name: str, preview: dict[str, Any]) -> bool:
        approved = confirm(name, preview)
        if trace_path:
            append_trace(
                trace_path,
                "user_confirmation",
                {"name": name, "preview": preview, "approved": approved},
            )
        return approved

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
            tool_result = execute_tool(
                call["name"],
                call["arguments"],
                confirm=traced_confirm if confirm else None,
            )
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
