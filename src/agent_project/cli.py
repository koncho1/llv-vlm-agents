"""Interactive entry point: where you're going, the weather, and preferences."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_project.agent import MAX_STEPS, run_agent
from agent_project.llm import OpenRouterClient

TRACES_DIR = Path(__file__).resolve().parents[2] / "traces"


def ask_user(name: str, preview: dict[str, Any]) -> bool:
    """Ask the person at the terminal; only an explicit 'yes' approves."""
    print(f"\nThe agent requested {name} on:\n{json.dumps(preview, indent=2)}")
    try:
        return input("Type 'yes' to allow this: ").strip().lower() == "yes"
    except EOFError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Outfit planner agent")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=MAX_STEPS,
        help=(
            "Step budget for this run (course default: "
            f"{MAX_STEPS}). Lower it to reliably demonstrate the "
            "step_limit failure path against the live model."
        ),
    )
    args = parser.parse_args()

    request = input(
        "Describe where you're going, the weather, and any preferences: "
    ).strip()
    if not request:
        print("No request provided.")
        return

    client = OpenRouterClient()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    trace_path = TRACES_DIR / f"run-{stamp}.jsonl"
    result = run_agent(
        client,
        request,
        trace_path=trace_path,
        max_steps=args.max_steps,
        confirm=ask_user,
    )

    if result["status"] == "success":
        print("\n" + result["answer"])
    else:
        print(f"\nRun failed: {result['reason']} after {result['steps']} steps.")
    print(f"\nTrace saved to {trace_path}")


if __name__ == "__main__":
    main()
