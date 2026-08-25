from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(
    __file__
).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT),
)

from monitoring.staleness_check import (
    check_all,
)


if __name__ == "__main__":

    results = check_all()

    print(
        json.dumps(
            results,
            indent=2,
            default=str,
        )
    )

    stale = [
        item
        for item in results
        if item.get("stale")
    ]

    if stale:

        print(
            f"\nSTALE DATASETS: {len(stale)}"
        )

        for item in stale:
            print(
                "-",
                item["dataset_id"],
            )