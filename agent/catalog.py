from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = {
    "sno",
    "data_title",
    "frequency",
    "data_description",
    "data_source",
    "data_link",
    "data_status",
    "Granularity",
}


@dataclass
class DatasetDefinition:
    sno: int
    data_title: str
    frequency: str
    data_description: str
    data_source: str
    data_link: str
    data_required_in_pipe: bool
    data_status: str
    granularity: str
    time_granularity: str
    data_scope: str
    owner: str

    def to_agent_context(self) -> dict[str, Any]:
        return {
            "sno": self.sno,
            "data_title": self.data_title,
            "frequency": self.frequency,
            "data_description": self.data_description,
            "data_source": self.data_source,
            "data_link": self.data_link,
            "data_required_in_pipe": (
                self.data_required_in_pipe
            ),
            "data_status": self.data_status,
            "granularity": self.granularity,
            "time_granularity": (
                self.time_granularity
            ),
            "data_scope": self.data_scope,
            "owner": self.owner,
        }


def _clean(value: Any) -> str:
    if pd.isna(value):
        return ""

    return str(value).strip()


def _to_bool(value: Any) -> bool:
    if pd.isna(value):
        return False

    if isinstance(value, bool):
        return value

    value = str(value).strip().lower()

    return value in {
        "true",
        "1",
        "yes",
        "y",
    }


def load_catalog(
    workbook_path: str | Path,
    sheet_name: str = "Summary Table",
) -> list[DatasetDefinition]:

    workbook_path = Path(
        workbook_path
    )

    if not workbook_path.exists():
        raise FileNotFoundError(
            f"Dataset catalog not found: "
            f"{workbook_path}"
        )

    # The actual workbook has its column headers
    # on Excel row 5, which is pandas header=4.
    dataframe = pd.read_excel(
        workbook_path,
        sheet_name=sheet_name,
        header=4,
    )

    dataframe = dataframe.dropna(
        how="all"
    )

    missing = (
        REQUIRED_COLUMNS
        - set(dataframe.columns)
    )

    if missing:
        raise RuntimeError(
            "Dataset catalog is missing "
            f"required columns: "
            f"{sorted(missing)}"
        )

    datasets: list[
        DatasetDefinition
    ] = []

    for _, row in dataframe.iterrows():

        title = _clean(
            row["data_title"]
        )

        url = _clean(
            row["data_link"]
        )

        if not title or not url:
            continue

        sno_value = row["sno"]

        try:
            sno = int(sno_value)
        except (
            TypeError,
            ValueError,
        ):
            continue

        datasets.append(
            DatasetDefinition(
                sno=sno,
                data_title=title,
                frequency=_clean(
                    row["frequency"]
                ),
                data_description=_clean(
                    row["data_description"]
                ),
                data_source=_clean(
                    row["data_source"]
                ),
                data_link=url,
                data_required_in_pipe=_to_bool(
                    row[
                        "data_required_in_pipe"
                    ]
                ),
                data_status=_clean(
                    row["data_status"]
                ),
                granularity=_clean(
                    row["Granularity"]
                ),
                time_granularity=_clean(
                    row[
                        "Time_granularity"
                    ]
                ),
                data_scope=_clean(
                    row["data_scope"]
                ),
                owner=_clean(
                    row["owner"]
                ),
            )
        )

    return datasets