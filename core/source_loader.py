from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

DATA_SOURCE_FILE = ROOT / "Data_source.xlsx"
SHEET_NAME = "Summary Table"


def _clean(value: Any) -> str | None:
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    value = str(value).strip()

    return value if value else None


def _slugify(value: str) -> str:
    value = value.lower().strip()

    value = re.sub(
        r"[^a-z0-9]+",
        "_",
        value,
    )

    value = re.sub(
        r"_+",
        "_",
        value,
    )

    return value.strip("_")


def _find_header_row(
    workbook: Path,
    sheet_name: str,
) -> int:

    preview = pd.read_excel(
        workbook,
        sheet_name=sheet_name,
        header=None,
        nrows=20,
    )

    required = {
        "data_title",
        "data_description",
        "data_link",
    }

    for index, row in preview.iterrows():

        values = {
            str(value).strip()
            for value in row.tolist()
            if not pd.isna(value)
        }

        if required.issubset(values):
            return int(index)

    raise RuntimeError(
        "Could not locate the dataset header row "
        f"in sheet '{sheet_name}'."
    )


def load_sources() -> list[dict[str, Any]]:
    """
    Load every dataset definition from Data_source.xlsx.

    The Excel workbook is the single source of truth
    for dataset definitions.
    """

    if not DATA_SOURCE_FILE.exists():
        raise FileNotFoundError(
            f"Data source workbook not found: "
            f"{DATA_SOURCE_FILE}"
        )

    header_row = _find_header_row(
        DATA_SOURCE_FILE,
        SHEET_NAME,
    )

    dataframe = pd.read_excel(
        DATA_SOURCE_FILE,
        sheet_name=SHEET_NAME,
        header=header_row,
    )

    dataframe = dataframe.dropna(
        axis=1,
        how="all",
    )

    if "data_title" not in dataframe.columns:
        raise RuntimeError(
            "Data_source.xlsx does not contain "
            "'data_title'."
        )

    dataframe = dataframe[
        dataframe["data_title"].notna()
    ].copy()

    sources: list[dict[str, Any]] = []

    for _, row in dataframe.iterrows():

        title = _clean(
            row.get("data_title")
        )

        if not title:
            continue

        sources.append(
            {
                "dataset_id": _slugify(title),

                "title": title,

                "frequency": _clean(
                    row.get("frequency")
                ),

                "description": _clean(
                    row.get("data_description")
                ),

                "time_granularity": _clean(
                    row.get("Time_granularity")
                ),

                "data_source": _clean(
                    row.get("data_source")
                ),

                "data_link": _clean(
                    row.get("data_link")
                ),

                "required_in_pipeline": _clean(
                    row.get(
                        "data_required_in_pipe"
                    )
                ),

                "status": _clean(
                    row.get("data_status")
                ),

                "granularity": _clean(
                    row.get("Granularity")
                ),

                "remark": _clean(
                    row.get("remark")
                ),
            }
        )

    return sources


def get_source(
    dataset_id: str,
) -> dict[str, Any]:

    for source in load_sources():

        if source["dataset_id"] == dataset_id:
            return source

    raise KeyError(
        f"Dataset '{dataset_id}' "
        "was not found in Data_source.xlsx."
    )