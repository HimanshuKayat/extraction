from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd


EXPECTED_COLUMNS = [
    "Day",
    "Volume (In Mn.)",
    "Value (In Cr.)",
]


def clean_text(value: Any) -> str:
    """Normalize whitespace and line breaks."""

    return " ".join(
        str(value)
        .replace("\n", " ")
        .split()
    ).strip()


def normalize_column_name(value: Any) -> str:
    """
    Normalize an HTML table column.

    NPCI currently exposes duplicated/multi-level headers such as:

        Day Day

    or:

        Volume (In Mn.) Volume (In Mn.)

    Reduce those to the actual dataset column name.
    """

    text = clean_text(value)

    # Exact expected columns are always preferred.
    for expected in EXPECTED_COLUMNS:
        if text == expected:
            return expected

    # Handle duplicated headers:
    # "Day Day" -> "Day"
    # "Value (In Cr.) Value (In Cr.)" -> "Value (In Cr.)"
    for expected in EXPECTED_COLUMNS:
        duplicated = f"{expected} {expected}"

        if text == duplicated:
            return expected

    return text


def normalize_table(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Normalize an extracted pandas HTML table."""

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
        normalize_column_name(column)
        for column in dataframe.columns
    ]

    return dataframe


def find_daily_upi_table(
    html: str,
) -> pd.DataFrame:
    """
    Find the Daily UPI transaction table in
    the rendered NPCI HTML.
    """

    try:
        tables = pd.read_html(
            StringIO(html)
        )

    except ValueError as exc:
        raise RuntimeError(
            "No HTML tables were found in the "
            "Crawl4AI output."
        ) from exc

    if not tables:
        raise RuntimeError(
            "NPCI page contains no HTML tables."
        )

    candidates: list[pd.DataFrame] = []

    for table in tables:

        table = normalize_table(table)

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

        discovered = []

        for table in tables:
            normalized = normalize_table(
                table
            )

            discovered.append(
                list(normalized.columns)
            )

        raise RuntimeError(
            "Daily UPI table was not found.\n"
            f"Expected columns: "
            f"{EXPECTED_COLUMNS}\n"
            f"Discovered tables: "
            f"{discovered}"
        )

    # If multiple matching representations
    # exist, use the one containing the most
    # records.
    dataframe = max(
        candidates,
        key=len,
    )

    return dataframe.reset_index(
        drop=True
    )


def remove_repeated_headers(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """Remove repeated header rows from the table."""

    dataframe = dataframe.copy()

    mask = (
        dataframe["Day"]
        .astype(str)
        .str.strip()
        .str.lower()
        != "day"
    )

    return dataframe.loc[
        mask
    ].reset_index(drop=True)


def parse(
    artifact_path: str | Path,
) -> pd.DataFrame:
    """Parse the crawled NPCI Daily UPI page."""

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
            "Crawl artifact does not appear "
            "to be HTML."
        )

    dataframe = find_daily_upi_table(
        html
    )

    dataframe = remove_repeated_headers(
        dataframe
    )

    return dataframe
