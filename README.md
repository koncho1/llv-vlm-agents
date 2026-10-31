# Outfit Planner Agent

## Installation

Clone the repository:

```bash
git clone <your-repository-url>
cd <your-repository-directory>
```

Install uv

```bash
uv sync --locked
cp .env.example .env
```

Add the individual OpenRouter key to `.env`

Verify the setup:

```bash
uv run pytest
```

## Project Brief

- **Project title:** Outfit Planner Agent
- **Intended user:** Anyone deciding what to wear who can describe where they're
  going, the weather, and any preferences or constraints in one sentence.
- **Problem and primary task:** Given a text request (containing destination/occasion,
  weather, constraints such as banned colors or items), return one complete
  outfit — a specific item for each needed category — drawn only from the
  user's own wardrobe data.
- **Why an agent is appropriate:** The weather keyword must first be resolved
  into structured attributes (temperature, precipitation, wind) before the
  wardrobe can be filtered meaningfully. If a wardrobe search comes back empty
  or only with excluded items, the agent must relax or change filters and
  search again. Each tool result changes what gets asked next, so no single
  model call can produce a grounded answer.
- **Planned data:** `data/wardrobe.json` (closet inventory: category, color,
  formality, weather tags) and `data/weather_profiles.json` (condition →
  temperature range, precipitation, wind, recommended wardrobe tags).
- **Tools:** `get_weather_profile(condition)` and `search_wardrobe(category,
  weather_tags, max_formality, exclude_colors, exclude_items)` (read-only),
  `save_outfit(name, item_ids)` (reversible write), and
  `delete_saved_outfit(name)` (sensitive). All are validated with Pydantic
  schemas; see [Tools and Controls](#tools-and-controls).
- **Planned visual input:** Not implemented this milestone. A future option is
  letting the user attach a photo of one item they've already picked, which
  the agent matches remaining pieces against.
- **Success criteria:** On a fixed evaluation set, the agent finishes within
  12 steps and under USD 0.10, returns exactly one item per needed category
  (top, bottom, shoes, and outerwear when precipitation or cold warrants it),
  and never includes an excluded color or item.
- **Non-goals and safety boundaries:** No shopping links or purchase
  suggestions, no appearance or body judgments, no items invented outside
  `data/wardrobe.json`, no live weather API calls.

## Running It

```bash
uv run outfit-planner
```

Enter a request such as `Suggest a casual outfit for rainy weather. No white
sneakers.`. The agent calls `get_weather_profile` to resolve "rainy" into
precipitation/wind/temperature and a recommended tag (`rain`), then calls
`search_wardrobe` per category with that tag and the exclusion applied, and
replies once it has a full outfit. Each run's trace is written to
`traces/run-<timestamp>.jsonl`.

To demonstrate the `step_limit` failure path against the live model, tighten
the per-run budget below the course default of 12:

```bash
uv run outfit-planner --max-steps 2
```

## Tools and Controls

The model can only request a tool. `execute_tool` in
`src/agent_project/policy.py` decides what actually runs.

| Tool | Type | Control in code |
| --- | --- | --- |
| `get_weather_profile` | Read-only | Allowlist and argument schema |
| `search_wardrobe` | Read-only | Allowlist and argument schema |
| `save_outfit` | Reversible write | Also checks state (`already_exists`, `not_found`, `invalid_outfit`) and re-reads the stored result. It only adds an outfit, so deleting it undoes the save |
| `delete_saved_outfit` | Sensitive | Also needs approval from the user at the terminal, for each call |


Argument schemas reject unknown fields, so a `confirmed: true` argument from the
model is refused, and text in a request never counts as approval. Without a way
to ask the user, sensitive tools return `confirmation_required` and change nothing.

Saved outfits are stored in `data/saved_outfits.json` (not committed). Set
`SAVED_OUTFITS_PATH` to use another file.

## MCP Server

```bash
uv run outfit-planner-mcp
```

This starts a local stdio server exposing `get_weather_profile`,
`search_wardrobe`, and `save_outfit`. They run through the same `execute_tool`
and tool functions as the agent. `delete_saved_outfit` is not exposed, because
the server cannot verify that a real user approved a call.

To connect an MCP client, use this server entry:

```json
{
  "mcpServers": {
    "outfit-planner": {
      "command": "uv",
      "args": ["run", "--directory", "<path-to-this-repo>", "outfit-planner-mcp"]
    }
  }
}
```
