from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from crawl import crawl
from parse import parse
from validate import validate, write_csv


HERE = Path(
    __file__
).resolve().parent


def load_config() -> dict:

    path = (
        HERE
        / "config.yaml"
    )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:

        return yaml.safe_load(
            file
        )


async def main() -> None:

    config = load_config()

    dataset_id = config[
        "dataset"
    ]["id"]

    ROOT = HERE.parents[1]

raw_directory = (
    ROOT
    / config[
        "artifact"
    ]["directory"]
)

    raw_path = (
        raw_directory
        / config[
            "artifact"
        ]["filename"]
    )

    output_directory = (
        HERE
        / "output"
    )

    output_path = (
        output_directory
        / config[
            "dataset"
        ]["id"]
        / (
            dataset_id
            + ".csv"
        )
    )

    print()
    print(
        "=" * 70
    )
    print(
        "DAILY UPI TRANSACTIONS"
    )
    print(
        "=" * 70
    )

    print()
    print(
        "[1/4] Crawling NPCI with Crawl4AI..."
    )

    crawl_result = await crawl(
        raw_path
    )

    print(
        f"      saved: "
        f"{crawl_result['path']}"
    )

    print(
        f"      bytes: "
        f"{crawl_result['bytes']}"
    )

    print()
    print(
        "[2/4] Extracting Daily UPI table..."
    )

    dataframe = parse(
        raw_path
    )

    print(
        f"      rows extracted: "
        f"{len(dataframe)}"
    )

    print()
    print(
        "[3/4] Validating..."
    )

    dataframe = validate(
        dataframe
    )

    print(
        f"      rows validated: "
        f"{len(dataframe)}"
    )

    print(
        f"      first date: "
        f"{dataframe['Day'].min().date()}"
    )

    print(
        f"      last date: "
        f"{dataframe['Day'].max().date()}"
    )

    print()
    print(
        "[4/4] Writing CSV..."
    )

    write_csv(
        dataframe,
        output_path,
    )

    print(
        f"      output: "
        f"{output_path}"
    )

    print()
    print(
        "=" * 70
    )

    print(
        "SUCCESS"
    )

    print(
        f"Dataset: {dataset_id}"
    )

    print(
        f"Rows: {len(dataframe)}"
    )

    print(
        "=" * 70
    )


if __name__ == "__main__":

    asyncio.run(
        main()
    )
