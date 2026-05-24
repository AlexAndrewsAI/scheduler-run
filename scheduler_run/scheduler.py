"""Scheduler module.

Provides a scheduler that reads commands from a YAML file and runs them at
specified times.
"""

import datetime
import logging
import random
import shlex
import subprocess
import time

import schedule
import yaml
from pydantic import ValidationError

from scheduler_run.config import Config, ScheduleEntry

logger = logging.getLogger(__name__)


class Scheduler:
    """A scheduler that runs commands from a YAML file.

    Reads a YAML file with a list of schedule entries, each containing:
    type, command, and time fields.
    Schedules each command to run daily at the specified time.
    Currently only type "system" is supported.
    """

    def __init__(self, config: Config | None = None) -> None:
        """Initialize the Scheduler instance.

        Args:
            config: Optional configuration object. If not provided,
                   a default Config instance will be created.

        """
        if config is None:
            config = Config()
        self.config = config
        self.scheduled_commands: list[tuple[str, str, str, int]] = []

    def _run_system_command(self, command: str) -> None:
        """Run a system command.

        Args:
            command: The command to execute.

        """
        logger.info("Running system command: %s", command)
        try:
            args = shlex.split(command)
            subprocess.run(args, check=True)  # noqa: S603
        except FileNotFoundError as e:
            logger.error("Command not found: %s. Error: %s", command, e)
        except subprocess.CalledProcessError as e:
            logger.error("Command failed: %s. Error: %s", command, e)

    def _calculate_actual_time(self, time_str: str, delay_seconds: int) -> str:
        """Calculate the actual start time including the random delay.

        Args:
            time_str: The base time in H:MM or HH:MM format.
            delay_seconds: The calculated random delay in seconds.

        Returns:
            The actual time in HH:MM:SS format.

        """
        parts = time_str.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])

        total_seconds = hours * 3600 + minutes * 60 + delay_seconds
        total_seconds = total_seconds % (24 * 3600)

        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60

        return f"{h:02d}:{m:02d}:{s:02d}"

    def _calculate_next_run(
        self, target_time_str: str, now: datetime.datetime | None = None
    ) -> str:
        """Calculate the next run date and time.

        Args:
            target_time_str: The target execution time in HH:MM:SS format.
            now: Optional current datetime (for testing).

        Returns:
            The next execution datetime as a string in YYYY-MM-DD HH:MM:SS format.

        """
        if now is None:
            now = datetime.datetime.now()

        parts = target_time_str.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2]) if len(parts) > 2 else 0

        target_dt = now.replace(
            hour=hours, minute=minutes, second=seconds, microsecond=0
        )
        if target_dt <= now:
            target_dt += datetime.timedelta(days=1)

        return target_dt.strftime("%Y-%m-%d %H:%M:%S")

    def _schedule_command(
        self,
        command_type: str,
        command: str,
        time_str: str,
        delay: int = 0,
        repetitions: int = 0,
        interval: int = -1,
    ) -> None:
        """Schedule a single command.

        Args:
            command_type: The type of command (currently only "system" supported).
            command: The command to execute.
            time_str: The time to run the command in 24h format (e.g., "14:10").
            delay: Optional base delay in seconds.
            repetitions: Number of times to repeat the command (0 means no repetition).
            interval: Time in seconds between repetitions
                (only used when repetitions > 0). If -1 and repetitions > 0,
                the interval is auto-calculated to spread runs evenly
                throughout the day.

        """
        if command_type == "system":
            # Auto-calculate interval if -1 and repetitions > 0
            if interval == -1 and repetitions > 0:
                interval = (24 * 3600) // (repetitions + 1)
                logger.info(
                    "Auto-calculated interval: %ss to spread %s executions "
                    "evenly throughout the day",
                    interval,
                    repetitions + 1,
                )

            # Calculate the number of executions (1 + repetitions)
            num_executions = 1 + repetitions

            for i in range(num_executions):
                # Recalculate delay for each repetition
                if delay > 0:
                    actual_delay = max(
                        0, int(random.gauss(mu=delay, sigma=0.15 * delay))
                    )
                else:
                    actual_delay = 0

                # Calculate the base time for this execution
                if i == 0:
                    base_time_str = time_str
                else:
                    # Add interval to the previous execution time
                    parts = time_str.split(":")
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    total_seconds = hours * 3600 + minutes * 60 + (i * interval)
                    total_seconds = total_seconds % (24 * 3600)
                    h = total_seconds // 3600
                    m = (total_seconds % 3600) // 60
                    base_time_str = f"{h:02d}:{m:02d}"

                actual_time = self._calculate_actual_time(base_time_str, actual_delay)

                schedule.every().day.at(actual_time).do(
                    self._run_system_command, command
                )
                self.scheduled_commands.append(
                    (command_type, command, actual_time, actual_delay)
                )
                logger.info(
                    "Scheduled system command '%s' (execution %s/%s) at %s "
                    "with calculated delay %ss",
                    command,
                    i + 1,
                    num_executions,
                    actual_time,
                    actual_delay,
                )
        else:
            raise ValueError(
                f"Unsupported command type: {command_type}. Supported types: system"
            )

    def load_schedule(self) -> None:
        """Load commands from YAML and schedule them.

        Reads the YAML file(s) specified in config.yaml_path and schedules
        each command to run daily at the specified time. Multiple YAML files
        are merged as if they were a single concatenated file.

        This method uses a two-phase approach for atomicity:
        1. Load and validate all YAML files into memory
        2. Schedule all validated entries in one pass

        If any file fails to load or validate, no changes are made to the
        scheduled commands.
        """
        yaml_paths = self.config.yaml_paths
        logger.info("Loading schedule from %s YAML file(s)", len(yaml_paths))

        # Phase 1: Load and validate all YAML files
        all_entries: list[ScheduleEntry] = []
        seen_entries: set[tuple[str, str, str, int, int, int]] = set()

        for yaml_path in yaml_paths:
            logger.info("Loading schedule from %s", yaml_path)

            try:
                with open(yaml_path, encoding="utf-8") as yamlfile:
                    data = yaml.safe_load(yamlfile)
                    if not data or "schedules" not in data:
                        error_msg = (
                            f"Invalid YAML format in {yaml_path}: "
                            "missing 'schedules' key"
                        )
                        logger.error("%s", error_msg)
                        raise ValueError(error_msg)

                    for entry_data in data["schedules"]:
                        try:
                            if not isinstance(entry_data, dict):
                                error_msg = (
                                    f"Invalid entry in {yaml_path}: expected dict, "
                                    f"got {type(entry_data).__name__}: {entry_data}"
                                )
                                logger.error("%s", error_msg)
                                raise ValueError(error_msg)
                            entry = ScheduleEntry(**entry_data)
                            entry_key = (
                                entry.type,
                                entry.command,
                                entry.time,
                                entry.delay,
                                entry.repetitions,
                                entry.interval,
                            )
                            if entry_key in seen_entries:
                                if self.config.allow_duplicates:
                                    logger.info(
                                        "Allowing duplicate entry in %s: "
                                        "type='%s', command='%s', time='%s', "
                                        "delay=%s, repetitions=%s, interval=%s",
                                        yaml_path,
                                        entry.type,
                                        entry.command,
                                        entry.time,
                                        entry.delay,
                                        entry.repetitions,
                                        entry.interval,
                                    )
                                    all_entries.append(entry)
                                else:
                                    logger.warning(
                                        "Duplicate entry detected in %s: "
                                        "type='%s', command='%s', time='%s', "
                                        "delay=%s, repetitions=%s, interval=%s. "
                                        "Use allow_duplicates=True or "
                                        "--allow-duplicates to permit.",
                                        yaml_path,
                                        entry.type,
                                        entry.command,
                                        entry.time,
                                        entry.delay,
                                        entry.repetitions,
                                        entry.interval,
                                    )
                            else:
                                seen_entries.add(entry_key)
                                all_entries.append(entry)
                        except ValidationError as e:
                            error_msg = (
                                f"Invalid entry in {yaml_path}: {entry_data}. "
                                f"Error: {e}"
                            )
                            logger.error("%s", error_msg)
                            raise
            except FileNotFoundError:
                logger.error("YAML file not found: %s", yaml_path)
                raise
            except PermissionError:
                logger.error("Permission denied reading YAML file: %s", yaml_path)
                raise
            except yaml.YAMLError as e:
                logger.error("YAML parsing error in %s: %s", yaml_path, e)
                raise
            except (KeyError, ValueError) as e:
                logger.error("Invalid YAML data in %s: %s", yaml_path, e)
                raise

        # Phase 2: Clear and schedule all validated entries
        schedule.clear()
        self.scheduled_commands.clear()

        for entry in all_entries:
            self._schedule_command(
                entry.type,
                entry.command,
                entry.time,
                delay=entry.delay,
                repetitions=entry.repetitions,
                interval=entry.interval,
            )

        # Log all scheduled commands
        logger.info("Scheduled commands:")
        for command_type, command, time_str, delay in self.scheduled_commands:
            next_run = self._calculate_next_run(time_str)
            logger.info(
                "%s • %s • %s • delay: %ss",
                command_type,
                command,
                next_run,
                delay,
            )

    def run(self) -> None:
        """Run the scheduler.

        Loads the schedule and then runs the scheduled tasks in a loop.
        This method blocks indefinitely.
        """
        self.load_schedule()

        logger.info("Scheduler started. Press Ctrl+C to stop.")
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
