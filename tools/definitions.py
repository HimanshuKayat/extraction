from __future__ import annotations

from .browser_tools import (
    browser_open,
    browser_inspect,
    browser_close,
)

from .dataset_output import (
    submit_dataset,
)

from .file_tools import (
    inspect_file,
)

from .download_tools import (
    http_download,
)

from core.parse import (
    read_csv,
    read_excel,
    read_pdf,
)

from .pdf_tools import (
    extract_pdf_table,
)

from core.validate import (
    validate_required_fields,
    validate_row_count,
)

from .registry import (
    ToolSpec,
    ToolRegistry,
)


def build_registry() -> ToolRegistry:
    """
    Build the complete controlled tool registry.

    This is the ONLY collection of tools that the
    autonomous agent is allowed to execute.

    The model does not receive direct access to:

        - eval()
        - exec()
        - shell commands
        - arbitrary Python
        - arbitrary filesystem operations
    """

    registry = ToolRegistry()

    # ==============================================================
    # HTTP DOWNLOAD
    # ==============================================================

    registry.register(
        ToolSpec(
            name="http_download",
            description=(
                "Download a remote resource over HTTP. "
                "The tool automatically stores the artifact "
                "inside the controlled raw dataset directory. "
                "Use this for direct PDF, CSV, Excel, JSON, "
                "XML, ZIP, or other downloadable resources."
            ),
            category="download",
            function=http_download,
            argument_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": (
                            "The URL of the resource."
                        ),
                    },
                    "source_id": {
                        "type": "string",
                        "description": (
                            "Identifier of the dataset/source."
                        ),
                    },
                    "filename": {
                        "type": "string",
                        "description": (
                            "Filename to use for the "
                            "downloaded artifact."
                        ),
                    },
                },
                "required": [
                    "url",
                    "source_id",
                    "filename",
                ],
                "additionalProperties": False,
            },
        )
    )

    # ==============================================================
    # FILE INSPECTION
    # ==============================================================

    registry.register(
        ToolSpec(
            name="inspect_file",
            description=(
                "Inspect a downloaded artifact and determine "
                "its file type, extension, size, and basic "
                "metadata before extraction."
            ),
            category="file",
            function=inspect_file,
            argument_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                    },
                },
                "required": [
                    "path",
                ],
                "additionalProperties": False,
            },
        )
    )

    # ==============================================================
    # CSV
    # ==============================================================

    registry.register(
        ToolSpec(
            name="read_csv",
            description=(
                "Read a CSV artifact and inspect its "
                "structured tabular contents."
            ),
            category="file",
            function=read_csv,
            argument_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                    },
                },
                "required": [
                    "path",
                ],
                "additionalProperties": False,
            },
        )
    )

    # ==============================================================
    # EXCEL
    # ==============================================================

    registry.register(
        ToolSpec(
            name="read_excel",
            description=(
                "Read an Excel workbook and inspect its "
                "sheets and tabular contents."
            ),
            category="file",
            function=read_excel,
            argument_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                    },
                    "sheet_name": {
                        "type": "string",
                    },
                },
                "required": [
                    "path",
                ],
                "additionalProperties": False,
            },
        )
    )

    # ==============================================================
    # PDF
    # ==============================================================

    registry.register(
        ToolSpec(
            name="read_pdf",
            description=(
                "Read text and structural information "
                "from a PDF."
            ),
            category="file",
            function=read_pdf,
            argument_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                    },
                },
                "required": [
                    "path",
                ],
                "additionalProperties": False,
            },
        )
    )

    # ==============================================================
    # PDF TABLE EXTRACTION
    # ==============================================================

    registry.register(
        ToolSpec(
            name="extract_pdf_table",
            description=(
                "Extract a structured table from a PDF "
                "when the requested dataset is represented "
                "as a PDF table."
            ),
            category="extraction",
            function=extract_pdf_table,
            argument_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                    },
                    "page": {
                        "type": "integer",
                        "minimum": 1,
                    },
                },
                "required": [
                    "path",
                ],
                "additionalProperties": False,
            },
        )
    )

    # ==============================================================
    # VALIDATE REQUIRED FIELDS
    # ==============================================================

    registry.register(
        ToolSpec(
            name="validate_required_fields",
            description=(
                "Validate that extracted rows contain "
                "the required fields."
            ),
            category="validation",
            function=validate_required_fields,
            argument_schema={
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {
                            "type": "object",
                        },
                    },
                    "required_fields": {
                        "type": "array",
                        "items": {
                            "type": "string",
                        },
                    },
                },
                "required": [
                    "data",
                    "required_fields",
                ],
                "additionalProperties": False,
            },
        )
    )

    # ==============================================================
    # VALIDATE ROW COUNT
    # ==============================================================

    registry.register(
        ToolSpec(
            name="validate_row_count",
            description=(
                "Validate that extracted data contains "
                "the expected or minimum number of rows."
            ),
            category="validation",
            function=validate_row_count,
            argument_schema={
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                    },
                    "minimum_rows": {
                        "type": "integer",
                        "minimum": 0,
                    },
                    "expected_rows": {
                        "type": "integer",
                        "minimum": 0,
                    },
                },
                "required": [
                    "data",
                ],
                "additionalProperties": False,
            },
        )
    )

    # ==============================================================
    # BROWSER OPEN
    # ==============================================================

    registry.register(
        ToolSpec(
            name="browser_open",
            description=(
                "Open a webpage using the controlled "
                "Playwright browser. Use this for dynamic "
                "websites and pages requiring JavaScript."
            ),
            category="browser",
            function=browser_open,
            argument_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                    },
                    "timeout": {
                        "type": "integer",
                        "minimum": 1,
                    },
                },
                "required": [
                    "url",
                ],
                "additionalProperties": False,
            },
        )
    )

    # ==============================================================
    # BROWSER INSPECT
    # ==============================================================

    registry.register(
        ToolSpec(
            name="browser_inspect",
            description=(
                "Inspect the currently open webpage and "
                "return its title, text, links, and URL."
            ),
            category="browser",
            function=browser_inspect,
            argument_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        )
    )

    # ==============================================================
    # BROWSER CLOSE
    # ==============================================================

    registry.register(
        ToolSpec(
            name="browser_close",
            description=(
                "Close the active Playwright browser "
                "session."
            ),
            category="browser",
            function=browser_close,
            argument_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        )
    )

    # ==============================================================
    # FINAL DATASET SUBMISSION
    # ==============================================================

    registry.register(
        ToolSpec(
            name="submit_dataset",
            description=(
                "Submit the final extracted dataset. "
                "Each row must be a JSON object. "
                "Only submit actual extracted data. "
                "Do not submit guesses, empty datasets, "
                "or unrelated information."
            ),
            category="output",
            function=submit_dataset,
            argument_schema={
                "type": "object",
                "properties": {
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                        },
                    },
                    "columns": {
                        "type": "array",
                        "items": {
                            "type": "string",
                        },
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "notes": {
                        "type": "string",
                    },
                },
                "required": [
                    "rows",
                ],
                "additionalProperties": False,
            },
        )
    )

    return registry