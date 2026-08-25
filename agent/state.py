from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "agent_state.json"


def _ensure_state_file() -> None:
    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not STATE_FILE.exists():
        STATE_FILE.write_text(
            "{}",
            encoding="utf-8",
        )


def load_state() -> dict[str, Any]:
    _ensure_state_file()

    try:
        return json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )
    except (
        json.JSONDecodeError,
        OSError,
    ):
        return {}


def save_state(
    state: dict[str, Any],
) -> None:

    _ensure_state_file()

    temporary = STATE_FILE.with_suffix(
        ".tmp"
    )

    temporary.write_text(
        json.dumps(
            state,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary.replace(
        STATE_FILE
    )


def get_dataset_state(
    dataset_id: str,
) -> dict[str, Any] | None:

    state = load_state()

    value = state.get(
        dataset_id
    )

    if isinstance(
        value,
        dict,
    ):
        return value

    return None


def update_dataset_state(
    dataset_id: str,
    **values: Any,
) -> dict[str, Any]:

    state = load_state()

    existing = state.get(
        dataset_id,
        {},
    )

    if not isinstance(
        existing,
        dict,
    ):
        existing = {}

    existing.update(
        values
    )

    existing[
        "updated_at"
    ] = time.time()

    state[
        dataset_id
    ] = existing

    save_state(
        state
    )

    return existing


def remove_dataset_state(
    dataset_id: str,
) -> None:

    state = load_state()

    state.pop(
        dataset_id,
        None,
    )

    save_state(
        state
    )