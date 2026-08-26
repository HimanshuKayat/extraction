from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from crawl import crawl
from parse import parse
from validate import validate_discovery


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load_config() -> dict:
    path = HERE / "config.yaml"

    with path.open(
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

    print()
    print("=" * 70)
    print("NPCI UPTIME FOR UPI")
    print("=" * 70)

    print()
    print(
        "[1/3] Crawling NPCI with Crawl4AI..."
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
        "[2/3] Inspecting Uptime data..."
    )

    tables = parse(
        raw_path
    )

    print(
        f"      tables found: {len(tables)}"
    )

    print()

    for index, table in enumerate(
        tables
    ):

        print("=" * 70)
        print(
            f"TABLE {index}"
        )
        print("=" * 70)

        print(
            "Columns:"
        )

        print(
            table.columns.tolist()
        )

        print()

        print(
            "Rows:",
            len(table)
        )

        print()

        print(
            table.head(10).to_string(
                index=False
            )
        )

        print()

    print()
    print(
        "[3/3] Basic validation..."
    )

    valid_tables = validate_discovery(
        tables
    )

    print(
        f"      non-empty tables: "
        f"{len(valid_tables)}"
    )

    print()
    print("=" * 70)
    print("DISCOVERY SUCCESS")
    print("=" * 70)
    print(
        f"Dataset: {dataset_id}"
    )
    print(
        "Schema discovery complete."
    )
    print(
        "Next step: lock the actual "
        "Uptime schema and implement "
        "deterministic extraction."
    )
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
