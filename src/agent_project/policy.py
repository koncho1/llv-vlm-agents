"""Application-side gate: the model only requests, this code decides what runs."""

import json
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from agent_project.tools import TOOL_ARGS, TOOL_FUNCTIONS, find_saved_outfit

Confirm = Callable[[str, dict[str, Any]], bool]

# Sensitive tools map to a lookup showing the user what the call would affect.
SENSITIVE_TOOLS: dict[str, Callable[..., dict[str, Any]]] = {
    "delete_saved_outfit": find_saved_outfit,
}


def execute_tool(
    name: str,
    arguments: str | dict[str, Any],
    confirm: Confirm | None = None,
) -> dict[str, Any]:
    """Check allowlist, arguments, and confirmation, in that order, then run.

    `confirm` must reach the real user. Nothing in `arguments` can stand in for
    it, because the argument schemas reject unknown fields such as `confirmed`.
    """
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        return {"status": "rejected", "error": f"Unknown tool '{name}'"}
    try:
        parsed = (
            json.loads(arguments or "{}") if isinstance(arguments, str) else arguments
        )
        args = TOOL_ARGS[name].model_validate(parsed).model_dump()
    except json.JSONDecodeError:
        return {"status": "rejected", "error": "Malformed JSON arguments"}
    except ValidationError as exc:
        errors = exc.errors(
            include_url=False, include_context=False, include_input=False
        )
        return {"status": "rejected", "error": f"Invalid arguments: {errors}"}

    try:
        lookup = SENSITIVE_TOOLS.get(name)
        if lookup is not None:
            preview = lookup(**args)
            if preview["status"] == "not_found":
                return preview
            if confirm is None:
                return {
                    "status": "confirmation_required",
                    "error": f"'{name}' needs user confirmation; nothing was changed.",
                }
            if not confirm(name, preview):
                return {
                    "status": "confirmation_denied",
                    "error": f"The user declined '{name}'; nothing was changed.",
                }
        return func(**args)
    except (OSError, ValueError) as exc:
        return {"status": "failed", "error": f"{name} failed: {exc}"}
