from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


EXPECTED_COLUMNS = [
    "Day",
    "Volume (In Mn.)",
    "Value (In Cr.)",
]


def clean_column(value: Any) -> str:

    return (
        " ".join(
            str(value)
            .replace("\n", " ")
            .split()
        )
        .strip()
    )


def normalize_table(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:

    dataframe = dataframe.copy()

    if isinstance(
        dataframe.columns,
        pd.MultiIndex,
    ):

        dataframe.columns = [
            " ".join(
                str(part)
                for part in column
                if str(part).lower() != "nan"
            ).strip()
            for column in dataframe.columns
        ]

    dataframe.columns = [
        clean_column(column)
        for column in dataframe.columns
    ]

    return dataframe


def find_daily_upi_table(
    html: str,
) -> pd.DataFrame:

    try:

        tables = pd.read_html(
            html
        )

    except ValueError as exc:

        raise RuntimeError(
            "No HTML tables were found."
        ) from exc

    if not tables:

        raise RuntimeError(
            "NPCI page contains no HTML tables."
        )

    candidates = []

    for table in tables:

        table = normalize_table(
            table
        )

        if all(
            column in table.columns
            for column in EXPECTED_COLUMNS
        ):

            candidates.append(
                table[
                    EXPECTED_COLUMNS
                ].copy()
            )

    if not candidates:

        discovered = [
            list(
                normalize_table(table).columns
            )
            for table in tables
        ]

        raise RuntimeError(
            "Daily UPI table was not found.\n"
            f"Expected columns: {EXPECTED_COLUMNS}\n"
            f"Discovered tables: {discovered}"
        )

    # If multiple matching tables exist,
    # use the one containing the greatest
    # number of records.
    dataframe = max(
        candidates,
        key=len,
    )

    return dataframe.reset_index(
        drop=True
    )


def parse(
    artifact_path: str | Path,
) -> pd.DataFrame:

    path = Path(
        artifact_path
    )

    if not path.exists():

        raise FileNotFoundError(
            f"Artifact not found: {path}"
        )

    html = path.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    if "<html" not in html.lower():

        raise RuntimeError(
            "Artifact does not appear to be HTML."
        )

    dataframe = find_daily_upi_table(
        html
    )

    # Remove accidental repeated header rows.
    dataframe = dataframe[
        dataframe["Day"]
        .astype(str)
        .str.strip()
        .str.lower()
        != "day"
    ]

    return dataframe.reset_index(
        drop=True
    )


def validate(
    dataframe: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:

    if dataframe.empty:

        return {
            "success": False,
            "error": "No rows extracted.",
        }

    missing = [
        column
        for column in EXPECTED_COLUMNS
        if column not in dataframe.columns
    ]

    if missing:

        return {
            "success": False,
            "error": (
                "Missing required columns: "
                f"{missing}"
            ),
        }

    dataframe = dataframe[
        EXPECTED_COLUMNS
    ].copy()

    dataframe["Day"] = pd.to_datetime(
        dataframe["Day"],
        errors="coerce",
    )

    dataframe[
        "Volume (In Mn.)"
    ] = pd.to_numeric(
        dataframe[
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

    dataframe[
        "Value (In Cr.)"
    ] = pd.to_numeric(
        dataframe[
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

    if dataframe["Day"].isna().any():

        return {
            "success": False,
            "error": "Invalid Day values found.",
        }

    if dataframe[
        "Volume (In Mn.)"
    ].isna().any():

        return {
            "success": False,
            "error": (
                "Invalid Volume "
                "values found."
            ),
        }

    if dataframe[
        "Value (In Cr.)"
    ].isna().any():

        return {
            "success": False,
            "error": (
                "Invalid Value "
                "values found."
            ),
        }

    if (
        dataframe[
            "Volume (In Mn.)"
        ] < 0
    ).any():

        return {
            "success": False,
            "error": (
                "Negative transaction "
                "volume found."
            ),
        }

    if (
        dataframe[
            "Value (In Cr.)"
        ] < 0
    ).any():

        return {
            "success": False,
            "error": (
                "Negative transaction "
                "value found."
            ),
        }

    if dataframe[
        "Day"
    ].duplicated().any():

        return {
            "success": False,
            "error": (
                "Duplicate Day values found."
            ),
        }

    return {
        "success": True,
        "rows": len(dataframe),
        "columns": list(
            dataframe.columns
        ),
        "date_min": str(
            dataframe["Day"].min().date()
        ),
        "date_max": str(
            dataframe["Day"].max().date()
        ),
    }
