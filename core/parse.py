from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from pypdf import PdfReader


def inspect_file(
    path: str | Path,
) -> dict[str, Any]:

    path = Path(path)

    if not path.exists():

        return {
            "success": False,
            "error_type": "FileNotFound",
            "message": str(path),
        }

    return {
        "success": True,
        "path": str(path),
        "filename": path.name,
        "extension": path.suffix.lower(),
        "bytes": path.stat().st_size,
    }


def read_pdf(
    path: str | Path,
) -> dict[str, Any]:

    path = Path(path)

    reader = PdfReader(str(path))

    pages = []

    for index, page in enumerate(reader.pages):

        pages.append({
            "page": index + 1,
            "text": page.extract_text() or "",
        })

    return {
        "success": True,
        "page_count": len(pages),
        "pages": pages,
    }


def read_csv(
    path: str | Path,
    **kwargs: Any,
) -> pd.DataFrame:

    return pd.read_csv(
        path,
        **kwargs,
    )


def read_excel(
    path: str | Path,
    sheet_name: str | int = 0,
    **kwargs: Any,
) -> pd.DataFrame:

    return pd.read_excel(
        path,
        sheet_name=sheet_name,
        **kwargs,
    )


def read_json(
    path: str | Path,
) -> Any:

    import json

    with Path(path).open(
        "r",
        encoding="utf-8",
    ) as handle:

        return json.load(handle)