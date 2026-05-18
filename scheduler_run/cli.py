"""Command line interface module.

Provides a typer-based CLI for the package.
"""

from pathlib import Path

import typer

from scheduler_run.config import Config
from scheduler_run.scheduler import Scheduler

app = typer.Typer(
    help="Scheduler CLI - Run scheduled commands from a CSV file",
    invoke_without_command=True,
)


@app.callback()
def main(
    csv_path: Path = typer.Option(
        Path("schedule.csv"),
        "--csv-path",
        "-c",
        help="Path to the CSV file containing scheduled commands "
        "(default: schedule.csv)",
    ),
) -> None:
    """Run the scheduler with commands from a CSV file.

    The CSV file should have columns: type, command, time
    Example:
        type,command,time
        system,"echo 'hello world'",14:10

    Args:
        csv_path: Path to the CSV file containing scheduled commands.
    """
    config = Config(csv_path=csv_path)
    scheduler = Scheduler(config)
    scheduler.run()


if __name__ == "__main__":
    app()
