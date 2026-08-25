from __future__ import annotations

from core.output import write_csv

import importlib
import traceback
from pathlib import Path
from typing import Any

from agent.runner import GenericExtractionAgent
from tools.definitions import build_registry

from .config import load_dataset_config
from .gate import change_gate
from .fetch import fetch_resource
from .sha256 import sha256_file
from .state import get_state, write_state


ROOT = Path(__file__).resolve().parents[1]


class PipelineRunner:
    """
    Generic runner for every dataset.

    Two execution paths currently exist:

    1. Legacy deterministic pipeline
       Used by existing pipelines such as Railway.

    2. Generic autonomous agent
       Used when no dataset-specific parse.py exists.

    The long-term architecture is to move all
    datasets to the generic agent path.
    """

    def __init__(
        self,
        dataset_id: str,
    ) -> None:

        self.dataset_id = dataset_id

        self.config = load_dataset_config(
            dataset_id,
            ROOT,
        )

        self.pipeline_module = None

        try:

            self.pipeline_module = (
                importlib.import_module(
                    f"pipelines.{dataset_id}.parse"
                )
            )

        except ModuleNotFoundError as exc:

            expected_module = (
                f"pipelines.{dataset_id}.parse"
            )

            if exc.name != expected_module:
                raise

            self.pipeline_module = None

    # ============================================================
    # PIPELINE TYPE
    # ============================================================

    def _has_legacy_pipeline(self) -> bool:

        return (
            self.pipeline_module is not None
            and hasattr(
                self.pipeline_module,
                "parse",
            )
        )

    # ============================================================
    # LEGACY ARTIFACT PATH
    # ============================================================

    def _artifact_path(self) -> Path:

        artifact = self.config["artifact"]

        directory = (
            ROOT
            / artifact["directory"]
        )

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        return (
            directory
            / artifact["filename"]
        )

    # ============================================================
    # LEGACY FETCH
    # ============================================================

    def fetch(self) -> dict[str, Any]:

        source = self.config["source"]

        fetch = self.config["fetch"]

        return fetch_resource(
            url=source["url"],
            save_path=self._artifact_path(),
            preferred_method=fetch.get(
                "preferred_method",
                "http",
            ),
            fallback_method=fetch.get(
                "fallback_method",
                "browser",
            ),
            timeout=fetch.get(
                "timeout_seconds",
                30,
            ),
        )

    # ============================================================
    # LEGACY PARSE
    # ============================================================

    def parse(
        self,
        artifact_path: Path,
    ) -> Any:

        if self.pipeline_module is None:

            raise RuntimeError(
                f"Dataset '{self.dataset_id}' "
                "does not have a legacy parser."
            )

        if not hasattr(
            self.pipeline_module,
            "parse",
        ):

            raise RuntimeError(
                f"Pipeline '{self.dataset_id}' "
                "does not define parse()."
            )

        return self.pipeline_module.parse(
            artifact_path
        )

    # ============================================================
    # LEGACY VALIDATION
    # ============================================================

    def validate(
        self,
        data: Any,
    ) -> dict[str, Any]:

        if (
            self.pipeline_module is not None
            and hasattr(
                self.pipeline_module,
                "validate",
            )
        ):

            return self.pipeline_module.validate(
                data,
                self.config,
            )

        return {
            "success": True,
            "message": (
                "No dataset-specific validation "
                "function defined."
            ),
        }

    # ============================================================
    # GENERIC AGENT
    # ============================================================

    def run_with_agent(
        self,
    ) -> dict[str, Any]:
        """
        Execute the dataset using the generic
        autonomous Qwen agent.

        The agent decides how to:

            discover
            navigate
            download
            inspect
            extract
            submit
        """

        registry = build_registry()

        agent = GenericExtractionAgent(
            registry=registry,
            max_steps=25,
        )

        source = {
            "dataset_id": self.dataset_id,
            "title": self.config.get(
                "name",
                self.dataset_id,
            ),
            "source": self.config.get(
                "source",
                {},
            ),
            "description": self.config.get(
                "description",
            ),
            "frequency": self.config.get(
                "frequency",
            ),
            "granularity": self.config.get(
                "granularity",
            ),
        }

        result = agent.run(
            source
        )

        if not result.get(
            "success",
            False,
        ):

            return result

        data = result.get(
            "data"
        )

        if data is None:

            return {
                "success": False,
                "status": "failed",
                "dataset_id": self.dataset_id,
                "error_type": (
                    "NoDatasetReturned"
                ),
                "message": (
                    "Generic agent finished "
                    "without returning data."
                ),
                "agent": result,
            }

        if not isinstance(
            data,
            list,
        ):

            return {
                "success": False,
                "status": "failed",
                "dataset_id": self.dataset_id,
                "error_type": (
                    "InvalidAgentDataset"
                ),
                "message": (
                    "Agent returned data that "
                    "is not a list of rows."
                ),
                "agent": result,
            }

        if len(data) == 0:

            return {
                "success": False,
                "status": "failed",
                "dataset_id": self.dataset_id,
                "error_type": (
                    "EmptyAgentDataset"
                ),
                "message": (
                    "Agent returned zero rows."
                ),
                "agent": result,
            }

        # --------------------------------------------------------
        # Generic structural validation
        # --------------------------------------------------------

        if not all(
            isinstance(row, dict)
            for row in data
        ):

            return {
                "success": False,
                "status": "failed",
                "dataset_id": self.dataset_id,
                "error_type": (
                    "InvalidAgentRows"
                ),
                "message": (
                    "Every submitted row must "
                    "be a JSON object."
                ),
                "agent": result,
            }

        # --------------------------------------------------------
        # Write through existing CSV writer.
        # --------------------------------------------------------

        output_result = write_csv(
            data,
            self.dataset_id,
        )

        if not output_result.get(
            "success",
            False,
        ):

            return {
                "success": False,
                "status": "failed",
                "dataset_id": self.dataset_id,
                "error_type": (
                    "OutputError"
                ),
                "message": (
                    "Agent extraction succeeded "
                    "but CSV writing failed."
                ),
                "agent": result,
                "output": output_result,
            }

        rows = len(data)

        output_path = Path(
            output_result["path"]
        )

        output_hash = None

        if output_path.exists():

            output_hash = sha256_file(
                output_path
            )

        write_state(
            self.dataset_id,
            "success",
            rows_loaded=rows,
            metadata={
                "mode": "generic_agent",
                "agent_steps": result.get(
                    "steps"
                ),
                "agent_confidence": result.get(
                    "confidence"
                ),
                "output": output_result,
                "output_sha256": output_hash,
            },
        )

        return {
            "success": True,
            "status": "success",
            "dataset_id": self.dataset_id,
            "rows": rows,
            "output": output_result,
            "agent": {
                "steps": result.get(
                    "steps"
                ),
                "confidence": result.get(
                    "confidence"
                ),
            },
        }

    # ============================================================
    # LEGACY RUNNER
    # ============================================================

    def run_legacy(
        self,
    ) -> dict[str, Any]:

        artifact_path = (
            self._artifact_path()
        )

        previous_state = get_state(
            self.dataset_id
        )

        previous_hash = (
            previous_state.get(
                "last_sha256"
            )
            if previous_state
            else None
        )

        write_state(
            self.dataset_id,
            "running",
        )

        try:

            fetch_result = self.fetch()

            if not fetch_result.get(
                "success"
            ):

                write_state(
                    self.dataset_id,
                    "failed",
                    message=str(
                        fetch_result
                    ),
                )

                return fetch_result

            gate = change_gate(
                artifact_path,
                previous_hash,
            )

            if not gate["changed"]:

                output_path = (
                    ROOT
                    / "processed"
                    / self.dataset_id
                    / f"{self.dataset_id}.csv"
                )

                if output_path.exists():

                    write_state(
                        self.dataset_id,
                        "unchanged",
                        sha256=gate[
                            "sha256"
                        ],
                    )

                    return {
                        "success": True,
                        "status": "unchanged",
                        "dataset_id": (
                            self.dataset_id
                        ),
                        "sha256": gate[
                            "sha256"
                        ],
                        "output": {
                            "success": True,
                            "path": str(
                                output_path
                            ),
                            "regenerated": False,
                        },
                    }

                data = self.parse(
                    artifact_path
                )

                validation = self.validate(
                    data
                )

                if not validation.get(
                    "success",
                    False,
                ):

                    raise RuntimeError(
                        "Dataset validation failed: "
                        + str(validation)
                    )

                output_result = write_csv(
                    data,
                    self.dataset_id,
                )

                write_state(
                    self.dataset_id,
                    "success",
                    sha256=gate[
                        "sha256"
                    ],
                    rows_loaded=len(data),
                    metadata={
                        "validation": validation,
                        "output": output_result,
                        "regenerated": True,
                    },
                )

                return {
                    "success": True,
                    "status": "regenerated",
                    "dataset_id": (
                        self.dataset_id
                    ),
                    "sha256": gate[
                        "sha256"
                    ],
                    "rows": len(data),
                    "validation": validation,
                    "output": output_result,
                }

            data = self.parse(
                artifact_path
            )

            validation = self.validate(
                data
            )

            if not validation.get(
                "success",
                False,
            ):

                raise RuntimeError(
                    "Dataset validation failed: "
                    + str(validation)
                )

            output_result = write_csv(
                data,
                self.dataset_id,
            )

            rows = (
                len(data)
                if hasattr(
                    data,
                    "__len__",
                )
                else None
            )

            sha = sha256_file(
                artifact_path
            )

            write_state(
                self.dataset_id,
                "success",
                sha256=sha,
                rows_loaded=rows,
                metadata={
                    "validation": validation,
                    "fetch": fetch_result,
                },
            )

            return {
                "success": True,
                "status": "success",
                "dataset_id": (
                    self.dataset_id
                ),
                "rows": rows,
                "sha256": sha,
                "validation": validation,
                "output": output_result,
            }

        except Exception as exc:

            write_state(
                self.dataset_id,
                "failed",
                message=str(exc),
                metadata={
                    "traceback": (
                        traceback.format_exc()
                    ),
                },
            )

            return {
                "success": False,
                "status": "failed",
                "dataset_id": (
                    self.dataset_id
                ),
                "error_type": (
                    type(exc).__name__
                ),
                "message": str(exc),
            }

    # ============================================================
    # UNIVERSAL RUN
    # ============================================================

    def run(self) -> dict[str, Any]:
        """
        Universal dataset execution.

        Existing datasets with a deterministic
        pipeline continue using that pipeline.

        Datasets without a dataset-specific parser
        automatically use the generic Qwen agent.
        """

        if not self._has_legacy_pipeline():

            return self.run_with_agent()

        return self.run_legacy()


def run_dataset(
    dataset_id: str,
) -> dict[str, Any]:

    runner = PipelineRunner(
        dataset_id
    )

    return runner.run()