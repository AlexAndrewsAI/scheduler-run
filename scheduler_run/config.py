"""Configuration module.

Provides configuration management using Pydantic models.
"""

import re
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class Config(BaseModel):
    """Configuration for the scheduler.

    Attributes:
        yaml_path: Path to the YAML file containing scheduled commands.
    """

    yaml_path: Path = Field(
        default=Path("tests/schedule.yaml"),
        description="Path to the YAML file containing scheduled commands",
    )

    model_config = {"title": "Scheduler Config"}


class ScheduleEntry(BaseModel):
    """A single schedule entry from the YAML file.

    Attributes:
        type: The type of command (e.g., "system").
        command: The command to execute.
        time: The time to run the command in 24h format (H:MM or HH:MM),
            where single-digit hours (H:MM) are allowed in addition to
            two-digit hours (HH:MM).
    """

    type: str = Field(description="The type of command (e.g., 'system')")
    command: str = Field(description="The command to execute")
    time: str = Field(
        description=(
            "The time to run the command in 24h format (H:MM or HH:MM), "
            "where single-digit hours (H:MM) are allowed in addition to "
            "two-digit hours (HH:MM)"
        )
    )

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
    def validate_type_not_empty(cls, v: str) -> str:
        """Validate that type is not empty.

        Args:
            v: The type string to validate.

        Returns:
            The validated type string.

        Raises:
            ValueError: If the type is empty.
        """
        if not v.strip():
            raise ValueError("Type cannot be empty")
        return v
