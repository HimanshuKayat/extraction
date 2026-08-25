from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(
    path: str | Path,
) -> str:

    file_path = Path(
        path
    )

    digest = hashlib.sha256()

    with file_path.open(
        "rb"
    ) as handle:

        while True:

            chunk = handle.read(
                1024 * 1024
            )

            if not chunk:
                break

            digest.update(
                chunk
            )

    return digest.hexdigest()


def fingerprint_dataset(
    dataset: dict[str, Any],
) -> str:
    """
    Create a deterministic fingerprint of the catalog
    definition relevant to extraction.

    This does NOT mean the source contents are unchanged.
    It identifies whether the dataset definition itself
    changed.
    """

    relevant = {
        "data_title": dataset.get(
            "data_title",
            "",
        ),
        "data_description": dataset.get(
            "data_description",
            "",
        ),
        "data_source": dataset.get(
            "data_source",
            "",
        ),
        "data_link": dataset.get(
            "data_link",
            "",
        ),
        "granularity": dataset.get(
            "granularity",
            "",
        ),
        "time_granularity": dataset.get(
            "time_granularity",
            "",
        ),
    }

    payload = json.dumps(
        relevant,
        sort_keys=True,
        ensure_ascii=False,
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        payload
    ).hexdigest()