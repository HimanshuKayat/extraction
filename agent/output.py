from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(
    __file__
).resolve().parents[1]

PROCESSED_DIR = (
    ROOT / "processed"
)


def dataset_output_path(
    dataset_id: str,
) -> Path:

    directory = (
        PROCESSED_DIR
        / dataset_id
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    return (
        directory
        / f"{dataset_id}.csv"
    )


def write_dataset_csv(
    dataset_id: str,
    rows: list[dict[str, Any]],
    columns: list[str] | None = None,
) -> dict[str, Any]:

    if not isinstance(
        rows,
        list,
    ):
        raise TypeError(
            "rows must be a list."
        )

    if not rows:
        raise ValueError(
            "Cannot write an empty dataset."
        )

    dataframe = pd.DataFrame(
        rows
    )

    if columns:

        ordered = [
            column
            for column in columns
            if column in dataframe.columns
        ]

        remaining = [
            column
            for column in dataframe.columns
            if column not in ordered
        ]

        dataframe = dataframe[
            ordered + remaining
        ]

    output_path = (
        dataset_output_path(
            dataset_id
        )
    )

    dataframe.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
    )

    return {
        "success": True,
        "path": str(
            output_path.resolve()
        ),
        "rows": len(
            dataframe
        ),
        "columns": list(
            dataframe.columns
        ),
    }