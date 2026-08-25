from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised when a dataset configuration is invalid."""


def load_yaml(path: str | Path) -> dict[str, Any]:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {path}"
        )

    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    if not isinstance(data, dict):
        raise ConfigError(
            f"Configuration must contain an object: {path}"
        )

    return data


def load_dataset_config(
    dataset_id: str,
    root: str | Path,
) -> dict[str, Any]:
    root = Path(root)

    config_path = (
        root
        / "pipelines"
        / dataset_id
        / "config.yaml"
    )

    config = load_yaml(config_path)

    validate_dataset_config(
        config,
        dataset_id,
    )

    return config


def validate_dataset_config(
    config: dict[str, Any],
    dataset_id: str | None = None,
) -> None:

    required = [
        "dataset",
        "source",
        "fetch",
        "artifact",
        "target",
        "validation",
    ]

    missing = [
        key
        for key in required
        if key not in config
    ]

    if missing:
        raise ConfigError(
            f"Missing configuration fields: {missing}"
        )

    configured_id = config["dataset"].get("id")

    if dataset_id and configured_id != dataset_id:
        raise ConfigError(
            f"Dataset ID mismatch: "
            f"expected {dataset_id}, "
            f"got {configured_id}"
        )

    if not config["source"].get("type"):
        raise ConfigError("source.type is required")

    if not config["target"].get("columns"):
        raise ConfigError(
            "target.columns must contain at least one field"
        )


def resolve_env(
    value: Any,
) -> Any:
    """
    Resolve ${ENV_VAR} references inside configuration.
    """

    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}"):
            name = value[2:-1]
            return os.environ.get(name)

    if isinstance(value, dict):
        return {
            key: resolve_env(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            resolve_env(item)
            for item in value
        ]

    return value