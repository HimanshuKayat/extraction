from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def extract_pdf_table(
    path: str,
    page: int | None = None,
) -> dict[str, Any]:
    """
    Extract tables from a PDF.

    This is an agent-facing tool. It attempts multiple
    extraction strategies so the agent does not need to
    know which PDF table implementation to use.

    page:
        Optional 1-based page number.
    """

    pdf_path = Path(path)

    if not pdf_path.exists():
        return {
            "success": False,
            "error_type": "FileNotFoundError",
            "message": f"PDF does not exist: {path}",
            "recoverable": True,
        }

    if not pdf_path.is_file():
        return {
            "success": False,
            "error_type": "NotAFile",
            "message": f"Path is not a file: {path}",
            "recoverable": True,
        }

    if pdf_path.suffix.lower() != ".pdf":
        return {
            "success": False,
            "error_type": "InvalidFileType",
            "message": (
                f"Expected PDF but received: "
                f"{pdf_path.suffix}"
            ),
            "recoverable": True,
        }

    try:
        import pdfplumber
    except ImportError:
        return {
            "success": False,
            "error_type": "MissingDependency",
            "message": (
                "pdfplumber is required for PDF table "
                "extraction. Install it with: "
                "pip install pdfplumber"
            ),
            "recoverable": False,
        }

    try:

        all_tables: list[list[list[Any]]] = []
        pages_processed: list[int] = []

        with pdfplumber.open(pdf_path) as pdf:

            if page is not None:

                if page < 1 or page > len(pdf.pages):
                    return {
                        "success": False,
                        "error_type": "InvalidPage",
                        "message": (
                            f"Page {page} is outside the "
                            f"PDF range 1-{len(pdf.pages)}."
                        ),
                        "recoverable": True,
                    }

                page_objects = [
                    (
                        page,
                        pdf.pages[page - 1],
                    )
                ]

            else:

                page_objects = [
                    (index + 1, pdf_page)
                    for index, pdf_page
                    in enumerate(pdf.pages)
                ]

            for page_number, pdf_page in page_objects:

                tables = pdf_page.extract_tables()

                if not tables:
                    continue

                pages_processed.append(
                    page_number
                )

                for table in tables:

                    if table:
                        all_tables.append(table)

        if not all_tables:
            return {
                "success": False,
                "error_type": "NoTablesFound",
                "message": (
                    "No structured tables were found "
                    "in the requested PDF pages."
                ),
                "recoverable": True,
                "pages_processed": pages_processed,
            }

        rows: list[dict[str, Any]] = []

        for table_index, table in enumerate(
            all_tables
        ):

            if not table:
                continue

            cleaned = []

            for row in table:

                if row is None:
                    continue

                cleaned_row = [
                    (
                        str(value).strip()
                        if value is not None
                        else ""
                    )
                    for value in row
                ]

                if any(cleaned_row):
                    cleaned.append(
                        cleaned_row
                    )

            if not cleaned:
                continue

            # Treat first non-empty row as header.
            header = cleaned[0]

            # Ensure headers are unique and non-empty.
            normalized_headers = []

            seen: dict[str, int] = {}

            for index, value in enumerate(
                header
            ):

                name = (
                    value.strip()
                    or f"column_{index + 1}"
                )

                count = seen.get(
                    name,
                    0,
                )

                if count:
                    unique_name = (
                        f"{name}_{count + 1}"
                    )
                else:
                    unique_name = name

                seen[name] = count + 1

                normalized_headers.append(
                    unique_name
                )

            for data_row in cleaned[1:]:

                row_dict = {}

                for index, column in enumerate(
                    normalized_headers
                ):

                    value = (
                        data_row[index]
                        if index < len(data_row)
                        else ""
                    )

                    row_dict[column] = value

                row_dict["_table_index"] = (
                    table_index
                )

                rows.append(
                    row_dict
                )

        if not rows:
            return {
                "success": False,
                "error_type": "EmptyTables",
                "message": (
                    "Tables were detected but no "
                    "data rows could be extracted."
                ),
                "recoverable": True,
            }

        columns = []

        for row in rows:

            for column in row:

                if column not in columns:
                    columns.append(
                        column
                    )

        return {
            "success": True,
            "path": str(
                pdf_path.resolve()
            ),
            "rows": rows,
            "columns": columns,
            "row_count": len(rows),
            "table_count": len(all_tables),
            "pages_processed": pages_processed,
        }

    except Exception as exc:

        return {
            "success": False,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "recoverable": True,
        }