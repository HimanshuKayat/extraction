from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd


EXPECTED_COLUMNS = [
    "Month",
    "Volume (In Mn.)",
    "Value (In Cr.)",
]


def clean_column(value) -> str:
    return " ".join(
        str(value)
        .replace("\n", " ")
        .split()
    ).strip()


def normalize_column(value) -> str:
    text = clean_column(value)

    for expected in EXPECTED_COLUMNS:
        if text == expected:
            return expected

        if text == f"{expected} {expected}":
            return expected

    return text


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
        normalize_column(column)
        for column in dataframe.columns
    ]

    return dataframe


def find_monthly_table(
    html: str,
) -> pd.DataFrame:

    tables = pd.read_html(
        StringIO(html)
    )

    if not tables:
        raise RuntimeError(
            "No HTML tables found."
        )

    candidates = []

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
            table = normalize_table(table)
            discovered.append(
                list(table.columns)
            )

        raise RuntimeError(
            "Monthly UPI table was not found.\n"
            f"Expected: {EXPECTED_COLUMNS}\n"
            f"Discovered: {discovered}"
        )

    return max(
        candidates,
        key=len,
    ).reset_index(drop=True)


def parse(
    artifact_path: str | Path,
) -> pd.DataFrame:

    path = Path(artifact_path)

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
            "Artifact is not HTML."
        )

    dataframe = find_monthly_table(
        html
    )

    dataframe = dataframe[
        dataframe["Month"]
        .astype(str)
        .str.strip()
        .str.lower()
        != "month"
    ]

    return dataframe.reset_index(
        drop=True
    )
