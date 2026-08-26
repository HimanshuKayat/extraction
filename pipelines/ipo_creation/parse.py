from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd


EXPECTED_COLUMNS = [
    "Remitter Bank",
    "Total Volume",
    "Approved%",
    "BD%",
    "TD%",
]


def clean_column_name(
    value,
) -> str:

    return " ".join(
        str(value)
        .replace("\n", " ")
        .split()
    ).strip()


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
        clean_column_name(column)
        for column in dataframe.columns
    ]

    # Handle duplicated HTML headers if NPCI
    # represents the header twice.
    normalized = {}

    for column in dataframe.columns:

        for expected in EXPECTED_COLUMNS:

            if column == expected:
                normalized[column] = expected
                break

            if column == f"{expected} {expected}":
                normalized[column] = expected
                break

    dataframe = dataframe.rename(
        columns=normalized
    )

    return dataframe


def find_ipo_creation_table(
    html: str,
) -> pd.DataFrame:

    try:
        tables = pd.read_html(
            StringIO(html)
        )

    except ValueError as exc:
        raise RuntimeError(
            "No HTML tables found in NPCI response."
        ) from exc

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
            "IPO Creation table was not found.\n"
            f"Expected columns: "
            f"{EXPECTED_COLUMNS}\n"
            f"Discovered tables: "
            f"{discovered}"
        )

    # Use the largest matching table.
    return max(
        candidates,
        key=len,
    ).reset_index(
        drop=True
    )


def remove_repeated_headers(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:

    dataframe = dataframe.copy()

    mask = (
        dataframe["Remitter Bank"]
        .astype(str)
        .str.strip()
        .str.lower()
        != "remitter bank"
    )

    return dataframe.loc[
        mask
    ].reset_index(drop=True)


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
            "Artifact does not appear to be HTML."
        )

    dataframe = find_ipo_creation_table(
        html
    )

    dataframe = remove_repeated_headers(
        dataframe
    )

    return dataframe
