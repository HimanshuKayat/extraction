from __future__ import annotations

from core.source_loader import load_sources
from core.runner import run_dataset


def main() -> None:

    sources = load_sources()

    print()
    print(
        "=" * 70
    )
    print(
        "GENERIC AUTONOMOUS DATA EXTRACTION"
    )
    print(
        "=" * 70
    )

    print(
        f"DATASETS FOUND: {len(sources)}"
    )

    print(
        "=" * 70
    )

    successful = 0
    unchanged = 0
    failed = 0

    for index, source in enumerate(
        sources,
        start=1,
    ):

        dataset_id = source[
            "dataset_id"
        ]

        title = source[
            "title"
        ]

        print()
        print(
            "=" * 70
        )
        print(
            f"[{index}/{len(sources)}] "
            f"{title}"
        )
        print(
            f"DATASET ID: {dataset_id}"
        )
        print(
            "=" * 70
        )

        try:

            result = run_dataset(
                dataset_id
            )

        except Exception as exc:

            result = {
                "success": False,
                "status": "failed",
                "dataset_id": dataset_id,
                "error_type": type(
                    exc
                ).__name__,
                "message": str(exc),
            }

        print()
        print(
            "RESULT:"
        )

        print(result)

        if result.get(
            "success",
            False,
        ):

            status = result.get(
                "status"
            )

            if status == "unchanged":

                unchanged += 1

            else:

                successful += 1

        else:

            failed += 1

    print()
    print(
        "=" * 70
    )
    print(
        "BATCH COMPLETE"
    )
    print(
        "=" * 70
    )

    print(
        f"Successful: {successful}"
    )

    print(
        f"Unchanged:  {unchanged}"
    )

    print(
        f"Failed:     {failed}"
    )

    print(
        f"Total:      {len(sources)}"
    )

    print(
        "=" * 70
    )


if __name__ == "__main__":
    main()