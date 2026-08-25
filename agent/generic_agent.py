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

    The agent receives ONE dataset definition from the
    master catalog and autonomously decides how to:

        1. Find the requested dataset.
        2. Navigate the source website.
        3. Download the underlying artifact.
        4. Inspect the artifact.
        5. Extract the requested data.
        6. Validate the extracted data.
        7. Submit the final structured dataset.

    The agent can only use tools explicitly registered
    in the controlled ToolRegistry.

    No dataset-specific run.py or parse.py is required.
    """

    MAX_STEPS = 20

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
        """

        tools = json.dumps(
            self.registry.to_prompt_list(),
            indent=2,
            ensure_ascii=False,
        )

        dataset_json = json.dumps(
            dataset,
            indent=2,
            ensure_ascii=False,
        )

        system_prompt = """
You are an autonomous data extraction agent.

Your task is to extract ONE specific dataset from
an official or authoritative source.

You have access ONLY to the registered tools provided
in the prompt.

You must autonomously determine how to obtain and
extract the requested dataset.

========================================================
CORE OBJECTIVE
========================================================

Extract the actual requested dataset.

Do NOT merely find the webpage.

Do NOT merely download a file.

Do NOT return a description of the dataset.

The final result must contain actual structured data.

========================================================
SOURCE NAVIGATION
========================================================

Start from the supplied data_link.

The URL may be:

- a direct file
- a webpage
- a dynamic website
- a page containing links to files
- a page containing multiple datasets
- a JavaScript application

Determine which situation applies.

Use:

browser_open
browser_inspect

when website navigation is required.

Use:

http_download

when a direct downloadable artifact is available.

========================================================
DOWNLOAD STRATEGY
========================================================

Prefer direct downloads when possible.

If direct HTTP downloading fails:

1. Use browser_open.
2. Inspect the page.
3. Identify the actual data resource.
4. Follow the appropriate link.
5. Download the underlying resource.

Do not repeatedly retry a failed HTTP request
without changing strategy.

========================================================
FILE INSPECTION
========================================================

After obtaining a file, ALWAYS inspect it before
deciding how to extract it.

Use:

inspect_file

Then choose the appropriate extraction tool.

PDF:
    read_pdf
    extract_pdf_table

CSV:
    read_csv

Excel:
    read_excel

Do not assume the file type from its filename alone.

========================================================
DATASET SELECTION
========================================================

The source may contain multiple datasets.

Use the supplied:

data_title
data_description
data_scope
granularity
time_granularity

to determine which data belongs to the requested
dataset.

Do not extract unrelated datasets simply because
they appear on the same page or file.

========================================================
EXTRACTION
========================================================

Extract the actual records.

Preserve the source values.

Do not invent missing values.

Do not fabricate columns.

Do not silently replace source values with guesses.

If a value is genuinely unavailable, preserve it
as empty/null where appropriate.

========================================================
VALIDATION
========================================================

Before submission:

1. Check that records were actually extracted.
2. Check required fields where identifiable.
3. Check that the row structure is consistent.
4. Check for obvious extraction corruption.
5. Use the validation tools when appropriate.

Do not submit an empty dataset.

Do not submit a dataset merely because a webpage
returned HTTP 200.

========================================================
SUBMISSION
========================================================

When extraction is complete, use:

submit_dataset

The rows must contain actual extracted records.

The final submission should contain:

rows
columns
confidence
notes

Use confidence to indicate how confident you are
that the extracted records correspond to the requested
dataset.

========================================================
IMPORTANT RESTRICTIONS
========================================================

Never:

- execute arbitrary Python
- execute shell commands
- access arbitrary filesystem paths
- invent data
- fabricate URLs
- fabricate records
- submit unrelated data
- stop after discovering only a webpage
- stop after downloading a file without extracting it

Only use registered tools.

========================================================
ACTION FORMAT
========================================================

Return exactly ONE JSON action at a time.

Format:

{
  "action": "tool_name",
  "arguments": {}
}

Do not return explanations outside the JSON action.

When the dataset is successfully extracted:

{
  "action": "submit_dataset",
  "arguments": {
    "rows": [...],
    "columns": [...],
    "confidence": 0.0,
    "notes": "..."
  }
}
"""

        user_prompt = f"""
Extract the following dataset.

DATASET DEFINITION:

{dataset_json}

AVAILABLE TOOLS:

{tools}

Begin by determining the best acquisition strategy.

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
    # ACTION PARSER
    # ==========================================================

    def _parse_action(
        self,
        response: str,
    ) -> dict[str, Any]:
        """
        Parse Qwen's JSON action.

        Handles:
            plain JSON
            ```json blocks
            surrounding text
        """

        if not isinstance(
            response,
            str,
        ):
            raise ValueError(
                "Qwen response must be a string."
            )

        response = response.strip()

        # ------------------------------------------------------
        # Remove HTML escaping occasionally produced by
        # notebook/display environments.
        # ------------------------------------------------------

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

        # ------------------------------------------------------
        # Remove markdown fences.
        # ------------------------------------------------------

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

        # ------------------------------------------------------
        # Locate JSON object.
        # ------------------------------------------------------

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

        # ------------------------------------------------------
        # Required action field.
        # ------------------------------------------------------

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

        action[
            "action"
        ] = action_name.strip()

        # ------------------------------------------------------
        # Arguments.
        # ------------------------------------------------------

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

        action[
            "arguments"
        ] = arguments

        return action

    # ==========================================================
    # TOOL RESULT → MODEL MESSAGE
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

        return (
            "TOOL EXECUTION RESULT:\n"
            + json.dumps(
                result,
                ensure_ascii=False,
                default=str,
            )
            + "\n\n"
            "Continue the extraction.\n"
            "Return exactly one JSON action."
        )

    # ==========================================================
    # INTERNAL AGENT LOOP
    # ==========================================================

    def _run(
        self,
        dataset: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute the autonomous extraction loop.
        """

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
            # ASK QWEN
            # --------------------------------------------------

            response = self.model.generate(
                messages,
                mode="tool_selection",
            )

            print(
                "\nRAW QWEN RESPONSE:"
            )

            print(
                response
            )

            # --------------------------------------------------
            # PARSE ACTION
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
                    "error_type": (
                        type(exc).__name__
                    ),
                    "message": str(
                        exc
                    ),
                    "recoverable": True,
                }

            print(
                "\nTOOL RESULT:"
            )

            print(
                json.dumps(
                    result,
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
            )

            # --------------------------------------------------
            # RECORD HISTORY
            # --------------------------------------------------

            history.append(
                {
                    "step": step,
                    "action": action,
                    "result": result,
                }
            )

            # --------------------------------------------------
            # FINAL DATASET SUBMISSION
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

                # Submission failed.
                # Give the failure back to Qwen so it
                # can attempt recovery.

            # --------------------------------------------------
            # ADD MODEL ACTION TO HISTORY
            # --------------------------------------------------

            messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(
                        action,
                        ensure_ascii=False,
                    ),
                }
            )

            # --------------------------------------------------
            # ADD TOOL RESULT
            # --------------------------------------------------

            messages.append(
                {
                    "role": "user",
                    "content": (
                        self._tool_result_message(
                            action,
                            result,
                        )
                    ),
                }
            )

        # ------------------------------------------------------
        # MAXIMUM STEPS
        # ------------------------------------------------------

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
    # PUBLIC RUN METHOD
    # ==========================================================

    def run(
        self,
        dataset: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Run one dataset extraction with an isolated
        submission context.

        The submission tool does not receive the dataset
        ID from Qwen. Instead, the runner establishes it
        here so Qwen cannot write into another dataset's
        output directory.
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