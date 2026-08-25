from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
    ),
)

from registry.build_registry_view import (
    discover_datasets,
)
from core.runner import run_dataset


def run_all() -> list[dict]:

    datasets = discover_datasets()

    results = []

    for dataset_id in datasets:

        print(
            f"\n{'=' * 70}"
        )

        print(
            f"RUNNING: {dataset_id}"
        )

        print(
            f"{'=' * 70}"
        )

        result = run_dataset(
            dataset_id
        )

        results.append(
            result
        )

    return results


if __name__ == "__main__":

    results = run_all()

    print(
        "\n"
        + "=" * 70
    )

    print(
        "ALL DATASETS COMPLETE"
    )

    print(
        "=" * 70
    )

    print(
        json.dumps(
            results,
            indent=2,
            default=str,
        )
    )