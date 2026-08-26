from __future__ import annotations

from pathlib import Path

import pandas as pd


EXPECTED_COLUMNS = [
    "Month",
    "Volume (In Mn.)",
    "Value (In Cr.)",
]


def validate(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:

    if dataframe.empty:
        raise ValueError(
            "Validation failed: zero rows."
        )

    missing = [
        column
        for column in EXPECTED_COLUMNS
        if column not in dataframe.columns
    ]

    if missing:
        raise ValueError(
            f"Missing columns: {missing}"
        )

    result = dataframe[
        EXPECTED_COLUMNS
    ].copy()

    result["Month"] = (
        result["Month"]
        .astype(str)
        .str.strip()
    )

    result[
        "Volume (In Mn.)"
    ] = pd.to_numeric(
        result[
            "Volume (In Mn.)"
        ]
        .astype(str)
        .str.replace(
            ",",
            "",
            regex=False,
        )
        .str.strip(),
        errors="coerce",
    )

    result[
        "Value (In Cr.)"
    ] = pd.to_numeric(
        result[
            "Value (In Cr.)"
        ]
        .astype(str)
        .str.replace(
            ",",
            "",
            regex=False,
        )
        .str.strip(),
        errors="coerce",
    )

    if result["Month"].eq("").any():
        raise ValueError(
            "Empty Month value found."
        )

    if result[
        "Volume (In Mn.)"
    ].isna().any():
        raise ValueError(
            "Invalid Volume values."
        )

    if result[
        "Value (In Cr.)"
    ].isna().any():
        raise ValueError(
            "Invalid Value values."
        )

    if (
        result["Volume (In Mn.)"] < 0
    ).any():
        raise ValueError(
            "Negative Volume found."
        )

    if (
        result["Value (In Cr.)"] < 0
    ).any():
        raise ValueError(
            "Negative Value found."
        )

    if result["Month"].duplicated().any():
        raise ValueError(
            "Duplicate Month values found."
        )

    return result.reset_index(
        drop=True
    )


def write_csv(
    dataframe: pd.DataFrame,
    output_path: str | Path,
) -> None:

    output_path = Path(output_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    dataframe.to_csv(
        output_path,
        index=False,
        encoding="utf-8",
    )
