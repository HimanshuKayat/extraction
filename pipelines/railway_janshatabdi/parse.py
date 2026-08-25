from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from core.parse import read_pdf


TRAIN_PATTERN = re.compile(
    r"(?P<number>\d{4,6})\s+"
    r"(?P<schedule>Daily|Except\s+[^0-9]+?|"
    r"M,W,F|Tu,W|Tu,\s*W)"
    r"\s+"
    r"(?P<origin>.+?)"
    r"\s+[–-]\s+"
    r"(?P<destination>.+?)"
    r"(?=\s+\d{1,3}[A-Z]?\b|\s*$)"
)


def clean_text(value: str) -> str:

    value = " ".join(
        str(value).split()
    )

    return value.strip()


def split_train_records(
    text: str,
) -> list[str]:

    """
    PDF extraction frequently merges two adjacent
    train columns into one line.

    Split whenever a new 4-6 digit train number
    appears.
    """

    text = clean_text(text)

    matches = list(
        re.finditer(
            r"\b\d{4,6}\b",
            text,
        )
    )

    if not matches:
        return []

    records = []

    for index, match in enumerate(matches):

        start = match.start()

        if index + 1 < len(matches):

            end = matches[
                index + 1
            ].start()

        else:

            end = len(text)

        record = text[
            start:end
        ].strip()

        if record:
            records.append(record)

    return records


def parse_train_record(
    record: str,
    page_number: int,
) -> dict[str, Any] | None:

    record = clean_text(
        record
    )

    match = TRAIN_PATTERN.search(
        record
    )

    if not match:
        return None

    number = match.group(
        "number"
    )

    schedule = clean_text(
        match.group(
            "schedule"
        )
    )

    origin = clean_text(
        match.group(
            "origin"
        )
    )

    destination = clean_text(
        match.group(
            "destination"
        )
    )

    return {
        "train_number": number,
        "schedule": schedule,
        "origin": origin,
        "destination": destination,
        "source_page": page_number,
        "raw_text": record,
    }


def parse(
    pdf_path: str | Path,
) -> pd.DataFrame:

    result = read_pdf(
        pdf_path
    )

    rows: list[
        dict[str, Any]
    ] = []

    for page in result["pages"]:

        page_number = page[
            "page"
        ]

        text = page[
            "text"
        ]

        records = split_train_records(
            text
        )

        for record in records:

            parsed = parse_train_record(
                record,
                page_number,
            )

            if parsed is not None:
                rows.append(
                    parsed
                )

    return pd.DataFrame(
        rows,
        columns=[
            "train_number",
            "schedule",
            "origin",
            "destination",
            "source_page",
            "raw_text",
        ],
    )


def validate(
    dataframe: pd.DataFrame,
    config: dict[str, Any],
) -> dict[str, Any]:

    if dataframe.empty:

        return {
            "success": False,
            "error": (
                "No train records extracted."
            ),
        }

    required = config[
        "validation"
    ].get(
        "required_fields",
        [],
    )

    missing = [
        field
        for field in required
        if field not in dataframe.columns
    ]

    if missing:

        return {
            "success": False,
            "error": (
                "Missing required fields: "
                + str(missing)
            ),
        }

    empty_fields = {}

    for field in required:

        empty_count = int(
            dataframe[field]
            .isna()
            .sum()
        )

        empty_fields[field] = (
            empty_count
        )

    invalid = {
        field: count
        for field, count
        in empty_fields.items()
        if count > 0
    }

    if invalid:

        return {
            "success": False,
            "error": (
                "Required fields contain "
                f"empty values: {invalid}"
            ),
        }

    return {
        "success": True,
        "rows": len(
            dataframe
        ),
        "columns": list(
            dataframe.columns
        ),
    }