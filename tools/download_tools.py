from __future__ import annotations

from pathlib import Path
from typing import Any

from core.fetch import fetch_resource


ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = ROOT / "raw"


def http_download(
    url: str,
    source_id: str,
    filename: str,
) -> dict[str, Any]:
    """
    Agent-facing HTTP download tool.

    The model supplies:
        url
        source_id
        filename

    The tool decides where the file is stored.

    Example:

        source_id = "railway_janshatabdi"
        filename = "Janshatabdi_Exp.pdf"

    becomes:

        raw/railway_janshatabdi/Janshatabdi_Exp.pdf
    """

    if not isinstance(url, str) or not url.strip():
        return {
            "success": False,
            "error_type": "InvalidURL",
            "message": "url cannot be empty.",
            "recoverable": True,
        }

    if not isinstance(source_id, str) or not source_id.strip():
        return {
            "success": False,
            "error_type": "InvalidSourceID",
            "message": "source_id cannot be empty.",
            "recoverable": True,
        }

    if not isinstance(filename, str) or not filename.strip():
        return {
            "success": False,
            "error_type": "InvalidFilename",
            "message": "filename cannot be empty.",
            "recoverable": True,
        }

    source_id = source_id.strip()

    # Prevent the agent from injecting directories
    # into the filename.
    filename = Path(
        filename.strip()
    ).name

    if filename in {
        "",
        ".",
        "..",
    }:
        return {
            "success": False,
            "error_type": "InvalidFilename",
            "message": "Invalid filename.",
            "recoverable": True,
        }

    destination = (
        RAW_DIR / source_id
    )

    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    save_path = (
        destination / filename
    )

    result = fetch_resource(
        url=url.strip(),
        save_path=save_path,
        preferred_method="http",
        fallback_method="browser",
        timeout=60,
    )

    if not isinstance(result, dict):
        return {
            "success": False,
            "error_type": "InvalidToolResult",
            "message": (
                "The underlying download "
                "function returned an invalid result."
            ),
            "recoverable": True,
        }

    if not result.get(
        "success",
        False,
    ):
        return result

    return {
        **result,
        "success": True,
        "url": url.strip(),
        "source_id": source_id,
        "filename": filename,
        "path": str(
            save_path.resolve()
        ),
    }