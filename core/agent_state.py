from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

STATE_DIR = ROOT / "state" / "agent"

STATE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def _state_path(
    dataset_id: str,
) -> Path:

    return (
        STATE_DIR
        / f"{dataset_id}.json"
    )


def load_agent_state(
    dataset_id: str,
) -> dict[str, Any] | None:

    path = _state_path(
        dataset_id
    )

    if not path.exists():
        return None

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:

        return json.load(handle)


def save_agent_state(
    dataset_id: str,
    state: dict[str, Any],
) -> None:

    path = _state_path(
        dataset_id
    )

    temporary = path.with_suffix(
        ".tmp"
    )

    with temporary.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            state,
            handle,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    temporary.replace(path)


def source_fingerprint(
    source: dict[str, Any],
) -> str:

    material = {
        "title": source.get("title"),
        "description": source.get(
            "description"
        ),
        "data_link": source.get(
            "data_link"
        ),
        "frequency": source.get(
            "frequency"
        ),
        "granularity": source.get(
            "granularity"
        ),
    }

    encoded = json.dumps(
        material,
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")

    return hashlib.sha256(
        encoded
    ).hexdigest()


def mark_success(
    dataset_id: str,
    source: dict[str, Any],
    artifact_sha256: str | None,
    output_sha256: str | None,
    latest_period: str | None,
    rows: int,
) -> None:

    save_agent_state(
        dataset_id,
        {
            "dataset_id": dataset_id,
            "source_fingerprint": (
                source_fingerprint(source)
            ),
            "artifact_sha256": (
                artifact_sha256
            ),
            "output_sha256": output_sha256,
            "latest_period": latest_period,
            "rows": rows,
            "status": "success",
            "last_successful_run": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        },
    )