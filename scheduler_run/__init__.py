"""Python package template.

A simple template for creating Python packages with configuration management
and a scheduler example.
"""

from scheduler_run.config import Config
from scheduler_run.scheduler import Scheduler

__version__ = "0.1.0"
__all__ = ["Config", "Scheduler"]
