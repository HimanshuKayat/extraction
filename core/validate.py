from __future__ import annotations

from typing import Any

import pandas as pd


def validate_required_fields(
    dataframe: pd.DataFrame,
    fields: list[str],
) -> dict[str, Any]:

    missing = [
        field
        for field in fields
        if field not in dataframe.columns
    ]

    return {
        "success": not missing,
        "missing_fields": missing,
    }


def validate_row_count(
    dataframe: pd.DataFrame,
    minimum: int = 1,
    maximum: int | None = None,
) -> dict[str, Any]:

    count = len(dataframe)

    valid = count >= minimum

    if maximum is not None:
        valid = valid and count <= maximum

    return {
        "success": valid,
        "row_count": count,
        "minimum": minimum,
        "maximum": maximum,
    }


def validate_fill_rate(
    dataframe: pd.DataFrame,
    fields: list[str],
    minimum_rate: float = 0.95,
) -> dict[str, Any]:

    results = {}

    overall_valid = True

    for field in fields:

        if field not in dataframe.columns:

            results[field] = 0.0
            overall_valid = False
            continue

        rate = (
            dataframe[field]
            .notna()
            .mean()
        )

        results[field] = float(rate)

        if rate < minimum_rate:
            overall_valid = False

    return {
        "success": overall_valid,
        "fill_rates": results,
        "minimum_rate": minimum_rate,
    }