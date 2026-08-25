from __future__ import annotations

import os
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text


def database_url() -> str:

    value = os.environ.get(
        "DATABASE_URL"
    )

    if not value:
        raise RuntimeError(
            "DATABASE_URL is not configured."
        )

    return value


def load_dataframe(
    dataframe: pd.DataFrame,
    table_name: str,
    *,
    schema: str | None = None,
    if_exists: str = "append",
) -> dict[str, Any]:

    engine = create_engine(
        database_url()
    )

    dataframe.to_sql(
        table_name,
        engine,
        schema=schema,
        if_exists=if_exists,
        index=False,
        method="multi",
    )

    return {
        "success": True,
        "table": table_name,
        "schema": schema,
        "rows_loaded": len(dataframe),
    }


def execute_sql(
    query: str,
) -> None:

    engine = create_engine(
        database_url()
    )

    with engine.begin() as connection:

        connection.execute(
            text(query)
        )