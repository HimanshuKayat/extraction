from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd


def _clean_text(
    value: str,
) -> str:

    return " ".join(
        str(value).split()
    ).strip()


def parse(
    artifact_path: str | Path,
) -> pd.DataFrame:

    path = Path(
        artifact_path
    )

    html = path.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    tables = pd.read_html(
        html
    )

    if not tables:

        return pd.DataFrame()

    frames = []

    for table in tables:

        table = table.copy()

        table.columns = [
            _clean_text(column)
            for column in table.columns
        ]

        frames.append(
            table
        )

    # Combine discovered tables.
    #
    # Dataset-specific normalization will select
    # the relevant UPI statistics table.

    return pd.concat(
        frames,
        ignore_index=True,
    )


def validate(
    dataframe: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:

    if dataframe.empty:

        return {
            "success": False,
            "error": "No UPI table extracted.",
        }

    return {
        "success": True,
        "rows": len(dataframe),
        "columns": list(
            dataframe.columns
        ),
    }