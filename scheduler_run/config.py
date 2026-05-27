"""Configuration module.

Provides configuration management using Pydantic models.
"""

import re
import shlex
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

# Type alias for a command runner registry
CommandRegistry = dict[str, Callable[..., None]]

# Module-level default registry.  Used for direct ScheduleEntry construction
# (e.g. in tests) and as the fallback when no per-Scheduler context is supplied.
# Typed as Callable[..., None] to allow optional keyword arguments (e.g. max_runtime)
COMMAND_RUNNERS: CommandRegistry = {}


# Placeholder for system runner - will be registered by Scheduler.__init__
# This ensures the registry is never empty during validation
def _system_runner_placeholder(_command: str) -> None:
    """Raise error if system command runner is not registered."""
    raise RuntimeError(
        "System command runner not registered. "
        "Initialize a Scheduler instance before using system commands."
    )


COMMAND_RUNNERS["system"] = _system_runner_placeholder


class Config(BaseModel):
    """Configuration for the scheduler.

    Attributes:
        yaml_path: Path(s) to the YAML file(s) containing scheduled commands.
            Accepts a string, Path, or a list of strings/Paths at construction
            time.  Always normalised to ``list[Path]`` at runtime by the
            validator; use the :attr:`yaml_paths` property for typed access.
        allow_duplicates: Whether to allow duplicate schedule entries.
            If False (default), duplicate entries are detected and skipped.
        max_concurrent: Maximum number of concurrent subprocesses to run.
            If None (default), there is no limit. If set to a positive integer,
            the scheduler will queue commands when the limit is reached and
            start them as slots become available.
        capture_output: Whether to capture stdout/stderr from subprocesses.
            If True (default), output is captured and logged on failure.
            If False, output is discarded (subprocess.DEVNULL).

    """

    yaml_path: str | Path | Sequence[Path | str] = Field(
        default_factory=lambda: [Path("schedule.yaml")],
        description="Path(s) to the YAML file(s) containing scheduled commands",
    )
    allow_duplicates: bool = Field(
        default=False,
        description="Whether to allow duplicate schedule entries",
    )
    max_concurrent: int | None = Field(
        default=5,
        description="Maximum number of concurrent subprocesses to run",
    )
    capture_output: bool = Field(
        default=True,
        description="Whether to capture stdout/stderr from subprocesses",
    )

    model_config = {"title": "Scheduler Config", "frozen": True}

    @property
    def yaml_paths(self) -> list[Path]:
        """Return yaml_path as a normalised list of Paths.

        The ``yaml_path`` field accepts flexible input types that mypy must be
        able to type-check at call sites.  This property is the single place
        that performs the final cast, giving callers a ``list[Path]`` with a
        correct static type.

        Returns:
            A list of Path objects derived from ``yaml_path``.

        Raises:
            TypeError: If the underlying yaml_path has an unexpected type.
                This can occur when using model_construct to bypass validators.

        """
        v = self.yaml_path
        # The field_validator already runs mode="before", so at runtime v is
        # always list[Path].  The isinstance checks below satisfy mypy so that
        # the return type is unambiguously list[Path] without a cast().
        if isinstance(v, str):
            return [Path(v)]
        if isinstance(v, Path):
            return [v]
        if isinstance(v, list):
            return [Path(item) if isinstance(item, str) else item for item in v]
        raise TypeError(
            f"Invalid type for yaml_path: {type(v)}. "
            "Use Config() constructor with proper validation "
            "instead of model_construct."
        )

    @field_validator("max_concurrent")
    @classmethod
    def validate_max_concurrent_positive(cls, v: int | None) -> int | None:
        """Validate that max_concurrent is None or a positive integer.

        Args:
            v: The max_concurrent value to validate.

        Returns:
            The validated max_concurrent value.

        Raises:
            ValueError: If max_concurrent is zero or negative.

        """
        if v is not None and v <= 0:
            raise ValueError(
                "max_concurrent must be a positive integer (got "
                f"{v}). Use None for unlimited concurrency."
            )
        return v

    @field_validator("yaml_path", mode="before")
    @classmethod
    def normalize_yaml_path(cls, v: Any) -> list[Path]:
        """Normalize yaml_path to a list of Paths.

        Args:
            v: The yaml_path value to normalize.

        Returns:
            A list of Path objects.

        Raises:
            TypeError: If the input type is invalid.

        """
        if isinstance(v, str):
            return [Path(v)]
        if isinstance(v, Path):
            return [v]
        if isinstance(v, list):
            return [Path(item) if isinstance(item, str) else item for item in v]
        raise TypeError(f"Invalid type for yaml_path: {type(v)}")


class ScheduleEntry(BaseModel):
    """A single schedule entry from the YAML file.

    Attributes:
        type: The type of command (e.g., "system").
        command: The command to execute.
        time: The time to run the command in 24h format (H:MM or HH:MM),
            where single-digit hours (H:MM) are allowed in addition to
            two-digit hours (HH:MM).
        delay: Optional delay in seconds, which triggers a random start delay.
        repetitions: Number of times to repeat the command (0 means no repetition).
        interval: Time offset in seconds from the base time for each repetition
            (only used when repetitions > 0). If set to -1 and repetitions > 0,
            the interval is auto-calculated to spread runs evenly throughout the day.

    """

    type: str = Field(description="The type of command (e.g., 'system')")
    command: str = Field(description="The command to execute (string or list of args)")
    time: str = Field(
        description=(
            "The time to run the command in 24h format (H:MM or HH:MM), "
            "where single-digit hours (H:MM) are allowed in addition to "
            "two-digit hours (HH:MM)"
        )
    )
    delay: int = Field(
        default=0,
        description="Optional delay in seconds, which triggers a random start delay",
    )
    repetitions: int = Field(
        default=0,
        description="Number of times to repeat the command (0 means no repetition)",
    )
    interval: int = Field(
        default=-1,
        description=(
            "Time offset in seconds from the base time for each repetition "
            "(only used when repetitions > 0). The timing for repetition i is "
            "calculated as base_time + (i * interval) + delay_i, where delay_i "
            "is a random delay recalculated for each execution. If set to -1 and "
            "repetitions > 0, the interval is auto-calculated to spread runs "
            "evenly throughout the day: 24*3600 / (repetitions + 1)"
        ),
    )
    max_runtime: int | None = Field(
        default=None,
        description=(
            "Maximum runtime in seconds for the job. Once a launched job hits "
            "this runtime, it and all child processes are recursively hard killed "
            "(SIGKILL). Defaults to None (no limit)."
        ),
    )

    model_config = {"title": "Schedule Entry", "frozen": True}

    @field_validator("time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate that time is in H:MM or HH:MM format.

        Args:
            v: The time string to validate.

        Returns:
            The validated time string.

        Raises:
            ValueError: If the time format is invalid.

        """
        if not re.match(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$", v):
            raise ValueError(
                f"Invalid time format: '{v}'. Expected format: H:MM or HH:MM (24-hour)"
            )
        return v

    @field_validator("command", mode="before")
    @classmethod
    def normalize_command(cls, v: str | list[str]) -> str:
        """Normalize command to string format.

        Args:
            v: The command as string or list of args.

        Returns:
            The command as a string.

        """
        if isinstance(v, list):
            return shlex.join(v)
        return v

    @field_validator("command")
    @classmethod
    def validate_command_not_empty(cls, v: str) -> str:
        """Validate that command is not empty.

        Args:
            v: The command string to validate.

        Returns:
            The validated command string.

        Raises:
            ValueError: If the command is empty.

        """
        if not v.strip():
            raise ValueError("Command cannot be empty")
        return v

    @field_validator("type")
    @classmethod
    def validate_type_supported(cls, v: str, info: ValidationInfo) -> str:
        """Validate that type is not empty and is a supported type.

        Checks the per-instance registry supplied via Pydantic validation
        context (key ``"registry"``) when available, and falls back to the
        module-level ``COMMAND_RUNNERS`` otherwise.  This allows ``Scheduler``
        to validate against its own isolated registry without mutating global
        state.

        Args:
            v: The type string to validate.
            info: Pydantic validation info; may carry a ``"registry"`` key in
                ``info.context`` that overrides the global registry.

        Returns:
            The validated type string.

        Raises:
            ValueError: If the type is empty or unsupported.

        """
        if not v.strip():
            raise ValueError("Type cannot be empty")
        registry: CommandRegistry = (
            info.context.get("registry", COMMAND_RUNNERS)
            if info.context
            else COMMAND_RUNNERS
        )
        if v not in registry:
            supported_types_str = ", ".join(sorted(registry.keys()))
            raise ValueError(
                f"Unsupported command type: '{v}'. "
                f"Supported types: {supported_types_str}"
            )
        return v

    @field_validator("max_runtime")
    @classmethod
    def validate_max_runtime_positive(cls, v: int | None) -> int | None:
        """Validate that max_runtime is positive if set.

        Args:
            v: The max_runtime value to validate.

        Returns:
            The validated max_runtime.

        Raises:
            ValueError: If max_runtime is not a positive integer.

        """
        if v is not None and v <= 0:
            raise ValueError("max_runtime must be a positive integer (seconds)")
        return v

    @field_validator("delay")
    @classmethod
    def validate_delay_non_negative(cls, v: int) -> int:
        """Validate that delay is non-negative.

        Args:
            v: The delay value to validate.

        Returns:
            The validated delay.

        Raises:
            ValueError: If the delay is negative.

        """
        if v < 0:
            raise ValueError("Delay must be a non-negative integer")
        return v

    @field_validator("repetitions")
    @classmethod
    def validate_repetitions_non_negative(cls, v: int) -> int:
        """Validate that repetitions is non-negative.

        Args:
            v: The repetitions value to validate.

        Returns:
            The validated repetitions.

        Raises:
            ValueError: If the repetitions is negative.

        """
        if v < 0:
            raise ValueError("Repetitions must be a non-negative integer")
        return v

    @model_validator(mode="after")
    def validate_interval_with_repetitions(self) -> "ScheduleEntry":
        """Validate that interval is consistent with repetitions.

        Args:
            self: The ScheduleEntry instance.

        Returns:
            The validated ScheduleEntry instance.

        Raises:
            ValueError: If interval is invalid for the given repetitions.

        """
        if self.repetitions > 0:
            if self.interval == 0:
                raise ValueError(
                    "Interval cannot be 0 when repetitions > 0. "
                    "Use -1 for auto-calculation or a positive value."
                )
            if self.interval < 0 and self.interval != -1:
                raise ValueError(
                    f"Interval cannot be negative (except -1) when repetitions > 0. "
                    f"Got: {self.interval}"
                )
        elif self.repetitions == 0 and self.interval > 0:
            raise ValueError(
                f"Interval ({self.interval}) is ignored when repetitions == 0. "
                "Set repetitions > 0 to use interval, or set interval to -1."
            )
        return self
