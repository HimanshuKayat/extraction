from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd


def normalize_columns(
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
        " ".join(
            str(column)
            .replace("\n", " ")
            .split()
        ).strip()
        for column in dataframe.columns
    ]

    return dataframe


def inspect_tables(
    html: str,
) -> list[pd.DataFrame]:

    try:
        tables = pd.read_html(
            StringIO(html)
        )
    except ValueError:
        return []

    return [
        normalize_columns(table)
        for table in tables
    ]


def parse(
    artifact_path: str | Path,
) -> list[pd.DataFrame]:

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

    tables = inspect_tables(html)

    if not tables:
        raise RuntimeError(
            "No HTML tables were found."
        )

    return tables
