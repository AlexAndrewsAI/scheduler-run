"""Scheduler module.

Provides a scheduler that reads commands from a YAML file and runs them at
specified times.
"""

import logging
import shlex
import subprocess
import time

import schedule
import yaml

from scheduler_run.config import Config, ScheduleEntry


class Scheduler:
    """A scheduler that runs commands from a YAML file.

    Reads a YAML file with a list of schedule entries, each containing:
    type, command, and time fields.
    Schedules each command to run daily at the specified time.
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
        self.scheduled_commands: list[tuple[str, str]] = []

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
            self.scheduled_commands.append((command, time_str))
            logging.info(f"Scheduled system command '{command}' at {time_str}")
        else:
            raise ValueError(
                f"Unsupported command type: {command_type}. Supported types: system"
            )

    def load_schedule(self) -> None:
        """Load commands from YAML and schedule them.

        Reads the YAML file specified in config.yaml_path and schedules
        each command to run daily at the specified time.
        """
        yaml_path = self.config.yaml_path
        logging.info(f"Loading schedule from {yaml_path}")

        seen_entries: set[tuple[str, str, str]] = set()

        try:
            with open(yaml_path) as yamlfile:
                data = yaml.safe_load(yamlfile)
                if not data or "schedules" not in data:
                    logging.error("Invalid YAML format: missing 'schedules' key")
                    raise ValueError("Invalid YAML format: missing 'schedules' key")

                for entry_data in data["schedules"]:
                    try:
                        entry = ScheduleEntry(
                            type=entry_data.get("type", "").strip(),
                            command=entry_data.get("command", "").strip(),
                            time=entry_data.get("time", "").strip(),
                        )
                        entry_key = (entry.type, entry.command, entry.time)
                        if entry_key in seen_entries:
                            logging.warning(
                                f"Duplicate entry detected: type='{entry.type}', "
                                f"command='{entry.command}', time='{entry.time}'"
                            )
                        else:
                            seen_entries.add(entry_key)
                            self._schedule_command(
                                entry.type, entry.command, entry.time
                            )
                    except ValueError as e:
                        logging.warning(
                            f"Skipping invalid entry: {entry_data}. Error: {e}"
                        )
        except FileNotFoundError:
            logging.error(f"YAML file not found: {yaml_path}")
            raise
        except PermissionError:
            logging.error(f"Permission denied reading YAML file: {yaml_path}")
            raise
        except yaml.YAMLError as e:
            logging.error(f"YAML parsing error: {e}")
            raise
        except (KeyError, ValueError) as e:
            logging.error(f"Invalid YAML data: {e}")
            raise

        # Log all scheduled commands
        logging.info("Scheduled commands:")
        for command, time_str in self.scheduled_commands:
            logging.info(f"  - {command} at {time_str}")

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
