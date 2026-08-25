from __future__ import annotations

import json
import re
from typing import Any

from agent.model import QwenModel

from tools.dataset_output import (
    clear_submission_context,
    set_submission_context,
)

from tools.definitions import (
    build_registry,
)

from tools.registry import (
    execute_action,
)


class GenericExtractionAgent:
    """
    Generic autonomous extraction agent.

    One agent can process any dataset definition.

    The agent autonomously decides how to:

        1. Find the requested dataset.
        2. Navigate the source website.
        3. Download the underlying artifact.
        4. Inspect the artifact.
        5. Extract the requested data.
        6. Validate the extracted data.
        7. Submit the final structured dataset.

    No dataset-specific run.py or parse.py is required.
    """

    # ----------------------------------------------------------
    # T4-safe limits
    # ----------------------------------------------------------

    MAX_STEPS = 12

    # Maximum number of previous messages retained.
    #
    # We keep the initial system/user messages plus only the
    # most recent tool interaction history.
    MAX_HISTORY_MESSAGES = 8

    # Maximum characters returned to the model from one tool.
    MAX_TOOL_RESULT_CHARS = 12000

    def __init__(
        self,
        model: QwenModel,
    ) -> None:

        self.model = model

        self.registry = (
            build_registry()
        )

    # ==========================================================
    # PROMPT
    # ==========================================================

    def _build_prompt(
        self,
        dataset: dict[str, Any],
    ) -> list[dict[str, str]]:
        """
        Build the initial Qwen conversation.

        The prompt is intentionally compact because the model is
        running on a 14.56 GB Tesla T4.
        """

        tools = json.dumps(
            self.registry.to_prompt_list(),
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
        )

        dataset_json = json.dumps(
            dataset,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
        )

        system_prompt = """
You are an autonomous data extraction agent.

Extract ONE requested dataset from an official or
authoritative source.

You have access ONLY to the registered tools.

Your objective is actual structured data, not merely
a webpage description or a downloaded file.

========================================================
ACQUISITION
========================================================

Start from data_link.

Possible source types include:

- direct downloadable file
- normal webpage
- dynamic JavaScript website
- page containing download links
- page containing multiple datasets

Prefer:

1. http_download for a direct file.
2. browser_open/browser_inspect for websites.
3. Use browser navigation to discover the actual
   downloadable resource when direct HTTP fails.

Do not repeatedly retry the same failed method.

========================================================
FILE EXTRACTION
========================================================

After downloading a file:

1. inspect_file
2. choose the appropriate reader

PDF:
    read_pdf
    extract_pdf_table

CSV:
    read_csv

Excel:
    read_excel

Extract ACTUAL records.

Preserve source values.

Never invent records, columns, URLs, or values.

========================================================
DATASET MATCHING
========================================================

Use the supplied dataset definition:

data_title
data_description
data_scope
granularity
time_granularity

Only extract records belonging to the requested dataset.

========================================================
VALIDATION
========================================================

Before submission:

- confirm records exist
- check row consistency
- check relevant required fields
- check obvious extraction corruption

Do not submit an empty dataset.

========================================================
SUBMISSION
========================================================

When the requested records have been extracted and
validated, call:

submit_dataset

The submission should contain:

rows
columns
confidence
notes

========================================================
RESTRICTIONS
========================================================

Never:

- execute arbitrary Python
- execute shell commands
- access arbitrary filesystem paths
- fabricate data
- fabricate URLs
- fabricate records
- submit unrelated data

Only use registered tools.

========================================================
ACTION FORMAT
========================================================

Return exactly ONE JSON action.

{
  "action": "tool_name",
  "arguments": {}
}

Do not return explanations outside JSON.

When complete:

{
  "action": "submit_dataset",
  "arguments": {
    "rows": [],
    "columns": [],
    "confidence": 0.0,
    "notes": ""
  }
}
"""

        user_prompt = f"""
Extract this dataset:

DATASET:
{dataset_json}

AVAILABLE TOOLS:
{tools}

Start with the best acquisition strategy.

Return exactly one JSON action.
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

    # ==========================================================
    # COMPACT JSON
    # ==========================================================

    def _compact_json(
        self,
        value: Any,
    ) -> str:
        """
        Serialize tool/model data compactly.
        """

        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
            default=str,
        )

    # ==========================================================
    # LIMIT TOOL RESULT
    # ==========================================================

    def _compact_tool_result(
        self,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Prevent very large browser/file results from filling the
        model context.

        Important information is preserved where possible.
        """

        serialized = self._compact_json(
            result
        )

        if len(serialized) <= (
            self.MAX_TOOL_RESULT_CHARS
        ):
            return result

        # ------------------------------------------------------
        # Preserve structure but truncate very large fields.
        # ------------------------------------------------------

        compact = dict(
            result
        )

        for key in (
            "text",
            "content",
            "body",
            "html",
            "stdout",
            "stderr",
            "data",
            "rows",
            "records",
        ):

            if key not in compact:
                continue

            value = compact[
                key
            ]

            if isinstance(
                value,
                str,
            ):

                compact[
                    key
                ] = (
                    value[
                        : self.MAX_TOOL_RESULT_CHARS
                    ]
                    + "\n...[TRUNCATED]..."
                )

            elif isinstance(
                value,
                list,
            ):

                # Keep the beginning of long lists.
                compact[
                    key
                ] = value[:100]

                compact[
                    f"{key}_truncated"
                ] = True

        # Final safety truncation.
        serialized = self._compact_json(
            compact
        )

        if len(serialized) > (
            self.MAX_TOOL_RESULT_CHARS
        ):

            return {
                "success": result.get(
                    "success",
                    False,
                ),
                "status": result.get(
                    "status"
                ),
                "message": result.get(
                    "message"
                ),
                "error_type": result.get(
                    "error_type"
                ),
                "summary": (
                    serialized[
                        : self.MAX_TOOL_RESULT_CHARS
                    ]
                    + "\n...[TRUNCATED]..."
                ),
            }

        return compact

    # ==========================================================
    # ACTION PARSER
    # ==========================================================

    def _parse_action(
        self,
        response: str,
    ) -> dict[str, Any]:
        """
        Parse Qwen's JSON action.

        Handles:

        - plain JSON
        - markdown JSON blocks
        - surrounding text
        """

        if not isinstance(
            response,
            str,
        ):

            raise ValueError(
                "Qwen response must be a string."
            )

        response = response.strip()

        response = (
            response
            .replace(
                "&#x20;",
                " ",
            )
            .replace(
                "&quot;",
                '"',
            )
            .replace(
                "&#34;",
                '"',
            )
        )

        response = re.sub(
            r"```json",
            "",
            response,
            flags=re.IGNORECASE,
        )

        response = re.sub(
            r"```",
            "",
            response,
        )

        response = response.strip()

        start = response.find(
            "{"
        )

        end = response.rfind(
            "}"
        )

        if start == -1 or end == -1:

            raise ValueError(
                "Qwen did not return a JSON object."
            )

        json_text = response[
            start : end + 1
        ]

        try:

            action = json.loads(
                json_text
            )

        except json.JSONDecodeError as exc:

            raise ValueError(
                "Qwen returned invalid JSON: "
                + str(exc)
            ) from exc

        if not isinstance(
            action,
            dict,
        ):

            raise ValueError(
                "Qwen action must be a JSON object."
            )

        action_name = action.get(
            "action"
        )

        if not isinstance(
            action_name,
            str,
        ) or not action_name.strip():

            raise ValueError(
                "Qwen action is missing a valid "
                "'action' field."
            )

        arguments = action.get(
            "arguments",
            {},
        )

        if arguments is None:
            arguments = {}

        if not isinstance(
            arguments,
            dict,
        ):

            raise ValueError(
                "Qwen 'arguments' must be a JSON object."
            )

        return {
            "action": action_name.strip(),
            "arguments": arguments,
        }

    # ==========================================================
    # TOOL RESULT MESSAGE
    # ==========================================================

    def _tool_result_message(
        self,
        action: dict[str, Any],
        result: dict[str, Any],
    ) -> str:
        """
        Convert a tool result into a compact model-facing
        message.
        """

        compact_result = (
            self._compact_tool_result(
                result
            )
        )

        return (
            "TOOL EXECUTION RESULT:\n"
            + self._compact_json(
                compact_result
            )
            + "\n\n"
            "Continue the extraction.\n"
            "Return exactly one JSON action."
        )

    # ==========================================================
    # MESSAGE COMPACTION
    # ==========================================================

    def _compact_messages(
        self,
        messages: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """
        Keep the initial instructions plus the most recent
        interactions.

        This is the main context protection mechanism for the T4.
        """

        if len(messages) <= (
            self.MAX_HISTORY_MESSAGES
        ):

            return messages

        first_two = messages[:2]

        recent = messages[
            -(
                self.MAX_HISTORY_MESSAGES
                - 2
            ):
        ]

        return (
            first_two
            + recent
        )

    # ==========================================================
    # INTERNAL LOOP
    # ==========================================================

    def _run(
        self,
        dataset: dict[str, Any],
    ) -> dict[str, Any]:

        messages = self._build_prompt(
            dataset
        )

        history: list[
            dict[str, Any]
        ] = []

        for step in range(
            1,
            self.MAX_STEPS + 1,
        ):

            print(
                "\n"
                + "=" * 70
            )

            print(
                f"AGENT STEP "
                f"{step}/{self.MAX_STEPS}"
            )

            print(
                "=" * 70
            )

            # --------------------------------------------------
            # Keep context bounded before every model call.
            # --------------------------------------------------

            messages = (
                self._compact_messages(
                    messages
                )
            )

            # --------------------------------------------------
            # ASK QWEN
            # --------------------------------------------------

            try:

                response = (
                    self.model.generate(
                        messages,
                        mode="tool_selection",
                    )
                )

            except Exception as exc:

                # ------------------------------------------------
                # Don't allow a model failure to silently become
                # a successful dataset.
                # ------------------------------------------------

                return {
                    "success": False,
                    "status": "failed",
                    "error_type": type(
                        exc
                    ).__name__,
                    "message": str(
                        exc
                    ),
                    "history": history,
                }

            print(
                "\nRAW QWEN RESPONSE:"
            )

            print(
                response
            )

            # --------------------------------------------------
            # PARSE
            # --------------------------------------------------

            try:

                action = self._parse_action(
                    response
                )

            except Exception as exc:

                return {
                    "success": False,
                    "status": "failed",
                    "error_type": (
                        "InvalidModelAction"
                    ),
                    "message": str(
                        exc
                    ),
                    "raw_response": response,
                    "history": history,
                }

            print(
                "\nPARSED ACTION:"
            )

            print(
                json.dumps(
                    action,
                    indent=2,
                    ensure_ascii=False,
                )
            )

            action_name = action[
                "action"
            ]

            arguments = action[
                "arguments"
            ]

            # --------------------------------------------------
            # FINISH
            # --------------------------------------------------

            if action_name == "finish":

                history.append(
                    {
                        "step": step,
                        "action": action,
                        "result": {
                            "success": True,
                            "status": "finished",
                        },
                    }
                )

                return {
                    "success": True,
                    "status": "finished",
                    "dataset": dataset,
                    "history": history,
                }

            # --------------------------------------------------
            # EXECUTE TOOL
            # --------------------------------------------------

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
                    "message": str(
                        exc
                    ),
                    "recoverable": True,
                }

            # --------------------------------------------------
            # Compact the result before storing it.
            # --------------------------------------------------

            result_for_model = (
                self._compact_tool_result(
                    result
                )
            )

            print(
                "\nTOOL RESULT:"
            )

            print(
                json.dumps(
                    result_for_model,
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
            )

            # --------------------------------------------------
            # HISTORY
            # --------------------------------------------------

            history.append(
                {
                    "step": step,
                    "action": action,
                    "result": result_for_model,
                }
            )

            # --------------------------------------------------
            # SUBMISSION
            # --------------------------------------------------

            if (
                action_name
                == "submit_dataset"
            ):

                if result.get(
                    "success",
                    False,
                ):

                    print(
                        "\nDATASET SUBMITTED "
                        "SUCCESSFULLY."
                    )

                    return {
                        "success": True,
                        "status": "submitted",
                        "dataset": dataset,
                        "submission": result,
                        "history": history,
                    }

            # --------------------------------------------------
            # Add model action.
            # --------------------------------------------------

            messages.append(
                {
                    "role": "assistant",
                    "content": self._compact_json(
                        action
                    ),
                }
            )

            # --------------------------------------------------
            # Add compact tool result.
            # --------------------------------------------------

            messages.append(
                {
                    "role": "user",
                    "content": (
                        self._tool_result_message(
                            action,
                            result_for_model,
                        )
                    ),
                }
            )

        return {
            "success": False,
            "status": "max_steps_exceeded",
            "dataset": dataset,
            "history": history,
            "message": (
                f"Agent reached the maximum "
                f"of {self.MAX_STEPS} steps "
                "without completing extraction."
            ),
        }

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def run(
        self,
        dataset: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Run one dataset with an isolated submission context.
        """

        dataset_id = dataset.get(
            "dataset_id"
        )

        if not dataset_id:

            return {
                "success": False,
                "status": "failed",
                "error_type": (
                    "MissingDatasetID"
                ),
                "message": (
                    "Dataset definition does not "
                    "contain dataset_id."
                ),
            }

        set_submission_context(
            dataset_id
        )

        try:

            return self._run(
                dataset
            )

        finally:

            clear_submission_context()
