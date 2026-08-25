from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def get_output_path(
    dataset_id: str,
) -> Path:

    directory = (
        ROOT
        / "processed"
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


def write_csv(
    data: Any,
    dataset_id: str,
) -> dict:

    output_path = get_output_path(
        dataset_id
    )

    if isinstance(
        data,
        pd.DataFrame,
    ):

        dataframe = data

    elif isinstance(
        data,
        list,
    ):

        dataframe = pd.DataFrame(
            data
        )

    elif isinstance(
        data,
        dict,
    ):

        dataframe = pd.DataFrame(
            [data]
        )

    else:

        raise TypeError(
            "CSV conversion requires "
            "a DataFrame, list, or dict."
        )

    dataframe.to_csv(
        output_path,
        index=False,
        encoding="utf-8",
    )

    return {
        "success": True,
        "path": str(
            output_path
        ),
        "rows": len(
            dataframe
        ),
        "columns": list(
            dataframe.columns
        ),
    }