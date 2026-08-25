from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.config import load_yaml
from core.state import get_state


ROOT = Path(
    __file__
).resolve().parents[1]


def check_dataset(
    dataset_id: str,
) -> dict:

    config = load_yaml(
        ROOT
        / "pipelines"
        / dataset_id
        / "config.yaml"
    )

    state = get_state(
        dataset_id
    )

    if not state:

        return {
            "dataset_id": dataset_id,
            "stale": True,
            "reason": "never_run",
        }

    last_success = (
        state.get("last_success")
    )

    if last_success is None:

        return {
            "dataset_id": dataset_id,
            "stale": True,
            "reason": "no_successful_run",
        }

    frequency = config.get(
        "schedule",
        {},
    ).get(
        "frequency",
        "daily",
    )

    hours = {
        "hourly": 1,
        "daily": 24,
        "weekly": 168,
        "monthly": 720,
    }.get(
        frequency,
        24,
    )

    age = (
        datetime.now(
            timezone.utc
        )
        - last_success
    ).total_seconds() / 3600

    return {
        "dataset_id": dataset_id,
        "stale": age > hours,
        "age_hours": round(
            age,
            2,
        ),
        "expected_hours": hours,
    }


def check_all() -> list[dict]:

    pipelines = (
        ROOT / "pipelines"
    )

    results = []

    for directory in sorted(
        pipelines.iterdir()
    ):

        if not directory.is_dir():
            continue

        config = (
            directory / "config.yaml"
        )

        if not config.exists():
            continue

        results.append(
            check_dataset(
                directory.name
            )
        )

    return results