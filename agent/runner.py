from __future__ import annotations

import json
from typing import Any

from agent.model import QwenModel
from agent.parser import parse_action
from tools.registry import execute_action


class GenericExtractionAgent:
    """
    One generic autonomous extraction agent.

    This class has NO knowledge of:
        - NPCI
        - Railway
        - GEO
        - weather
        - finance
        - any individual dataset

    The dataset definition is supplied at runtime.
    """

    def __init__(
        self,
        registry,
        model: QwenModel | None = None,
        max_steps: int = 25,
    ) -> None:

        self.registry = registry

        self.model = (
            model
            if model is not None
            else QwenModel()
        )

        self.max_steps = max_steps

    def _build_messages(
        self,
        source: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> list[dict[str, str]]:

        source_json = json.dumps(
            source,
            indent=2,
            ensure_ascii=False,
        )

        tools_json = json.dumps(
            self.registry.to_prompt_list(),
            indent=2,
            ensure_ascii=False,
        )

        history_json = json.dumps(
            history[-12:],
            indent=2,
            ensure_ascii=False,
            default=str,
        )

        system_prompt = """
You are the autonomous data extraction agent.

You are responsible for retrieving the exact
dataset described in the dataset specification.

You control deterministic tools.

Your tools may allow you to:

- navigate websites
- inspect webpages
- interact with browser pages
- wait for dynamic content
- download files
- inspect downloaded files
- read PDF files
- read Excel files
- read CSV files
- extract tables
- validate extracted data
- submit structured datasets

CORE RULES

1. The dataset specification is authoritative.

2. Use the official source whenever possible.

3. Do not invent data.

4. Do not guess missing values.

5. Do not silently substitute a similar dataset.

6. Inspect a source before extracting from it.

7. A HTTP 200 response does NOT automatically mean
   that useful data was obtained.

8. Empty pages, anti-bot pages, login pages,
   access-denied pages, challenge pages, and
   error pages are not datasets.

9. If one legitimate acquisition strategy fails,
   inspect the failure and try another available
   strategy when appropriate.

10. Use only registered tools.

11. Never execute arbitrary Python.

12. Never execute shell commands.

13. Never directly modify files outside the
    registered tools.

14. Do not modify the dataset specification.

15. Do not fabricate values to satisfy validation.

16. Do not submit a dataset until you have
    identified the actual requested data.

17. Preserve the source's meaning and granularity.

18. If the requested data cannot currently be
    obtained, report failure instead of inventing
    an answer.

19. You are operating iteratively. The result of
    every tool call becomes an observation for
    your next decision.

20. Choose the NEXT action only.

OUTPUT FORMAT

Return ONLY valid JSON:

{
  "action": "registered_tool_name",
  "arguments": {}
}

Do not return Markdown.
Do not return explanations outside the JSON.
"""

        user_prompt = f"""
DATASET SPECIFICATION
=====================

{source_json}


AVAILABLE TOOLS
===============

{tools_json}


PREVIOUS ACTIONS AND RESULTS
============================

{history_json}


Choose the next action required to retrieve,
understand, extract, validate, or submit the
requested dataset.

Return only the JSON action.
"""

        return [
            {
                "role": "system",
                "content": system_prompt.strip(),
            },
            {
                "role": "user",
                "content": user_prompt.strip(),
            },
        ]

    def run(
        self,
        source: dict[str, Any],
    ) -> dict[str, Any]:

        dataset_id = source[
            "dataset_id"
        ]

        history: list[
            dict[str, Any]
        ] = []

        for step in range(
            1,
            self.max_steps + 1,
        ):

            print()
            print(
                "=" * 70
            )
            print(
                f"AGENT STEP "
                f"{step}/{self.max_steps}"
            )
            print(
                f"DATASET: {source['title']}"
            )
            print(
                "=" * 70
            )

            messages = self._build_messages(
                source,
                history,
            )

            print(
                "[1] Asking Qwen for next action..."
            )

            try:

                raw_response = self.model.generate(
                    messages,
                    mode="tool_selection",
                )

            except Exception as exc:

                return {
                    "success": False,
                    "status": "model_error",
                    "dataset_id": dataset_id,
                    "steps": step,
                    "history": history,
                    "error_type": type(
                        exc
                    ).__name__,
                    "message": str(exc),
                }

            print()
            print(
                "RAW QWEN RESPONSE:"
            )
            print(raw_response)

            try:

                action = parse_action(
                    raw_response
                )

            except Exception as exc:

                print(
                    "ACTION PARSING FAILED:"
                )
                print(exc)

                history.append(
                    {
                        "step": step,
                        "raw_response": raw_response,
                        "parse_error": str(exc),
                    }
                )

                continue

            action_name = action[
                "action"
            ]

            arguments = action.get(
                "arguments",
                {},
            )

            print()
            print(
                "PARSED ACTION:"
            )

            print(
                json.dumps(
                    action,
                    indent=2,
                    ensure_ascii=False,
                )
            )

            if action_name == "finish":

                history.append(
                    {
                        "step": step,
                        "action": action_name,
                        "arguments": arguments,
                    }
                )

                return {
                    "success": True,
                    "status": "finished",
                    "dataset_id": dataset_id,
                    "steps": step,
                    "history": history,
                    "data": None,
                }

            print()
            print(
                f"[2] Executing: "
                f"{action_name}"
            )

            try:

                result = execute_action(
                    self.registry,
                    action_name,
                    arguments,
                )

            except Exception as exc:

                result = {
                    "success": False,
                    "error_type": type(
                        exc
                    ).__name__,
                    "message": str(exc),
                    "recoverable": True,
                }

            print()
            print(
                "TOOL RESULT:"
            )

            print(
                json.dumps(
                    result,
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
            )

            history.append(
                {
                    "step": step,
                    "action": action_name,
                    "arguments": arguments,
                    "result": result,
                }
            )

            # --------------------------------------------------
            # FINAL DATASET SUBMISSION
            # --------------------------------------------------

            if action_name == "submit_dataset":

                if not result.get(
                    "success",
                    False,
                ):

                    continue

                data = result.get(
                    "data"
                )

                if data is None:

                    return {
                        "success": False,
                        "status": (
                            "empty_submission"
                        ),
                        "dataset_id": dataset_id,
                        "steps": step,
                        "history": history,
                        "error_type": (
                            "NoDatasetReturned"
                        ),
                        "message": (
                            "submit_dataset succeeded "
                            "but returned no data."
                        ),
                    }

                return {
                    "success": True,
                    "status": (
                        "dataset_submitted"
                    ),
                    "dataset_id": dataset_id,
                    "steps": step,
                    "history": history,
                    "data": data,
                    "rows": result.get(
                        "row_count"
                    ),
                    "columns": result.get(
                        "columns"
                    ),
                    "confidence": result.get(
                        "confidence"
                    ),
                    "notes": result.get(
                        "notes"
                    ),
                }

            # --------------------------------------------------
            # UNRECOVERABLE TOOL FAILURE
            # --------------------------------------------------

            if (
                result.get(
                    "success",
                    True,
                ) is False
                and result.get(
                    "recoverable",
                    True,
                ) is False
            ):

                return {
                    "success": False,
                    "status": (
                        "unrecoverable_tool_error"
                    ),
                    "dataset_id": dataset_id,
                    "steps": step,
                    "history": history,
                    "error_type": result.get(
                        "error_type"
                    ),
                    "message": result.get(
                        "message"
                    ),
                }

        return {
            "success": False,
            "status": "max_steps_exceeded",
            "dataset_id": dataset_id,
            "steps": self.max_steps,
            "history": history,
            "error_type": (
                "AgentMaxStepsExceeded"
            ),
            "message": (
                f"Agent exceeded the maximum "
                f"of {self.max_steps} steps."
            ),
        }