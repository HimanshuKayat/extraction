from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config import load_yaml


ROOT = Path(
    __file__
).resolve().parents[1]


def discover_datasets() -> list[str]:

    pipelines = (
        ROOT / "pipelines"
    )

    if not pipelines.exists():
        return []

    datasets = []

    for directory in sorted(
        pipelines.iterdir()
    ):

        if not directory.is_dir():
            continue

        if (
            directory.name.startswith(
                "_"
            )
        ):
            continue

        config = (
            directory / "config.yaml"
        )

        parse = (
            directory / "parse.py"
        )

        if (
            config.exists()
            and parse.exists()
        ):
            datasets.append(
                directory.name
            )

    return datasets


def build_registry() -> list[dict[str, Any]]:

    registry = []

    for dataset_id in discover_datasets():

        config = load_yaml(
            ROOT
            / "pipelines"
            / dataset_id
            / "config.yaml"
        )

        registry.append({
            "dataset_id": dataset_id,
            "name": config[
                "dataset"
            ]["name"],
            "source_type": config[
                "source"
            ]["type"],
            "source_url": config[
                "source"
            ].get("url"),
            "frequency": config.get(
                "schedule",
                {},
            ).get(
                "frequency",
                "daily",
            ),
        })

    return registry


if __name__ == "__main__":

    import json

    print(
        json.dumps(
            build_registry(),
            indent=2,
            ensure_ascii=False,
        )
    )