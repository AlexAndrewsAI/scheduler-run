"""Scheduler module.

Provides a scheduler that reads commands from a YAML file and runs them at
specified times.
"""

import datetime
import itertools
import json
import logging
import os
import random
import re
import shlex
import signal
import subprocess
import time
from collections import deque
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NamedTuple

import yaml
from pydantic import ValidationError

from scheduler_run.config import CommandRegistry, Config, ScheduleEntry

logger = logging.getLogger(__name__)

# Constants for delay randomization
DELAY_SIGMA_MULTIPLIER = 0.15  # 15% standard deviation for delay randomization


def _expand_variables(
    command: str, variables: dict[str, list[str | int | float]]
) -> list[tuple[str, dict[str, str | int | float | None]]]:
    """Expand a command using variable mappings with Cartesian product.

    Args:
        command: The command template with variable placeholders (e.g., '{num}').
        variables: A dictionary mapping variable names to lists of values.

    Returns:
        A list of (expanded_command, variable_mapping) tuples for each
        combination of variable values.

    """
    # Extract variable names from the command
    pattern = r"\{(\w+)\}"
    used_vars = set(re.findall(pattern, command))

    # If no variables are used in the command, return a single expansion
    # with the first value of each variable (for backward compatibility)
    if not used_vars:
        var_mapping = {k: v[0] if v else None for k, v in variables.items()}
        return [(command, var_mapping)]

    # Validate that all referenced variables are defined
    undefined_vars = used_vars - set(variables.keys())
    if undefined_vars:
        raise ValueError(
            f"Undefined variables in command: {', '.join(sorted(undefined_vars))}. "
            f"Defined variables: {', '.join(sorted(variables.keys()))}"
        )

    # Get the variable names in a consistent order (only used variables)
    var_names = sorted(used_vars)
    var_values = [variables[name] for name in var_names]

    # Compute Cartesian product
    expanded_commands: list[tuple[str, dict[str, str | int | float | None]]] = []
    for combination in itertools.product(*var_values):
        var_mapping = dict(zip(var_names, combination, strict=True))
        try:
            expanded_command = command.format(**var_mapping)
        except (KeyError, ValueError) as e:
            raise ValueError(f"Failed to substitute variables in command '{command}': {e}") from e
        expanded_commands.append((expanded_command, var_mapping))

    return expanded_commands


def _parse_time_to_next_run(
    target_time_str: str, now: datetime.datetime | None = None
) -> datetime.datetime:
    """Calculate the next run datetime for a given target time string.

    Args:
        target_time_str: The target execution time in HH:MM:SS format.
        now: Optional current datetime (for testing). Defaults to datetime.now().

    Returns:
        The next execution datetime. If the target time has already passed today,
        returns the target time for tomorrow.

    """
    if now is None:
        now = datetime.datetime.now()

    parts = target_time_str.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = int(parts[2]) if len(parts) > 2 else 0

    target_dt = now.replace(hour=hours, minute=minutes, second=seconds, microsecond=0)
    if target_dt <= now:
        target_dt += datetime.timedelta(days=1)

    return target_dt


class Job:
    """A scheduled job with execution details.

    Attributes:
        func: The function to execute.
        args: Positional arguments to pass to the function.
        kwargs: Keyword arguments to pass to the function.
        target_time_str: The target execution time in HH:MM:SS format.
        last_run: The datetime when this job was last run.
        next_run: The datetime when this job should next run.

    """

    def __init__(
        self,
        func: Callable[..., None],
        target_time_str: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize a Job instance.

        Args:
            func: The function to execute.
            target_time_str: The target execution time in HH:MM:SS format.
            *args: Positional arguments to pass to the function.
            **kwargs: Keyword arguments to pass to the function.

        """
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.target_time_str = target_time_str
        self.last_run: datetime.datetime | None = None
        self.next_run: datetime.datetime = self._calculate_next_run()

    def _calculate_next_run(self) -> datetime.datetime:
        """Calculate the next run datetime for this job.

        Returns:
            The next execution datetime.

        """
        return _parse_time_to_next_run(self.target_time_str)

    def should_run(self, now: datetime.datetime) -> bool:
        """Check if the job should run at the given time.

        Args:
            now: The current datetime.

        Returns:
            True if the job should run, False otherwise.

        """
        # If last_run was on a previous day, recalculate next_run based on last_run
        if self.last_run is not None:
            # Calculate what today's target time would be
            parts = self.target_time_str.split(":")
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2]) if len(parts) > 2 else 0

            today_target = now.replace(hour=hours, minute=minutes, second=seconds, microsecond=0)

            # If last_run was before today's target time and now is after it,
            # the job should run
            if self.last_run.date() < now.date() and now >= today_target:
                return True

        return now >= self.next_run

    def run(self) -> None:
        """Execute the job."""
        self.func(*self.args, **self.kwargs)
        self.last_run = datetime.datetime.now()
        self.next_run = self._calculate_next_run()


class JobRegistry:
    """A registry for managing scheduled jobs.

    This registry is owned by a Scheduler instance and avoids the global
    state issues of the schedule package.
    """

    def __init__(self) -> None:
        """Initialize an empty JobRegistry."""
        self._jobs: list[Job] = []

    def schedule_daily(
        self,
        func: Callable[..., None],
        time_str: str,
        *args: Any,
        **kwargs: Any,
    ) -> Job:
        """Schedule a function to run daily at a specific time.

        Args:
            func: The function to execute.
            time_str: The time to run in HH:MM format.
            *args: Positional arguments to pass to the function.
            **kwargs: Keyword arguments to pass to the function.

        Returns:
            The created Job instance.

        """
        # Convert HH:MM to HH:MM:SS
        parts = time_str.split(":")
        if len(parts) == 2:
            time_str = f"{time_str}:00"

        job = Job(func, time_str, *args, **kwargs)
        self._jobs.append(job)
        return job

    def clear(self) -> None:
        """Clear all jobs from the registry."""
        self._jobs.clear()

    def run_pending(self) -> None:
        """Run all jobs that are due to run."""
        now = datetime.datetime.now()
        for job in self._jobs:
            if job.should_run(now):
                try:
                    job.run()
                except Exception as e:
                    logger.error("Job execution failed: %s", e)

    def get_jobs(self) -> list[Job]:
        """Return a copy of the jobs list."""
        return list(self._jobs)


class RunningProcess(NamedTuple):
    """A tracked running subprocess with its metadata.

    Attributes:
        process: The underlying Popen object.
        start_time: Monotonic clock value at process start.
        max_runtime: Maximum allowed runtime in seconds, or None for no limit.

    """

    process: subprocess.Popen[bytes]
    start_time: float
    max_runtime: int | None


class ScheduledCommand(NamedTuple):
    """A scheduled command with its execution details.

    Attributes:
        command_type: The type of command (e.g., "system").
        command: The command to execute.
        time: The scheduled execution time in HH:MM:SS format.
        delay: The calculated random delay in seconds.
        max_runtime: Maximum allowed runtime in seconds, or None for no limit.

    """

    command_type: str
    command: str
    time: str
    delay: int
    max_runtime: int | None


class Scheduler:
    """A scheduler that runs commands from a YAML file.

    Reads a YAML file with a list of schedule entries, each containing:
    type, command, and time fields.
    Schedules each command to run daily at the specified time.
    Commands run in parallel as background subprocesses; stopping the
    scheduler (for example with Ctrl+C) terminates any still-running children.
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
        self.scheduled_commands: list[ScheduledCommand] = []
        self._running_processes: list[RunningProcess] = []
        self._pending_queue: deque[tuple[str, str, int | None]] = (
            deque()
        )  # (command_type, command, max_runtime)
        self._job_registry = JobRegistry()

        # Instance-level registry — isolated from global state and from other
        # Scheduler instances.  Populated here so the Scheduler owns its runners.
        self._command_runners: CommandRegistry = {
            "system": self._run_system_command,
        }

    def _reap_finished_processes(self) -> None:
        """Remove finished child processes and log their exit status."""
        still_running: list[RunningProcess] = []
        now = time.monotonic()
        for rp in self._running_processes:
            # Enforce max_runtime: hard-kill the process group if exceeded
            if rp.max_runtime is not None and rp.process.poll() is None:
                elapsed = now - rp.start_time
                if elapsed >= rp.max_runtime:
                    command = self._process_command(rp.process)
                    logger.warning(
                        "max_runtime of %ss exceeded for command '%s' "
                        "(elapsed %.1fs) — killing process group",
                        rp.max_runtime,
                        command,
                        elapsed,
                    )
                    self._kill_process_group(rp.process)
                    rp.process.wait()
                    continue

            return_code = rp.process.poll()
            if return_code is None:
                still_running.append(rp)
                continue
            command = self._process_command(rp.process)
            # Log captured output if available.
            # NOTE: communicate() must be called at most once per process.
            # This is safe here because _reap_finished_processes is the
            # sole consumer of each RunningProcess — nothing else reads
            # stdout/stderr — so the pipe buffers are still intact at
            # this point. If that invariant ever changes, buffer the
            # output at process-completion time instead of calling
            # communicate() here.
            if self.config.capture_output:
                stdout, stderr = rp.process.communicate()
                if return_code == 0:
                    logger.info("Command completed: %s (exit %s)", command, return_code)
                    if stdout:
                        logger.info("stdout: %s", stdout.decode(errors="replace").strip())
                    if stderr:
                        logger.info("stderr: %s", stderr.decode(errors="replace").strip())
                else:
                    logger.error("Command failed: %s (exit %s)", command, return_code)
                    if stdout:
                        logger.error("stdout: %s", stdout.decode(errors="replace").strip())
                    if stderr:
                        logger.error("stderr: %s", stderr.decode(errors="replace").strip())
                    logger.warning(
                        "Command '%s' failed with exit code %s. "
                        "Check the logs above for output details.",
                        command,
                        return_code,
                    )
            else:
                if return_code == 0:
                    logger.info("Command completed: %s (exit %s)", command, return_code)
                else:
                    logger.error("Command failed: %s (exit %s)", command, return_code)
        self._running_processes = still_running
        self._process_pending_queue()

    def _process_pending_queue(self) -> None:
        """Process pending commands from the queue when slots are available."""
        if not self._pending_queue:
            return

        max_concurrent = self.config.max_concurrent
        if max_concurrent is None:
            # No limit, process all pending commands
            while self._pending_queue:
                command_type, command, max_runtime = self._pending_queue.popleft()
                if command_type in self._command_runners:
                    self._command_runners[command_type](command, max_runtime=max_runtime)
                else:
                    logger.error("Unsupported command type in queue: %s", command_type)
            return

        # Process as many as we can within the limit
        while self._pending_queue and len(self._running_processes) < max_concurrent:
            command_type, command, max_runtime = self._pending_queue.popleft()
            logger.info(
                "Starting queued command: %s (running: %s/%s, queued: %s)",
                command,
                len(self._running_processes) + 1,
                max_concurrent,
                len(self._pending_queue),
            )
            if command_type in self._command_runners:
                self._command_runners[command_type](command, max_runtime=max_runtime)
            else:
                logger.error("Unsupported command type in queue: %s", command_type)

    @staticmethod
    def _process_command(process: subprocess.Popen[bytes]) -> str:
        """Return a human-readable command string for a tracked process."""
        args = process.args
        if args is None:
            return "<unknown>"
        if isinstance(args, str):
            return args
        if isinstance(args, (bytes, bytearray)):
            return args.decode(errors="replace")
        if isinstance(args, Sequence):
            return " ".join(str(part) for part in args)
        return str(args)

    @staticmethod
    def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
        """Hard-kill the process group of a subprocess (SIGKILL).

        Because all subprocesses are spawned with ``start_new_session=True``,
        the child becomes its own session/process-group leader.  Sending
        SIGKILL to the entire group therefore kills the child and all of its
        descendants recursively.

        Args:
            process: The Popen object whose process group should be killed.

        """
        try:
            pgid = os.getpgid(process.pid)
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # Process already gone

    def _terminate_running_processes(self) -> None:
        """Terminate all child processes started by this scheduler."""
        if not self._running_processes:
            return

        logger.info("Terminating %s running process(es)", len(self._running_processes))
        for rp in self._running_processes:
            if rp.process.poll() is not None:
                continue
            command = self._process_command(rp.process)
            logger.info("Terminating process: %s", command)
            try:
                pgid = os.getpgid(rp.process.pid)
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass

        deadline = time.monotonic() + 5.0
        for rp in self._running_processes:
            if rp.process.poll() is not None:
                continue
            remaining = max(0.0, deadline - time.monotonic())
            try:
                rp.process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                command = self._process_command(rp.process)
                logger.warning("Killing process group: %s", command)
                self._kill_process_group(rp.process)
                rp.process.wait()

        self._running_processes.clear()

    def _run_system_command(self, command: str, max_runtime: int | None = None) -> None:
        """Start a system command in a background subprocess.

        Commands run in parallel; the scheduler does not wait for completion
        before running other scheduled tasks.  Each subprocess is started in
        its own session (``start_new_session=True``) so that the entire
        process group can be killed together when ``max_runtime`` is enforced.

        Args:
            command: The command to execute.
            max_runtime: Maximum runtime in seconds before the process group
                is hard-killed (SIGKILL).  None means no limit.

        """
        max_concurrent = self.config.max_concurrent
        if max_concurrent is not None and len(self._running_processes) >= max_concurrent:
            logger.info(
                "Throttling: queuing command '%s' (running: %s/%s, queued: %s)",
                command,
                len(self._running_processes),
                max_concurrent,
                len(self._pending_queue) + 1,
            )
            self._pending_queue.append(("system", command, max_runtime))
            return

        logger.info("Starting system command: %s", command)
        try:
            args = shlex.split(command)
        except ValueError as e:
            logger.error("Invalid command syntax (could not parse): %s. Error: %s", command, e)
            return

        try:
            if self.config.capture_output:
                process = subprocess.Popen(  # noqa: S603
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                )
            else:
                process = subprocess.Popen(  # noqa: S603
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
        except FileNotFoundError as e:
            logger.error("Command not found: %s. Error: %s", command, e)
            return

        self._running_processes.append(
            RunningProcess(
                process=process,
                start_time=time.monotonic(),
                max_runtime=max_runtime,
            )
        )

    def _calculate_actual_time(self, time_str: str, delay_seconds: int) -> str:
        """Calculate the actual start time including the random delay.

        Args:
            time_str: The base time in HH:MM format (as stored by ScheduleEntry).
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
        """Calculate the next run date and time for display purposes.

        Args:
            target_time_str: The target execution time in HH:MM:SS format.
            now: Optional current datetime (for testing).

        Returns:
            The next execution datetime as a string in YYYY-MM-DD HH:MM:SS format.

        """
        target_dt = _parse_time_to_next_run(target_time_str, now)
        return target_dt.strftime("%Y-%m-%d %H:%M:%S")

    def _schedule_command(
        self,
        command_type: str,
        command: str,
        time_str: str,
        delay: int = 0,
        repetitions: int = 0,
        interval: int = -1,
        max_runtime: int | None = None,
        variables: dict[str, list[str | int | float]] | None = None,
        variables_env: dict[str, str] | None = None,
    ) -> None:
        """Schedule a single command.

        Args:
            command_type: The type of command (e.g., "system").
            command: The command to execute.
            time_str: The time to run the command in 24h format (e.g., "14:10").
            delay: Optional base delay in seconds.
            repetitions: Number of times to repeat the command (0 means no repetition).
                Deprecated: use variables instead.
            interval: Time in seconds between repetitions
                (only used when repetitions > 0 or variables is set). If -1 and
                repetitions > 0 or variables is set, the interval is auto-calculated
                to spread runs evenly throughout the day.
            max_runtime: Maximum runtime in seconds before the process group is
                hard-killed (SIGKILL).  None means no limit.
            variables: Variable mappings for pattern expansion. If provided, the command
                will be expanded for each combination of variable values.
            variables_env: Variable mappings from environment variables. Maps variable
                names to environment variable names. The environment variable values
                are JSON-formatted strings containing lists of values.

        Raises:
            ValueError: If the command type is not registered in the instance registry.

        """
        if command_type not in self._command_runners:
            supported_types_str = ", ".join(sorted(self._command_runners.keys()))
            raise ValueError(
                f"Unsupported command type: {command_type}. Supported types: {supported_types_str}"
            )

        runner = self._command_runners[command_type]

        # Merge variables and variables_env
        merged_variables: dict[str, list[str | int | float]] = {}
        if variables is not None:
            merged_variables.update(variables)
        if variables_env is not None:
            for var_name, env_var_name in variables_env.items():
                env_value = os.environ.get(env_var_name)
                if env_value is not None:
                    try:
                        parsed_value = json.loads(env_value)
                        if isinstance(parsed_value, list):
                            merged_variables[var_name] = parsed_value
                    except (json.JSONDecodeError, ValueError):
                        # Validation should have caught this, but handle gracefully
                        logger.warning(
                            "Failed to parse environment variable '%s' for variable '%s'",
                            env_var_name,
                            var_name,
                        )

        # Handle variable expansion
        if merged_variables:
            # Expand command using merged variables
            expanded_commands = _expand_variables(command, merged_variables)
            num_executions = len(expanded_commands)

            # Auto-calculate interval if negative
            if interval < 0:
                times_per_day = abs(interval)
                # Each variable combination runs times_per_day times per day
                # Total executions = num_executions * times_per_day
                # Interval = 24 hours / total_executions
                total_executions = num_executions * times_per_day
                interval = (24 * 3600) // total_executions
                logger.info(
                    "Auto-calculated interval: %ss to spread %s variable combinations "
                    "evenly %s times per day (%s total executions)",
                    interval,
                    num_executions,
                    times_per_day,
                    total_executions,
                )
            else:
                # Positive interval: run each combination once with specified interval
                times_per_day = 1

            # Schedule each variable combination times_per_day times
            for run_num in range(times_per_day):
                for i, (expanded_command, var_mapping) in enumerate(expanded_commands):
                    # Recalculate delay for each execution
                    if delay > 0:
                        actual_delay = max(
                            0,
                            int(random.gauss(mu=delay, sigma=DELAY_SIGMA_MULTIPLIER * delay)),
                        )
                    else:
                        actual_delay = 0

                    # Calculate the base time for this execution
                    # Global execution index across all runs
                    global_index = run_num * num_executions + i
                    if global_index == 0:
                        base_time_str = time_str
                    else:
                        # Add interval to the base time
                        parts = time_str.split(":")
                        hours = int(parts[0])
                        minutes = int(parts[1])
                        total_seconds = hours * 3600 + minutes * 60 + (global_index * interval)
                        total_seconds = total_seconds % (24 * 3600)
                        h = total_seconds // 3600
                        m = (total_seconds % 3600) // 60
                        base_time_str = f"{h:02d}:{m:02d}"

                    # Calculate actual time with delay
                    actual_time = self._calculate_actual_time(base_time_str, actual_delay)

                    self._job_registry.schedule_daily(
                        runner, actual_time, expanded_command, max_runtime=max_runtime
                    )
                    self.scheduled_commands.append(
                        ScheduledCommand(
                            command_type,
                            expanded_command,
                            actual_time,
                            actual_delay,
                            max_runtime,
                        )
                    )
                    logger.info(
                        "Scheduled %s command '%s' (execution %s/%s, run %s/%s, vars: %s) at %s "
                        "with calculated delay %ss",
                        command_type,
                        expanded_command,
                        i + 1,
                        num_executions,
                        run_num + 1,
                        times_per_day,
                        var_mapping,
                        actual_time,
                        actual_delay,
                    )
        else:
            # Use existing repetitions logic for backward compatibility
            # Auto-calculate interval if negative and repetitions > 0
            if interval < 0 and repetitions > 0:
                times_per_day = abs(interval)
                num_executions = 1 + repetitions
                interval = (24 * 3600) // (times_per_day * num_executions)
                logger.info(
                    "Auto-calculated interval: %ss to spread %s executions "
                    "evenly %s times per day",
                    interval,
                    num_executions,
                    times_per_day,
                )

            # Calculate the number of executions (1 + repetitions)
            num_executions = 1 + repetitions

            for i in range(num_executions):
                # Recalculate delay for each repetition
                if delay > 0:
                    actual_delay = max(
                        0,
                        int(random.gauss(mu=delay, sigma=DELAY_SIGMA_MULTIPLIER * delay)),
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

                # Calculate actual time with delay
                actual_time = self._calculate_actual_time(base_time_str, actual_delay)

                self._job_registry.schedule_daily(
                    runner, actual_time, command, max_runtime=max_runtime
                )
                self.scheduled_commands.append(
                    ScheduledCommand(command_type, command, actual_time, actual_delay, max_runtime)
                )
                logger.info(
                    "Scheduled %s command '%s' (execution %s/%s) at %s with calculated delay %ss",
                    command_type,
                    command,
                    i + 1,
                    num_executions,
                    actual_time,
                    actual_delay,
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
        scheduled commands. Progress logging is deferred until all files
        are successfully validated to avoid misleading partial state on failure.
        """
        yaml_paths = self.config.yaml_paths

        # Phase 1: Load and validate all YAML files (no progress logging yet)
        all_entries: list[ScheduleEntry] = []
        seen_entries: set[
            tuple[
                str,
                str,
                str,
                int,
                int,
                int,
                int | None,
                tuple | None,
                tuple | None,
            ]
        ] = set()
        loaded_files: list[Path] = []
        duplicate_warnings: list[tuple[Path, ScheduleEntry]] = []
        allowed_duplicates: list[tuple[Path, ScheduleEntry]] = []

        for yaml_path in yaml_paths:
            try:
                with open(yaml_path, encoding="utf-8") as yamlfile:
                    data = yaml.safe_load(yamlfile)
                    if not data or "schedules" not in data:
                        error_msg = f"Invalid YAML format in {yaml_path}: missing 'schedules' key"
                        raise ValueError(error_msg)

                    schedules = data["schedules"]
                    if not isinstance(schedules, list):
                        error_msg = (
                            f"Invalid YAML format in {yaml_path}: "
                            f"'schedules' must be a list, "
                            f"got {type(schedules).__name__}"
                        )
                        raise ValueError(error_msg)

                    for entry_data in schedules:
                        if not isinstance(entry_data, dict):
                            error_msg = (
                                f"Invalid entry in {yaml_path}: expected dict, "
                                f"got {type(entry_data).__name__}: {entry_data}"
                            )
                            raise ValueError(error_msg)
                        entry = ScheduleEntry.model_validate(
                            entry_data,
                            context={"registry": self._command_runners},
                        )
                        # Convert variables to a hashable format for duplicate detection
                        variables_hashable = None
                        if entry.variables:
                            variables_hashable = tuple(
                                (k, tuple(v) if isinstance(v, list) else v)
                                for k, v in sorted(entry.variables.items())
                            )
                        # Convert variables_env to a hashable format
                        # for duplicate detection
                        variables_env_hashable = None
                        if entry.variables_env:
                            variables_env_hashable = tuple(
                                (k, v) for k, v in sorted(entry.variables_env.items())
                            )
                        entry_key = (
                            entry.type,
                            entry.command,
                            entry.time,
                            entry.delay,
                            entry.repetitions,
                            entry.interval,
                            entry.max_runtime,
                            variables_hashable,
                            variables_env_hashable,
                        )
                        if entry_key in seen_entries:
                            if self.config.allow_duplicates:
                                all_entries.append(entry)
                                # Defer logging until after validation succeeds
                                allowed_duplicates.append((yaml_path, entry))
                            else:
                                # Defer warning logging until after validation succeeds
                                duplicate_warnings.append((yaml_path, entry))
                        else:
                            seen_entries.add(entry_key)
                            all_entries.append(entry)
                    loaded_files.append(yaml_path)
            except FileNotFoundError:
                error_msg = f"YAML file not found: {yaml_path}"
                logger.error("%s", error_msg)
                raise
            except PermissionError:
                error_msg = f"Permission denied reading YAML file: {yaml_path}"
                logger.error("%s", error_msg)
                raise
            except yaml.YAMLError as e:
                error_msg = f"YAML parsing error in {yaml_path}: {e}"
                logger.error("%s", error_msg)
                raise
            except (KeyError, ValueError, ValidationError) as e:
                error_msg = f"Invalid entry in {yaml_path}: {e}"
                logger.error("%s", error_msg)
                raise

        # All files validated successfully - now log progress
        logger.info("Loading schedule from %s YAML file(s)", len(loaded_files))
        for yaml_path in loaded_files:
            logger.info("Loading schedule from %s", yaml_path)

        # Log allowed duplicates (deferred from validation phase)
        for yaml_path, entry in allowed_duplicates:
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

        # Log duplicate warnings (deferred from validation phase)
        for yaml_path, entry in duplicate_warnings:
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

        # Phase 2: Clear and schedule all validated entries
        self._job_registry.clear()
        self.scheduled_commands.clear()

        for entry in all_entries:
            self._schedule_command(
                entry.type,
                entry.command,
                entry.time,
                delay=entry.delay,
                repetitions=entry.repetitions,
                interval=entry.interval,
                max_runtime=entry.max_runtime,
                variables=entry.variables,
                variables_env=entry.variables_env,
            )

        # Log all scheduled commands
        logger.info("Scheduled commands:")
        for cmd in self.scheduled_commands:
            next_run = self._calculate_next_run(cmd.time)
            max_rt_str = f"{cmd.max_runtime}s" if cmd.max_runtime is not None else "none"
            logger.info(
                "%s • %s • %s • delay: %ss • max_runtime: %s",
                cmd.command_type,
                cmd.command,
                next_run,
                cmd.delay,
                max_rt_str,
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
                self._job_registry.run_pending()
                self._reap_finished_processes()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
        finally:
            self._terminate_running_processes()
