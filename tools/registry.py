from __future__ import annotations

import asyncio
import inspect
import time

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import jsonschema
from jsonschema import ValidationError as JsonSchemaValidationError


FINISH_ACTION = "finish"


# ==============================================================
# CONTROLLED TOOL EXCEPTIONS
# ==============================================================


class ToolRegistryError(Exception):
    """Base exception for controlled tool execution."""


class InvalidArgumentsError(ToolRegistryError):
    """Tool arguments failed JSON-schema validation."""


class ToolDisabledError(ToolRegistryError):
    """Tool is registered but disabled."""


class ToolNotFoundError(ToolRegistryError):
    """Requested tool is not registered."""


class ToolExecutionError(ToolRegistryError):
    """Controlled tool execution failure."""

    def __init__(
        self,
        message: str,
        error_type: str = "ToolExecutionError",
        recoverable: bool = True,
    ) -> None:

        super().__init__(message)

        self.message = message
        self.error_type = error_type
        self.recoverable = recoverable


# ==============================================================
# TOOL SPECIFICATION
# ==============================================================


@dataclass
class ToolSpec:
    """
    Machine-readable description of a single tool.
    """

    name: str
    description: str
    category: str
    function: Optional[Callable[..., Any]]
    argument_schema: Dict[str, Any]
    enabled: bool = True

    def to_prompt_dict(
        self,
    ) -> Dict[str, Any]:

        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "arguments": self.argument_schema,
            "enabled": self.enabled,
        }


# ==============================================================
# TOOL REGISTRY
# ==============================================================


class ToolRegistry:
    """
    Controlled collection of tools available
    to the autonomous agent.
    """

    def __init__(
        self,
    ) -> None:

        self._tools: Dict[
            str,
            ToolSpec,
        ] = {}

    def register(
        self,
        spec: ToolSpec,
    ) -> None:

        if spec.name in self._tools:

            raise ValueError(
                f"Tool '{spec.name}' "
                "is already registered."
            )

        self._tools[
            spec.name
        ] = spec

    def get(
        self,
        name: str,
    ) -> ToolSpec:

        if name not in self._tools:

            raise ToolNotFoundError(
                f"Unknown tool: '{name}'"
            )

        return self._tools[
            name
        ]

    def list_enabled(
        self,
    ) -> List[ToolSpec]:

        return [
            spec
            for spec in self._tools.values()
            if spec.enabled
        ]

    def list_all(
        self,
    ) -> List[ToolSpec]:

        return list(
            self._tools.values()
        )

    def to_prompt_list(
        self,
    ) -> List[Dict[str, Any]]:

        return [
            spec.to_prompt_dict()
            for spec in self.list_enabled()
        ]


# ==============================================================
# ARGUMENT VALIDATION
# ==============================================================


def validate_arguments(
    spec: ToolSpec,
    arguments: Dict[str, Any],
) -> None:

    if not isinstance(
        arguments,
        dict,
    ):

        raise InvalidArgumentsError(
            (
                f"Arguments for tool "
                f"'{spec.name}' must be "
                f"a JSON object, got "
                f"{type(arguments).__name__}"
            )
        )

    try:

        jsonschema.validate(
            instance=arguments,
            schema=spec.argument_schema,
        )

    except JsonSchemaValidationError as exc:

        raise InvalidArgumentsError(
            (
                f"Invalid arguments for "
                f"tool '{spec.name}': "
                f"{exc.message}"
            )
        ) from exc


# ==============================================================
# ASYNC EXECUTION
# ==============================================================


def _run_async_result(
    result: Any,
) -> Any:
    """
    Execute an awaitable from the synchronous
    agent interface.

    If an event loop is already running in the
    current thread, execution is refused rather
    than nesting event loops.
    """

    try:

        asyncio.get_running_loop()

    except RuntimeError:

        return asyncio.run(
            result
        )

    # The coroutine has already been created by
    # the caller. Since we cannot execute it here,
    # close it to prevent "coroutine was never awaited"
    # warnings.

    if inspect.iscoroutine(
        result
    ):

        result.close()

    raise ToolExecutionError(
        message=(
            "An asynchronous tool cannot be "
            "executed through the synchronous "
            "agent interface while an event loop "
            "is already running."
        ),
        error_type=(
            "AsyncExecutionContextError"
        ),
        recoverable=False,
    )


def _execute_function(
    function: Callable[..., Any],
    arguments: Dict[str, Any],
) -> Any:
    """
    Execute either a synchronous or asynchronous
    tool function.
    """

    result = function(
        **arguments
    )

    if inspect.isawaitable(
        result
    ):

        return _run_async_result(
            result
        )

    return result


# ==============================================================
# SINGLE TOOL EXECUTION GATEWAY
# ==============================================================


def execute_action(
    registry: ToolRegistry,
    action: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Execute exactly one model-selected tool.

    The model can only execute functions that have
    explicitly been registered in ToolRegistry.
    """

    # ----------------------------------------------------------
    # FINISH
    # ----------------------------------------------------------

    if action == FINISH_ACTION:

        reason = (
            arguments.get(
                "reason",
                "",
            )
            if isinstance(
                arguments,
                dict,
            )
            else ""
        )

        return {
            "success": True,
            "action": FINISH_ACTION,
            "reason": reason,
        }

    # ----------------------------------------------------------
    # TOOL LOOKUP
    # ----------------------------------------------------------

    spec = registry.get(
        action
    )

    # ----------------------------------------------------------
    # ENABLED CHECK
    # ----------------------------------------------------------

    if not spec.enabled:

        raise ToolDisabledError(
            (
                f"Tool '{action}' is "
                "registered but disabled."
            )
        )

    # ----------------------------------------------------------
    # IMPLEMENTATION CHECK
    # ----------------------------------------------------------

    if spec.function is None:

        raise ToolDisabledError(
            (
                f"Tool '{action}' has no "
                "implementation."
            )
        )

    # ----------------------------------------------------------
    # ARGUMENT VALIDATION
    # ----------------------------------------------------------

    validate_arguments(
        spec,
        arguments,
    )

    # ----------------------------------------------------------
    # EXECUTION
    # ----------------------------------------------------------

    start = time.monotonic()

    try:

        result = _execute_function(
            spec.function,
            arguments,
        )

    except ToolExecutionError as exc:

        duration = (
            time.monotonic()
            - start
        )

        return {
            "success": False,
            "error_type": exc.error_type,
            "message": exc.message,
            "recoverable": exc.recoverable,
            "duration_seconds": round(
                duration,
                4,
            ),
        }

    except Exception as exc:

        duration = (
            time.monotonic()
            - start
        )

        return {
            "success": False,
            "error_type": type(
                exc
            ).__name__,
            "message": str(
                exc
            ),
            "recoverable": True,
            "duration_seconds": round(
                duration,
                4,
            ),
        }

    # ----------------------------------------------------------
    # NORMALIZE RESULT
    # ----------------------------------------------------------

    duration = (
        time.monotonic()
        - start
    )

    if isinstance(
        result,
        dict,
    ):

        result.setdefault(
            "success",
            True,
        )

        result[
            "duration_seconds"
        ] = round(
            duration,
            4,
        )

        return result

    return {
        "success": True,
        "result": result,
        "duration_seconds": round(
            duration,
            4,
        ),
    }