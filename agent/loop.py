from __future__ import annotations

from typing import Any, Callable

from .model import ModelClient
from .parser import parse_action
from .prompts import build_messages


class AgentLoopError(Exception):
    pass


def run_agent(
    *,
    model: ModelClient,
    source_config: dict[str, Any],
    tools: list[dict[str, Any]],
    execute_tool: Callable[
        [str, dict[str, Any]],
        dict[str, Any],
    ],
    max_steps: int = 20,
) -> dict[str, Any]:

    history: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []

    for step in range(
        1,
        max_steps + 1,
    ):

        messages = build_messages(
            source_config=source_config,
            tools=tools,
            history=history,
            observations=observations,
        )

        raw = model.generate(
            messages,
            mode="tool_selection",
        )

        action = parse_action(raw)

        action_name = action["action"]
        arguments = action["arguments"]

        history.append({
            "step": step,
            "action": action,
            "raw_response": raw,
        })

        if action_name == "finish":

            return {
                "success": True,
                "status": "finished",
                "steps": step,
                "reason": arguments.get(
                    "reason",
                    "",
                ),
                "history": history,
                "observations": observations,
            }

        result = execute_tool(
            action_name,
            arguments,
        )

        observations.append({
            "step": step,
            "action": action_name,
            "result": result,
        })

        if (
            not result.get("success", False)
            and not result.get(
                "recoverable",
                False,
            )
        ):

            return {
                "success": False,
                "status": "tool_failure",
                "steps": step,
                "history": history,
                "observations": observations,
            }

    return {
        "success": False,
        "status": "max_steps_exceeded",
        "steps": max_steps,
        "history": history,
        "observations": observations,
    }