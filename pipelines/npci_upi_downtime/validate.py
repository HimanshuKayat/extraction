from __future__ import annotations

import pandas as pd


def validate_discovery(
    tables: list[pd.DataFrame],
) -> list[pd.DataFrame]:

    if not tables:
        raise ValueError(
            "No tables discovered."
        )

    valid_tables = [
        table.reset_index(drop=True)
        for table in tables
        if not table.empty
    ]

    if not valid_tables:
        raise ValueError(
            "All discovered tables are empty."
        )

    return valid_tables
