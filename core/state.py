from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

STATE_DIR = ROOT / "state"
STATE_DB = STATE_DIR / "extraction_state.db"


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS extraction_state (
    dataset_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    last_run TEXT,
    last_success TEXT,
    last_sha256 TEXT,
    rows_loaded INTEGER,
    message TEXT,
    metadata TEXT
)
"""


def _connection() -> sqlite3.Connection:
    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        STATE_DB
    )

    connection.row_factory = sqlite3.Row

    return connection


def initialize_state_table() -> None:

    with _connection() as connection:

        connection.execute(
            CREATE_TABLE_SQL
        )

        connection.commit()


def write_state(
    dataset_id: str,
    status: str,
    *,
    sha256: str | None = None,
    rows_loaded: int | None = None,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:

    initialize_state_table()

    now = datetime.now(
        timezone.utc
    ).isoformat()

    with _connection() as connection:

        connection.execute(
            """
            INSERT INTO extraction_state (
                dataset_id,
                status,
                last_run,
                last_success,
                last_sha256,
                rows_loaded,
                message,
                metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(dataset_id)
            DO UPDATE SET
                status = excluded.status,
                last_run = excluded.last_run,

                last_success =
                    CASE
                        WHEN excluded.status = 'success'
                        THEN excluded.last_run
                        ELSE extraction_state.last_success
                    END,

                last_sha256 =
                    COALESCE(
                        excluded.last_sha256,
                        extraction_state.last_sha256
                    ),

                rows_loaded =
                    excluded.rows_loaded,

                message =
                    excluded.message,

                metadata =
                    excluded.metadata
            """,
            (
                dataset_id,
                status,
                now,
                now if status == "success" else None,
                sha256,
                rows_loaded,
                message,
                json.dumps(
                    metadata or {}
                ),
            ),
        )

        connection.commit()


def get_state(
    dataset_id: str,
) -> dict[str, Any] | None:

    initialize_state_table()

    with _connection() as connection:

        row = connection.execute(
            """
            SELECT
                dataset_id,
                status,
                last_run,
                last_success,
                last_sha256,
                rows_loaded,
                message,
                metadata
            FROM extraction_state
            WHERE dataset_id = ?
            """,
            (dataset_id,),
        ).fetchone()

    if row is None:
        return None

    result = dict(row)

    if result.get("metadata"):
        try:
            result["metadata"] = json.loads(
                result["metadata"]
            )
        except json.JSONDecodeError:
            pass

    return result