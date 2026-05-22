"""scheduler-run.

A scheduler that runs commands from a YAML file at specified times using
pydantic for configuration and the schedule library for task scheduling.
"""

from scheduler_run.config import Config
from scheduler_run.scheduler import Scheduler

__version__ = "0.1.1"
__all__ = ["Config", "Scheduler"]
