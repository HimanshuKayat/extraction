from __future__ import annotations

import argparse
import json
import re
import traceback
from pathlib import Path
from typing import Any

from agent.catalog import load_catalog
from agent.fingerprint import fingerprint_dataset
from agent.generic_agent import GenericExtractionAgent
from agent.state import (
    get_dataset_state,
    update_dataset_state,
)
from agent.model import QwenModel


ROOT = Path(__file__).resolve().parent

# Change this filename if your master workbook has a different name.
CATALOG_PATH = (
    ROOT
    / "data_dictionary_final_v2 (1)(2).xlsx"
)


# ==============================================================
# API DETECTION
# ==============================================================

API_TERMS = {
    "api",
    "rest api",
    "rest",
    "graphql",
    "web api",
    "json api",
    "api endpoint",
}


def is_api_dataset(
    dataset: dict[str, Any],
) -> bool:
    """
    Determine whether a catalog entry represents an API
    source.

    This intentionally uses the catalog metadata rather than
    guessing from the URL alone.
    """

    source = str(
        dataset.get(
            "data_source",
            "",
        )
    ).lower()

    description = str(
        dataset.get(
            "data_description",
            "",
        )
    ).lower()

    url = str(
        dataset.get(
            "data_link",
            "",
        )
    ).lower()

    combined = " ".join(
        [
            source,
            description,
            url,
        ]
    )

    # Explicit API indicators.
    for term in API_TERMS:
        if term in combined:
            return True

    # Common API URL patterns.
    api_patterns = [
        r"/api/",
        r"/api$",
        r"\.json$",
        r"graphql",
    ]

    for pattern in api_patterns:
        if re.search(
            pattern,
            url,
        ):
            return True

    return False


# ==============================================================
# OUTPUT CHECK
# ==============================================================


def output_path(
    dataset_id: str,
) -> Path:

    return (
        ROOT
        / "processed"
        / dataset_id
        / f"{dataset_id}.csv"
    )


# ==============================================================
# DATASET SELECTION
# ==============================================================


def select_datasets(
    datasets: list[Any],
    limit: int,
) -> list[dict[str, Any]]:
    """
    Convert catalog definitions to agent dictionaries and
    select the first eligible non-API datasets.

    API datasets are skipped before the limit is applied.
    """

    selected: list[
        dict[str, Any]
    ] = []

    for definition in datasets:

        dataset = (
            definition.to_agent_context()
        )

        if is_api_dataset(
            dataset
        ):
            print(
                f"[SKIP API] "
                f"{dataset['data_title']}"
            )
            continue

        selected.append(
            dataset
        )

        if len(selected) >= limit:
            break

    return selected


# ==============================================================
# DATASET RUN
# ==============================================================


def run_one_dataset(
    agent: GenericExtractionAgent,
    dataset: dict[str, Any],
) -> dict[str, Any]:

    dataset_id = dataset[
        "dataset_id"
    ]

    title = dataset[
        "data_title"
    ]

    print()
    print(
        "=" * 75
    )
    print(
        f"DATASET: {title}"
    )
    print(
        f"ID:      {dataset_id}"
    )
    print(
        f"URL:     {dataset['data_link']}"
    )
    print(
        "=" * 75
    )

    catalog_fingerprint = (
        fingerprint_dataset(
            dataset
        )
    )

    previous_state = (
        get_dataset_state(
            dataset_id
        )
    )

    # ----------------------------------------------------------
    # CHECK WHETHER THIS DATASET IS ALREADY CURRENT
    # ----------------------------------------------------------

    if previous_state:

        previous_fingerprint = (
            previous_state.get(
                "catalog_fingerprint"
            )
        )

        previous_status = (
            previous_state.get(
                "status"
            )
        )

        existing_output = (
            output_path(
                dataset_id
            )
        )

        if (
            previous_status
            == "success"
            and previous_fingerprint
            == catalog_fingerprint
            and existing_output.exists()
        ):

            print(
                "\n[SKIP]"
            )

            print(
                "Dataset definition has not "
                "changed and output already exists."
            )

            print(
                f"Existing CSV: "
                f"{existing_output}"
            )

            return {
                "success": True,
                "status": "unchanged",
                "dataset_id": dataset_id,
                "output": str(
                    existing_output
                ),
            }

    # ----------------------------------------------------------
    # MARK RUNNING
    # ----------------------------------------------------------

    update_dataset_state(
        dataset_id,
        status="running",
        catalog_fingerprint=(
            catalog_fingerprint
        ),
        data_title=title,
        data_link=dataset[
            "data_link"
        ],
    )

    # ----------------------------------------------------------
    # START AGENT
    # ----------------------------------------------------------

    print(
        "\n[AGENT]"
    )

    print(
        "Starting autonomous extraction..."
    )

    try:

        result = agent.run(
            dataset
        )

    except Exception as exc:

        traceback_text = (
            traceback.format_exc()
        )

        update_dataset_state(
            dataset_id,
            status="failed",
            catalog_fingerprint=(
                catalog_fingerprint
            ),
            error_type=type(
                exc
            ).__name__,
            error_message=str(
                exc
            ),
            traceback=(
                traceback_text
            ),
        )

        return {
            "success": False,
            "status": "failed",
            "dataset_id": dataset_id,
            "error_type": type(
                exc
            ).__name__,
            "message": str(
                exc
            ),
        }

    # ----------------------------------------------------------
    # AGENT FAILURE
    # ----------------------------------------------------------

    if not result.get(
        "success",
        False,
    ):

        update_dataset_state(
            dataset_id,
            status="failed",
            catalog_fingerprint=(
                catalog_fingerprint
            ),
            agent_result=result,
        )

        return {
            "success": False,
            "status": "failed",
            "dataset_id": dataset_id,
            "agent_result": result,
        }

    # ----------------------------------------------------------
    # VERIFY OUTPUT
    # ----------------------------------------------------------

    submission = result.get(
        "submission",
        {},
    )

    csv_path = (
        submission.get(
            "path"
        )
        if isinstance(
            submission,
            dict,
        )
        else None
    )

    if csv_path:

        csv_file = Path(
            csv_path
        )

    else:

        csv_file = output_path(
            dataset_id
        )

    if not csv_file.exists():

        error = (
            "Agent reported success, but "
            "the expected CSV output does not exist."
        )

        update_dataset_state(
            dataset_id,
            status="failed",
            catalog_fingerprint=(
                catalog_fingerprint
            ),
            error_message=error,
            agent_result=result,
        )

        return {
            "success": False,
            "status": "failed",
            "dataset_id": dataset_id,
            "message": error,
        }

    # ----------------------------------------------------------
    # SUCCESS
    # ----------------------------------------------------------

    rows = (
        submission.get(
            "rows"
        )
        if isinstance(
            submission,
            dict,
        )
        else None
    )

    columns = (
        submission.get(
            "columns"
        )
        if isinstance(
            submission,
            dict,
        )
        else None
    )

    update_dataset_state(
        dataset_id,
        status="success",
        catalog_fingerprint=(
            catalog_fingerprint
        ),
        output_path=str(
            csv_file.resolve()
        ),
        rows=rows,
        columns=columns,
        agent_result=result,
    )

    print(
        "\n[SUCCESS]"
    )

    print(
        f"CSV: {csv_file.resolve()}"
    )

    return {
        "success": True,
        "status": "success",
        "dataset_id": dataset_id,
        "rows": rows,
        "columns": columns,
        "output": str(
            csv_file.resolve()
        ),
    }


# ==============================================================
# MAIN
# ==============================================================


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Generic autonomous dataset "
            "extraction runner."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help=(
            "Number of eligible non-API "
            "datasets to process. "
            "Default: 5"
        ),
    )

    parser.add_argument(
        "--catalog",
        type=str,
        default=str(
            CATALOG_PATH
        ),
        help=(
            "Path to the master dataset "
            "catalog XLSX."
        ),
    )

    args = parser.parse_args()

    if args.limit <= 0:

        raise ValueError(
            "--limit must be greater than zero."
        )

    catalog_path = Path(
        args.catalog
    )

    print(
        "=" * 75
    )

    print(
        "GENERIC AUTONOMOUS EXTRACTION RUNNER"
    )

    print(
        "=" * 75
    )

    print(
        f"Catalog: {catalog_path}"
    )

    print(
        f"Requested datasets: {args.limit}"
    )

    # ----------------------------------------------------------
    # LOAD CATALOG
    # ----------------------------------------------------------

    print(
        "\n[1/4] Loading master catalog..."
    )

    definitions = load_catalog(
        catalog_path
    )

    print(
        f"Catalog datasets loaded: "
        f"{len(definitions)}"
    )

    # ----------------------------------------------------------
    # SELECT NON-API DATASETS
    # ----------------------------------------------------------

    print(
        "\n[2/4] Selecting non-API datasets..."
    )

    datasets = select_datasets(
        definitions,
        args.limit,
    )

    print(
        f"Selected: {len(datasets)}"
    )

    if not datasets:

        print(
            "No eligible non-API datasets found."
        )

        return 0

    for index, dataset in enumerate(
        datasets,
        start=1,
    ):

        print(
            f"{index}. "
            f"{dataset['data_title']}"
        )

    # ----------------------------------------------------------
    # LOAD QWEN
    # ----------------------------------------------------------

    print(
        "\n[3/4] Loading Qwen..."
    )

    model = QwenModel(
        load_in_4bit=False,
        device_map="cpu",
    )

    agent = (
        GenericExtractionAgent(
            model
        )
    )

    # ----------------------------------------------------------
    # PROCESS DATASETS
    # ----------------------------------------------------------

    print(
        "\n[4/4] Processing datasets..."
    )

    results: list[
        dict[str, Any]
    ] = []

    for index, dataset in enumerate(
        datasets,
        start=1,
    ):

        print()
        print(
            "#" * 75
        )

        print(
            f"PROCESSING "
            f"{index}/{len(datasets)}"
        )

        print(
            "#" * 75
        )

        try:

            result = run_one_dataset(
                agent,
                dataset,
            )

        except Exception as exc:

            result = {
                "success": False,
                "status": "failed",
                "dataset_id": dataset[
                    "dataset_id"
                ],
                "error_type": type(
                    exc
                ).__name__,
                "message": str(
                    exc
                ),
            }

        results.append(
            result
        )

        # ------------------------------------------------------
        # IMPORTANT:
        # One dataset failure must NOT stop the entire run.
        # ------------------------------------------------------

        if result.get(
            "success",
            False,
        ):

            print(
                "\nDataset completed."
            )

        else:

            print(
                "\nDataset failed."
            )

            print(
                json.dumps(
                    result,
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                )
            )

    # ----------------------------------------------------------
    # SUMMARY
    # ----------------------------------------------------------

    successful = sum(
        1
        for result in results
        if result.get(
            "success",
            False,
        )
    )

    failed = (
        len(results)
        - successful
    )

    print()
    print(
        "=" * 75
    )

    print(
        "RUN COMPLETE"
    )

    print(
        "=" * 75
    )

    print(
        f"Processed: {len(results)}"
    )

    print(
        f"Successful: {successful}"
    )

    print(
        f"Failed: {failed}"
    )

    print()

    for result in results:

        print(
            f"{result.get('dataset_id')}: "
            f"{result.get('status')}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )