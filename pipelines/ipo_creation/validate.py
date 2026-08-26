from __future__ import annotations

from pathlib import Path

import pandas as pd


EXPECTED_COLUMNS = [
    "Remitter Bank",
    "Total Volume",
    "Approved%",
    "BD%",
    "TD%",
]


def validate(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:

    if dataframe.empty:
        raise ValueError(
            "Validation failed: zero IPO Creation rows."
        )

    missing = [
        column
        for column in EXPECTED_COLUMNS
        if column not in dataframe.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    result = dataframe[
        EXPECTED_COLUMNS
    ].copy()

    # --------------------------------------------------
    # Remitter Bank
    # --------------------------------------------------

    result["Remitter Bank"] = (
        result["Remitter Bank"]
        .astype(str)
        .str.strip()
    )

    if result[
        "Remitter Bank"
    ].eq("").any():
        raise ValueError(
            "Empty Remitter Bank value found."
        )

    # --------------------------------------------------
    # Total Volume
    # --------------------------------------------------

    result["Total Volume"] = pd.to_numeric(
        result["Total Volume"]
        .astype(str)
        .str.replace(
            ",",
            "",
            regex=False,
        )
        .str.strip(),
        errors="coerce",
    )

    if result[
        "Total Volume"
    ].isna().any():
        raise ValueError(
            "Invalid Total Volume values found."
        )

    result["Total Volume"] = (
        result["Total Volume"]
        .astype("int64")
    )

    if (
        result["Total Volume"] < 0
    ).any():
        raise ValueError(
            "Negative Total Volume found."
        )

    # --------------------------------------------------
    # Rates
    # --------------------------------------------------

    for column in [
        "Approved%",
        "BD%",
        "TD%",
    ]:

        result[column] = pd.to_numeric(
            result[column]
            .astype(str)
            .str.replace(
                "%",
                "",
                regex=False,
            )
            .str.strip(),
            errors="coerce",
        )

        if result[column].isna().any():
            raise ValueError(
                f"Invalid {column} values found."
            )

        if (
            result[column] < 0
        ).any():
            raise ValueError(
                f"Negative {column} found."
            )

        # The dictionary samples use proportions:
        # 0.9462 rather than 94.62.
        if (
            result[column] > 1
        ).any():

            # If NPCI provides literal percentage
            # values such as 94.62, normalize them.
            if (
                result[column] <= 100
            ).all():

                result[column] = (
                    result[column] / 100
                )

            else:
                raise ValueError(
                    f"Invalid {column}: "
                    "values exceed 100%."
                )

    # --------------------------------------------------
    # Business consistency
    # --------------------------------------------------

    rate_sum = (
        result["Approved%"]
        + result["BD%"]
        + result["TD%"]
    )

    if (
        (rate_sum < 0.98)
        | (rate_sum > 1.02)
    ).any():

        raise ValueError(
            "Approval + BD + TD rates "
            "do not approximately sum to 100%."
        )

    # --------------------------------------------------
    # Duplicate banks
    # --------------------------------------------------

    if result[
        "Remitter Bank"
    ].duplicated().any():

        duplicates = result.loc[
            result[
                "Remitter Bank"
            ].duplicated(),
            "Remitter Bank",
        ].tolist()

        raise ValueError(
            "Duplicate Remitter Bank values: "
            f"{duplicates}"
        )

    return result.reset_index(
        drop=True
    )


def write_csv(
    dataframe: pd.DataFrame,
    output_path: str | Path,
) -> None:

    output_path = Path(
        output_path
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    dataframe.to_csv(
        output_path,
        index=False,
        encoding="utf-8",
    )
