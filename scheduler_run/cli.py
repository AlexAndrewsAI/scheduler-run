"""Command line interface module.

Provides a typer-based CLI for the package.
"""

import logging
from pathlib import Path

import typer

from scheduler_run.config import Config
from scheduler_run.scheduler import Scheduler

app = typer.Typer(
    help="Scheduler CLI - Run scheduled commands from a YAML file",
    invoke_without_command=True,
)


@app.callback()
def main(
    yaml_path: Path = typer.Option(
        Path("schedule.yaml"),
        "--yaml-path",
        "-y",
        help="Path to the YAML file containing scheduled commands "
        "(default: schedule.yaml)",
    ),
) -> None:
    """Run the scheduler with commands from a YAML file.

    The YAML file should have a 'schedules' key with a list of entries,
    each containing: type, command, time
    Example:
        schedules:
          - type: system
            command: echo 'hello world'
            time: '14:10'

    Args:
        yaml_path: Path to the YAML file containing scheduled commands.
    """
    # Configure logging to display messages
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    config = Config(yaml_path=yaml_path)
    scheduler = Scheduler(config)
    scheduler.run()


if __name__ == "__main__":
    app()
