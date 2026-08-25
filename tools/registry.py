from __future__ import annotations

import asyncio
import inspect
import threading
import time

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import jsonschema
from jsonschema import ValidationError as JsonSchemaValidationError


FINISH_ACTION = "finish"

# Maximum time allowed for one asynchronous tool call.
#
# Browser tools already have their own internal timeouts, but this
# prevents a broken async operation from freezing the autonomous
# agent indefinitely.
ASYNC_TOOL_TIMEOUT_SECONDS = 60


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
# ASYNC WORKER
# ==============================================================


def _async_worker(
    coroutine: Any,
    result_holder: Dict[str, Any],
    finished: threading.Event,
) -> None:
    """
    Run one coroutine inside a dedicated thread and event loop.

    This prevents the synchronous agent from trying to nest
    asyncio.run() inside an already-running Colab/Jupyter loop.
    """

    async def runner() -> None:

        try:

            result_holder[
                "result"
            ] = await coroutine

        except BaseException as exc:

            result_holder[
                "exception"
            ] = exc

        finally:

            finished.set()

    try:

        asyncio.run(
            runner()
        )

    except BaseException as exc:

        result_holder[
            "exception"
        ] = exc

        finished.set()


def _run_async_result(
    result: Any,
    timeout: float = ASYNC_TOOL_TIMEOUT_SECONDS,
) -> Any:
    """
    Execute an awaitable in a dedicated worker thread.

    This function works whether the caller itself is running
    inside an asyncio event loop or not.
    """

    if not inspect.isawaitable(
        result
    ):

        return result

    result_holder: Dict[
        str,
        Any,
    ] = {}

    finished = (
        threading.Event()
    )

    worker = threading.Thread(
        target=_async_worker,
        args=(
            result,
            result_holder,
            finished,
        ),
        daemon=True,
    )

    worker.start()

    completed = finished.wait(
        timeout=timeout
    )

    if not completed:

        # We cannot safely kill a Python thread. The worker is
        # therefore daemonized and the registry returns control
        # to the agent.
        raise ToolExecutionError(
            message=(
                "Asynchronous tool execution "
                f"exceeded {timeout:.0f} seconds."
            ),
            error_type=(
                "AsyncToolTimeout"
            ),
            recoverable=True,
        )

    exception = result_holder.get(
        "exception"
    )

    if exception is not None:

        if isinstance(
            exception,
            ToolRegistryError,
        ):

            raise exception

        raise ToolExecutionError(
            message=str(
                exception
            ),
            error_type=type(
                exception
            ).__name__,
            recoverable=True,
        ) from exception

    return result_holder.get(
        "result"
    )


# ==============================================================
# FUNCTION EXECUTION
# ==============================================================


def _execute_function(
    function: Callable[..., Any],
    arguments: Dict[str, Any],
) -> Any:
    """
    Execute either a synchronous or asynchronous tool.
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

    The model can only execute functions that have explicitly
    been registered in ToolRegistry.
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

    try:

        spec = registry.get(
            action
        )

    except ToolRegistryError:

        raise

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

    except ToolRegistryError:

        raise

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
