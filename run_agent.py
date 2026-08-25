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
from agent.model import QwenModel
from agent.state import (
    get_dataset_state,
    update_dataset_state,
)


ROOT = Path(__file__).resolve().parent

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
    Determine whether a dataset should be treated as an API
    source.

    This is only the current catalog-level API filter.
    Deeper website/backend detection will be handled by the
    autonomous agent itself.
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

    for term in API_TERMS:
        if term in combined:
            return True

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
# DATASET ID
# ==============================================================


def make_dataset_id(
    definition: Any,
    dataset: dict[str, Any],
) -> str | None:
    """
    Resolve a stable dataset ID.

    Different catalog-definition implementations may expose the
    identifier under different names, so this function provides
    one central resolution point.
    """

    # ----------------------------------------------------------
    # First: context dictionary
    # ----------------------------------------------------------

    value = dataset.get(
        "dataset_id"
    )

    if value:
        return str(value)

    value = dataset.get(
        "id"
    )

    if value:
        return str(value)

    # ----------------------------------------------------------
    # Second: catalog definition attributes
    # ----------------------------------------------------------

    for attribute in (
        "dataset_id",
        "id",
        "name",
        "key",
    ):

        value = getattr(
            definition,
            attribute,
            None,
        )

        if value:
            return str(value)

    # ----------------------------------------------------------
    # Third: generate a stable ID from the title
    # ----------------------------------------------------------

    title = str(
        dataset.get(
            "data_title",
            "",
        )
    ).strip()

    if title:

        generated = re.sub(
            r"[^a-z0-9]+",
            "_",
            title.lower(),
        ).strip("_")

        if generated:
            return generated

    return None


# ==============================================================
# OUTPUT
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
    Convert catalog definitions into agent contexts.

    API datasets are skipped before the requested limit is
    applied.

    Every selected dataset is guaranteed to contain dataset_id.
    """

    selected: list[
        dict[str, Any]
    ] = []

    for definition in datasets:

        dataset = (
            definition.to_agent_context()
        )

        # ------------------------------------------------------
        # Resolve dataset ID.
        # ------------------------------------------------------

        dataset_id = make_dataset_id(
            definition,
            dataset,
        )

        if not dataset_id:

            print(
                "[SKIP] Dataset has no usable ID: "
                f"{dataset.get('data_title', 'UNKNOWN')}"
            )

            continue

        dataset[
            "dataset_id"
        ] = dataset_id

        # ------------------------------------------------------
        # API FILTER
        # ------------------------------------------------------

        if is_api_dataset(
            dataset
        ):

            print(
                f"[SKIP API] "
                f"{dataset.get('data_title', 'UNKNOWN')}"
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
    """
    Run one dataset using the already-loaded generic agent.
    """

    dataset_id = dataset.get(
        "dataset_id"
    )

    if not dataset_id:

        return {
            "success": False,
            "status": "failed",
            "dataset_id": "unknown",
            "message": (
                "Dataset does not contain "
                "a dataset_id."
            ),
        }

    title = dataset.get(
        "data_title",
        dataset_id,
    )

    data_link = dataset.get(
        "data_link",
        "",
    )

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
        f"URL:     {data_link}"
    )

    print(
        "=" * 75
    )

    # ----------------------------------------------------------
    # FINGERPRINT
    # ----------------------------------------------------------

    catalog_fingerprint = (
        fingerprint_dataset(
            dataset
        )
    )

    # ----------------------------------------------------------
    # PREVIOUS STATE
    # ----------------------------------------------------------

    previous_state = (
        get_dataset_state(
            dataset_id
        )
    )

    # ----------------------------------------------------------
    # CHANGE / OUTPUT GATE
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
        data_link=data_link,
    )

    # ----------------------------------------------------------
    # AGENT
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
            "traceback": traceback_text,
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
    # OUTPUT
    # ----------------------------------------------------------

    submission = result.get(
        "submission",
        {},
    )

    if isinstance(
        submission,
        dict,
    ):

        csv_path = submission.get(
            "path"
        )

    else:

        csv_path = None

    if csv_path:

        csv_file = Path(
            csv_path
        )

    else:

        csv_file = output_path(
            dataset_id
        )

    # ----------------------------------------------------------
    # VERIFY CSV
    # ----------------------------------------------------------

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
    # METADATA
    # ----------------------------------------------------------

    if isinstance(
        submission,
        dict,
    ):

        rows = submission.get(
            "rows"
        )

        columns = submission.get(
            "columns"
        )

    else:

        rows = None
        columns = None

    # ----------------------------------------------------------
    # SUCCESS
    # ----------------------------------------------------------

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
# IN-PROCESS RUNNER
# ==============================================================


def run_datasets(
    agent: GenericExtractionAgent,
    limit: int = 5,
    catalog_path: str | Path = CATALOG_PATH,
) -> list[dict[str, Any]]:
    """
    Run multiple datasets using ONE already-loaded agent.

    This is the preferred Colab entry point.

    Qwen is NOT loaded here.
    """

    if limit <= 0:

        raise ValueError(
            "limit must be greater than zero."
        )

    catalog_path = Path(
        catalog_path
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
        f"Requested datasets: {limit}"
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
    # SELECT
    # ----------------------------------------------------------

    print(
        "\n[2/4] Selecting non-API datasets..."
    )

    datasets = select_datasets(
        definitions,
        limit,
    )

    print(
        f"Selected: {len(datasets)}"
    )

    if not datasets:

        print(
            "No eligible non-API datasets found."
        )

        return []

    for index, dataset in enumerate(
        datasets,
        start=1,
    ):

        print(
            f"{index}. "
            f"{dataset.get('data_title', 'UNKNOWN')}"
        )

    # ----------------------------------------------------------
    # PROCESS
    # ----------------------------------------------------------

    print(
        "\n[3/4] Processing datasets..."
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

            dataset_id = dataset.get(
                "dataset_id",
                "unknown",
            )

            result = {
                "success": False,
                "status": "failed",
                "dataset_id": dataset_id,
                "error_type": type(
                    exc
                ).__name__,
                "message": str(
                    exc
                ),
                "traceback": traceback.format_exc(),
            }

        results.append(
            result
        )

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

    print(
        "\n[4/4] Run summary..."
    )

    successful = sum(
        1
        for result in results
        if result.get(
            "success",
            False,
        )
    )

    unchanged = sum(
        1
        for result in results
        if result.get(
            "status"
        ) == "unchanged"
    )

    regenerated = sum(
        1
        for result in results
        if result.get(
            "status"
        ) == "regenerated"
    )

    failed = sum(
        1
        for result in results
        if result.get(
            "status"
        ) == "failed"
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
        f"Processed:   {len(results)}"
    )

    print(
        f"Successful:  {successful}"
    )

    print(
        f"Unchanged:   {unchanged}"
    )

    print(
        f"Regenerated: {regenerated}"
    )

    print(
        f"Failed:      {failed}"
    )

    print()

    for result in results:

        print(
            f"{result.get('dataset_id', 'unknown')}: "
            f"{result.get('status', 'unknown')}"
        )

    return results


# ==============================================================
# CLI
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
            "datasets to process."
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
    # LOAD QWEN ONCE
    # ----------------------------------------------------------

    print(
        "\n[1/2] Loading Qwen..."
    )

    model = QwenModel(
        load_in_4bit=True,
        device_map="auto",
    )

    agent = GenericExtractionAgent(
        model
    )

    # ----------------------------------------------------------
    # RUN
    # ----------------------------------------------------------

    print(
        "\n[2/2] Processing datasets..."
    )

    run_datasets(
        agent=agent,
        limit=args.limit,
        catalog_path=catalog_path,
    )

    return 0


# ==============================================================
# ENTRY POINT
# ==============================================================


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
