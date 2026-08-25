from __future__ import annotations

from pathlib import Path
from typing import Any


def inspect_file(
    path: str,
) -> dict[str, Any]:
    """
    Inspect a local file without extracting its contents.

    The agent uses this to determine what kind of artifact
    it has received before choosing the appropriate reader.

    Supported observations include:

        - existence
        - filename
        - extension
        - size
        - basic file type

    This function intentionally does not execute arbitrary
    code or load untrusted files as Python objects.
    """

    file_path = Path(path)

    if not file_path.exists():

        return {
            "success": False,
            "error_type": "FileNotFoundError",
            "message": (
                f"File does not exist: {path}"
            ),
            "recoverable": True,
        }

    if not file_path.is_file():

        return {
            "success": False,
            "error_type": "NotAFile",
            "message": (
                f"Path is not a file: {path}"
            ),
            "recoverable": True,
        }

    suffix = file_path.suffix.lower()

    size_bytes = file_path.stat().st_size

    file_type = {
        ".pdf": "pdf",
        ".csv": "csv",
        ".xlsx": "excel",
        ".xls": "excel",
        ".xlsm": "excel",
        ".json": "json",
        ".xml": "xml",
        ".txt": "text",
        ".html": "html",
        ".htm": "html",
        ".zip": "zip",
    }.get(
        suffix,
        "unknown",
    )

    return {
        "success": True,
        "path": str(
            file_path.resolve()
        ),
        "filename": file_path.name,
        "extension": suffix,
        "file_type": file_type,
        "size_bytes": size_bytes,
    }