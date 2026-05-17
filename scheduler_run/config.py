"""Configuration module.

Provides configuration management using Pydantic models.
"""

from pathlib import Path
from pydantic import BaseModel, Field


class Config(BaseModel):
    """Configuration for the scheduler.

    Attributes:
        csv_path: Path to the CSV file containing scheduled commands.
    """
    csv_path: Path = Field(default=Path("tests/schedule.csv"), description="Path to the CSV file containing scheduled commands")

    model_config = {"title": "Scheduler Config"}

