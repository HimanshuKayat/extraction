from __future__ import annotations

from pathlib import Path
from typing import Any

from .sha256 import sha256_file


def change_gate(
    path: str | Path,
    previous_hash: str | None,
) -> dict[str, Any]:

    path = Path(path)

    if not path.exists():
        return {
            "changed": False,
            "status": "missing",
            "sha256": None,
        }

    current_hash = sha256_file(path)

    if previous_hash is None:
        return {
            "changed": True,
            "status": "new",
            "sha256": current_hash,
        }

    if current_hash == previous_hash:
        return {
            "changed": False,
            "status": "unchanged",
            "sha256": current_hash,
        }

    return {
        "changed": True,
        "status": "changed",
        "sha256": current_hash,
    }