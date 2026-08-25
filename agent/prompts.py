from __future__ import annotations

import json
from typing import Any


SYSTEM_PROMPT = """
You are the decision engine of an automated data extraction system.

Your job is to choose the SINGLE best next action.

You do not execute tools yourself.

You do not invent tools.

You may ONLY select tools listed in AVAILABLE TOOLS.

You must return exactly one JSON object.

Required format:

{
  "action": "tool_name",
  "arguments": {}
}

When the dataset is completely processed:

{
  "action": "finish",
  "arguments": {
    "reason": "..."
  }
}

Rules:

1. Choose exactly one action.
2. Use only registered tools.
3. Use only arguments accepted by the tool.
4. Do not output markdown.
5. Do not output explanations.
6. Do not output <think>.
7. Do not fabricate observations.
8. Prefer deterministic tools when they can perform the task.
9. Use browser tools when direct HTTP acquisition is unavailable
   or the source requires browser interaction.
10. After acquisition, inspect the artifact before parsing it.
11. Validate extracted data before finishing.
""".strip()


def build_messages(
    source_config: dict[str, Any],
    tools: list[dict[str, Any]],
    history: list[dict[str, Any]] | None = None,
    observations: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:

    history = history or []
    observations = observations or []

    user_prompt = f"""
SOURCE CONFIGURATION:

{json.dumps(
    source_config,
    indent=2,
    ensure_ascii=False,
)}


AVAILABLE TOOLS:

{json.dumps(
    tools,
    indent=2,
    ensure_ascii=False,
)}


ACTION HISTORY:

{json.dumps(
    history,
    indent=2,
    ensure_ascii=False,
)}


OBSERVATIONS:

{json.dumps(
    observations,
    indent=2,
    ensure_ascii=False,
)}


Choose the single best next action.

Return ONLY JSON.
""".strip()

    return [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]