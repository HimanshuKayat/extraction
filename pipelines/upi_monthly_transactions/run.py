from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from crawl import crawl
from parse import parse
from validate import validate, write_csv


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load_config() -> dict:
    config_path = HERE / "config.yaml"

    with config_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return yaml.safe_load(file)


async def main() -> None:

    config = load_config()

    dataset_id = config[
        "dataset"
    ]["id"]

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
        ROOT
        / "output"
        / dataset_id
    )

    output_path = (
        output_directory
        / f"{dataset_id}.csv"
    )

    print()
    print("=" * 70)
    print("UPI MONTHLY TRANSACTIONS")
    print("=" * 70)

    print()
    print(
        "[1/4] Crawling NPCI with Crawl4AI..."
    )

    result = await crawl(
        raw_path
    )

    print(
        f"      saved: {result['path']}"
    )
    print(
        f"      bytes: {result['bytes']}"
    )

    print()
    print(
        "[2/4] Extracting Monthly UPI table..."
    )

    dataframe = parse(
        raw_path
    )

    print(
        f"      rows extracted: "
        f"{len(dataframe)}"
    )

    print()
    print("[3/4] Validating...")

    dataframe = validate(
        dataframe
    )

    print(
        f"      rows validated: "
        f"{len(dataframe)}"
    )

    print()
    print("[4/4] Writing CSV...")

    write_csv(
        dataframe,
        output_path,
    )

    print(
        f"      output: {output_path}"
    )

    print()
    print("=" * 70)
    print("SUCCESS")
    print("=" * 70)
    print(
        f"Dataset: {dataset_id}"
    )
    print(
        f"Rows: {len(dataframe)}"
    )
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
