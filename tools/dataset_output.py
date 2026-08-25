from __future__ import annotations

from typing import Any

from agent.output import (
    write_dataset_csv,
)


def submit_dataset(
    rows: list[dict[str, Any]],
    columns: list[str] | None = None,
    confidence: float | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """
    Temporary agent-facing dataset submission.

    The generic runner supplies the current dataset ID
    through the submission context.

    The actual dataset context is injected using
    set_submission_context().
    """

    if not rows:
        return {
            "success": False,
            "error_type": "EmptyDataset",
            "message": (
                "The agent attempted to submit "
                "an empty dataset."
            ),
            "recoverable": True,
        }

    if not isinstance(
        rows,
        list,
    ):

        return {
            "success": False,
            "error_type": "InvalidRows",
            "message": (
                "rows must be a list of objects."
            ),
            "recoverable": True,
        }

    for index, row in enumerate(
        rows
    ):

        if not isinstance(
            row,
            dict,
        ):

            return {
                "success": False,
                "error_type": "InvalidRow",
                "message": (
                    f"Row {index} is not "
                    "a JSON object."
                ),
                "recoverable": True,
            }

    dataset_id = (
        _submission_context.get(
            "dataset_id"
        )
    )

    if not dataset_id:

        return {
            "success": False,
            "error_type": "MissingDatasetContext",
            "message": (
                "No dataset context is active."
            ),
            "recoverable": False,
        }

    try:

        output = write_dataset_csv(
            dataset_id=dataset_id,
            rows=rows,
            columns=columns,
        )

    except Exception as exc:

        return {
            "success": False,
            "error_type": type(
                exc
            ).__name__,
            "message": str(
                exc
            ),
            "recoverable": True,
        }

    return {
        "success": True,
        "dataset_id": dataset_id,
        "rows": output[
            "rows"
        ],
        "columns": output[
            "columns"
        ],
        "path": output[
            "path"
        ],
        "confidence": confidence,
        "notes": notes,
    }


_submission_context: dict[
    str,
    Any,
] = {}


def set_submission_context(
    dataset_id: str,
) -> None:

    _submission_context.clear()

    _submission_context[
        "dataset_id"
    ] = dataset_id


def clear_submission_context() -> None:

    _submission_context.clear()