"""Command line interface module.

Provides a typer-based CLI for the package.
"""

import logging
from pathlib import Path

import typer

from scheduler_run import __version__
from scheduler_run.config import Config
from scheduler_run.scheduler import Scheduler

app = typer.Typer(
    help="Scheduler CLI - Run scheduled commands from a YAML file",
    invoke_without_command=True,
)


def version_callback(value: bool) -> None:
    """Handle the version flag callback."""
    if value:
        typer.echo(f"scheduler-run version: {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    files: list[Path] | None = typer.Argument(
        None,
        help="Path(s) to YAML file(s) containing scheduled commands "
        "(default: schedule.yaml)",
    ),
    allow_duplicates: bool = typer.Option(
        False,
        "--allow-duplicates",
        help="Allow duplicate schedule entries",
    ),
    max_concurrent: int | None = typer.Option(
        None,
        "--max-concurrent",
        help="Maximum number of concurrent subprocesses to run (default: unlimited)",
    ),
    version: bool | None = typer.Option(
        None,
        "--version",
        "-V",
        callback=version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Run the scheduler with commands from YAML file(s).

    The YAML file(s) should have a 'schedules' key with a list of entries,
    each containing: type, command, time, delay (optional), repetitions (optional),
    interval (optional)

    Example:
        schedules:
          - type: system
            command: echo 'hello world'
            time: '14:10'
            delay: 10
            repetitions: 3
            interval: 3600

    Args:
        files: List of paths to YAML files containing scheduled commands.
            If not provided, defaults to schedule.yaml in the current directory.
        allow_duplicates: When True, duplicate schedule entries are scheduled twice.
        max_concurrent: Maximum number of concurrent subprocesses to run.
            If None, there is no limit.
        version: Eager flag handled by version_callback; not used in the body.

    """
    # Configure logging to display messages only if not already configured
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Default to schedule.yaml if no files provided
    if not files:
        files = [Path("schedule.yaml")]

    config = Config(
        yaml_path=files,
        allow_duplicates=allow_duplicates,
        max_concurrent=max_concurrent,
    )
    scheduler = Scheduler(config)
    scheduler.run()


if __name__ == "__main__":
    app()
