"""Scheduler module.

Provides a scheduler that reads commands from a CSV file and runs them at
specified times.
"""

import csv
import logging
import shlex
import subprocess
import time

import schedule

from scheduler_run.config import Config, ScheduleEntry


class Scheduler:
    """A scheduler that runs commands from a CSV file.

    Reads a CSV file with columns: type, command, time
    and schedules each command to run daily at the specified time.
    Currently only type "system" is supported.
    """

    def __init__(self, config: Config | None = None):
        """Initialize the Scheduler instance.

        Args:
            config: Optional configuration object. If not provided,
                   a default Config instance will be created.
        """
        if config is None:
            config = Config()
        self.config = config

    def _run_system_command(self, command: str) -> None:
        """Run a system command.

        Args:
            command: The command to execute.
        """
        logging.info(f"Running system command: {command}")
        try:
            args = shlex.split(command)
            subprocess.run(args, check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Command failed: {command}. Error: {e}")

    def _schedule_command(self, command_type: str, command: str, time_str: str) -> None:
        """Schedule a single command.

        Args:
            command_type: The type of command (currently only "system" supported).
            command: The command to execute.
            time_str: The time to run the command in 24h format (e.g., "14:10").
        """
        if command_type == "system":
            schedule.every().day.at(time_str).do(self._run_system_command, command)
            logging.info(f"Scheduled system command '{command}' at {time_str}")
        else:
            raise ValueError(f"Unsupported command type: {command_type}")

    def load_schedule(self) -> None:
        """Load commands from CSV and schedule them.

        Reads the CSV file specified in config.csv_path and schedules
        each command to run daily at the specified time.
        """
        csv_path = self.config.csv_path
        logging.info(f"Loading schedule from {csv_path}")

        try:
            with open(csv_path, newline="") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    try:
                        entry = ScheduleEntry(
                            type=row.get("type", "").strip(),
                            command=row.get("command", "").strip(),
                            time=row.get("time", "").strip(),
                        )
                        self._schedule_command(entry.type, entry.command, entry.time)
                    except ValueError as e:
                        logging.warning(f"Skipping invalid row: {row}. Error: {e}")
        except FileNotFoundError:
            logging.error(f"CSV file not found: {csv_path}")
            raise
        except PermissionError:
            logging.error(f"Permission denied reading CSV file: {csv_path}")
            raise
        except csv.Error as e:
            logging.error(f"CSV parsing error: {e}")
            raise
        except (KeyError, ValueError) as e:
            logging.error(f"Invalid CSV data: {e}")
            raise

        # Log all scheduled commands
        logging.info("Scheduled commands:")
        for job in schedule.jobs:
            if job.job_func is not None and job.job_func.args:
                command = job.job_func.args[0]
            else:
                command = "unknown"
            logging.info(f"  - {command} at {job.at_time}")

    def run(self) -> None:
        """Run the scheduler.

        Loads the schedule and then runs the scheduled tasks in a loop.
        This method blocks indefinitely.
        """
        self.load_schedule()

        logging.info("Scheduler started. Press Ctrl+C to stop.")
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Scheduler stopped by user")
