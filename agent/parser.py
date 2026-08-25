from __future__ import annotations

import json
import re
from typing import Any


class AgentParseError(Exception):
    pass


def parse_action(
    raw: str,
) -> dict[str, Any]:

    if not isinstance(raw, str):
        raise AgentParseError(
            "Model output must be a string."
        )

    cleaned = raw.strip()

    cleaned = re.sub(
        r"^```(?:json)?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"```$",
        "",
        cleaned,
    )

    cleaned = (
        cleaned
        .replace(
            "\\_",
            "_",
        )
    )

    # Locate JSON object if Qwen included
    # accidental surrounding text.

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1:
        raise AgentParseError(
            "No JSON object found."
        )

    cleaned = cleaned[start:end + 1]

    try:

        action = json.loads(cleaned)

    except json.JSONDecodeError as exc:

        raise AgentParseError(
            f"Invalid JSON: {exc}"
        ) from exc

    if not isinstance(action, dict):
        raise AgentParseError(
            "Action must be an object."
        )

    if not isinstance(
        action.get("action"),
        str,
    ):
        raise AgentParseError(
            "Action name is missing."
        )

    arguments = action.get(
        "arguments",
        {},
    )

    if not isinstance(
        arguments,
        dict,
    ):
        raise AgentParseError(
            "arguments must be an object."
        )

    return {
        "action": action["action"],
        "arguments": arguments,
    }