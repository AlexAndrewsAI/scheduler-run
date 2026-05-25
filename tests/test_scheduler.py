"""Tests for the scheduler module."""

import datetime
import logging
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
import yaml
from pydantic import ValidationError

from scheduler_run.config import COMMAND_RUNNERS, Config
from scheduler_run.scheduler import Scheduler


def test_scheduler_init_default_config() -> None:
    """Test Scheduler initialization with default config."""
    scheduler = Scheduler()
    assert scheduler.config.yaml_path == [Path("schedule.yaml")]


def test_scheduler_init_custom_config() -> None:
    """Test Scheduler initialization with custom config."""
    custom_path = Path("custom/schedule.yaml")
    config = Config(yaml_path=custom_path)
    scheduler = Scheduler(config)
    assert scheduler.config.yaml_path == [custom_path]


def test_scheduler_registers_system_runner() -> None:
    """Test Scheduler registers the system command runner on initialization."""
    # Save original system runner
    original_system = COMMAND_RUNNERS.get("system")
    
    COMMAND_RUNNERS.clear()
    assert "system" not in COMMAND_RUNNERS

    scheduler = Scheduler()
    assert "system" in COMMAND_RUNNERS
    assert COMMAND_RUNNERS["system"] == scheduler._run_system_command
    
    # Restore original system runner
    if original_system is not None:
        COMMAND_RUNNERS["system"] = original_system


def test_run_system_command_success(caplog: pytest.LogCaptureFixture) -> None:
    """Test _run_system_command starts a background subprocess with capture_output=True."""
    scheduler = Scheduler()
    caplog.set_level(logging.INFO)

    mock_process = MagicMock(spec=subprocess.Popen)
    with patch("scheduler_run.scheduler.subprocess.Popen") as mock_popen:
        mock_popen.return_value = mock_process
        scheduler._run_system_command("echo 'test'")
        mock_popen.assert_called_once_with(
            ["echo", "test"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert scheduler._running_processes == [mock_process]
        assert "Starting system command: echo 'test'" in caplog.text


def test_run_system_command_capture_output_false(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test _run_system_command with capture_output=False discards output."""
    config = Config(capture_output=False)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    mock_process = MagicMock(spec=subprocess.Popen)
    with patch("scheduler_run.scheduler.subprocess.Popen") as mock_popen:
        mock_popen.return_value = mock_process
        scheduler._run_system_command("echo 'test'")
        mock_popen.assert_called_once_with(
            ["echo", "test"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        assert scheduler._running_processes == [mock_process]
        assert "Starting system command: echo 'test'" in caplog.text


def test_reap_finished_processes_success(caplog: pytest.LogCaptureFixture) -> None:
    """Test _reap_finished_processes logs success for exit code 0."""
    scheduler = Scheduler()
    caplog.set_level(logging.INFO)

    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.poll.return_value = 0
    mock_process.args = ["echo", "test"]
    scheduler._running_processes = [mock_process]

    scheduler._reap_finished_processes()

    assert scheduler._running_processes == []
    assert "Command completed: echo test (exit 0)" in caplog.text


def test_reap_finished_processes_failure(caplog: pytest.LogCaptureFixture) -> None:
    """Test _reap_finished_processes logs failure for non-zero exit with captured output."""
    scheduler = Scheduler()
    caplog.set_level(logging.WARNING)

    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.poll.return_value = 1
    mock_process.args = ["false"]
    mock_process.communicate.return_value = (b"stdout output", b"stderr output")
    scheduler._running_processes = [mock_process]

    scheduler._reap_finished_processes()

    assert scheduler._running_processes == []
    assert "Command failed: false (exit 1)" in caplog.text
    assert "stdout: stdout output" in caplog.text
    assert "stderr: stderr output" in caplog.text
    assert "Check the logs above for output details" in caplog.text


def test_reap_finished_processes_failure_no_capture(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test _reap_finished_processes logs failure without captured output when disabled."""
    config = Config(capture_output=False)
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.poll.return_value = 1
    mock_process.args = ["false"]
    scheduler._running_processes = [mock_process]

    scheduler._reap_finished_processes()

    assert scheduler._running_processes == []
    assert "Command failed: false (exit 1)" in caplog.text
    assert "stdout:" not in caplog.text
    assert "stderr:" not in caplog.text
    assert "Check the logs above for output details" not in caplog.text


def test_reap_finished_processes_keeps_running() -> None:
    """Test _reap_finished_processes keeps processes that are still running."""
    scheduler = Scheduler()

    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.poll.return_value = None
    scheduler._running_processes = [mock_process]

    scheduler._reap_finished_processes()

    assert scheduler._running_processes == [mock_process]


def test_run_system_command_not_found(caplog: pytest.LogCaptureFixture) -> None:
    """Test _run_system_command when the executable is not found."""
    scheduler = Scheduler()
    caplog.set_level(logging.ERROR)

    with patch("scheduler_run.scheduler.subprocess.Popen") as mock_popen:
        mock_popen.side_effect = FileNotFoundError("No such file")
        scheduler._run_system_command("nonexistent-cmd-xyz")
        assert scheduler._running_processes == []
        assert "Command not found: nonexistent-cmd-xyz" in caplog.text


def test_terminate_running_processes(caplog: pytest.LogCaptureFixture) -> None:
    """Test _terminate_running_processes terminates active children."""
    scheduler = Scheduler()
    caplog.set_level(logging.INFO)

    running = MagicMock(spec=subprocess.Popen)
    running.poll.return_value = None
    running.args = ["sleep", "60"]
    finished = MagicMock(spec=subprocess.Popen)
    finished.poll.return_value = 0
    finished.args = ["true"]
    scheduler._running_processes = [running, finished]

    scheduler._terminate_running_processes()

    running.terminate.assert_called_once()
    finished.terminate.assert_not_called()
    running.wait.assert_called()
    assert scheduler._running_processes == []
    assert "Terminating 2 running process(es)" in caplog.text
    assert "Terminating process: sleep 60" in caplog.text


def test_terminate_running_processes_kills_on_timeout(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test _terminate_running_processes kills children that ignore SIGTERM."""
    scheduler = Scheduler()
    caplog.set_level(logging.WARNING)

    stubborn = MagicMock(spec=subprocess.Popen)
    stubborn.poll.return_value = None
    stubborn.args = ["sleep", "60"]
    stubborn.wait.side_effect = [subprocess.TimeoutExpired("sleep", 5), None]
    scheduler._running_processes = [stubborn]

    scheduler._terminate_running_processes()

    stubborn.kill.assert_called_once()
    assert "Killing process: sleep 60" in caplog.text


def test_schedule_command_system_type(caplog: pytest.LogCaptureFixture) -> None:
    """Test _schedule_command with system type."""
    scheduler = Scheduler()
    caplog.set_level(logging.INFO)

    scheduler._schedule_command("system", "echo 'test'", "14:30")

    # Verify the job was registered
    assert len(scheduler._job_registry.get_jobs()) == 1
    job = scheduler._job_registry.get_jobs()[0]
    assert job.target_time_str == "14:30:00"
    assert (
        "Scheduled system command 'echo 'test'' (execution 1/1) "
        "at 14:30:00 with calculated delay 0s" in caplog.text
    )


def test_schedule_command_unsupported_type() -> None:
    """Test _schedule_command with unsupported command type."""
    scheduler = Scheduler()

    with pytest.raises(ValueError, match="Unsupported command type: unsupported"):
        scheduler._schedule_command("unsupported", "echo 'test'", "14:30")


def test_load_schedule_success(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with a valid YAML file."""
    yaml_file = tmp_path / "test_schedule.yaml"
    yaml_file.write_text(
        "schedules:\n  - type: system\n    command: echo 'hello'\n    time: '14:10'\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    scheduler.load_schedule()

    assert f"Loading schedule from {yaml_file}" in caplog.text
    # Verify the job was registered
    assert len(scheduler._job_registry.get_jobs()) == 1


@pytest.mark.parametrize(
    "yaml_content",
    [
        "",
        "other_key: value\n",
    ],
    ids=["empty_file", "missing_schedules_key"],
)
def test_load_schedule_missing_schedules_key(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    yaml_content: str,
) -> None:
    """Test load_schedule when YAML has no schedules key."""
    yaml_file = tmp_path / "no_schedules.yaml"
    yaml_file.write_text(yaml_content)

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    with pytest.raises(ValueError, match="missing 'schedules' key"):
        scheduler.load_schedule()

    assert "Invalid YAML format" in caplog.text
    assert len(scheduler._job_registry.get_jobs()) == 0
    assert len(scheduler.scheduled_commands) == 0


def test_load_schedule_permission_denied(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule when the YAML file cannot be read."""
    yaml_file = tmp_path / "protected.yaml"
    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    with (
        patch(
            "builtins.open",
            mock_open(read_data="schedules: []\n"),
        ) as mock_file,
    ):
        mock_file.side_effect = PermissionError("Permission denied")

        with pytest.raises(PermissionError):
            scheduler.load_schedule()

        assert f"Permission denied reading YAML file: {yaml_file}" in caplog.text
        assert len(scheduler._job_registry.get_jobs()) == 0
        assert len(scheduler.scheduled_commands) == 0


def test_load_schedule_yaml_parse_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule when YAML parsing fails."""
    yaml_file = tmp_path / "broken.yaml"
    yaml_file.write_text("schedules:\n  - type: [\n")

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    with pytest.raises(yaml.YAMLError):
        scheduler.load_schedule()

    assert f"YAML parsing error in {yaml_file}" in caplog.text
    assert len(scheduler._job_registry.get_jobs()) == 0
    assert len(scheduler.scheduled_commands) == 0


def test_load_schedule_file_not_found(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with a non-existent YAML file."""
    non_existent = tmp_path / "non_existent.yaml"
    config = Config(yaml_path=non_existent)  # type: ignore[arg-type]
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    with pytest.raises(FileNotFoundError):
        scheduler.load_schedule()

    assert f"YAML file not found: {non_existent}" in caplog.text


def test_load_schedule_invalid_entry(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with invalid YAML entries raises ValidationError."""
    yaml_file = tmp_path / "invalid_schedule.yaml"
    yaml_file.write_text(
        "schedules:\n"
        "  - type: system\n"
        "    command: echo 'hello'\n"
        "    time: ''\n"
        "  - type: ''\n"
        "    command: echo test\n"
        "    time: '14:10'\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    with pytest.raises(ValidationError):
        scheduler.load_schedule()

    assert "Invalid entry" in caplog.text
    assert len(scheduler._job_registry.get_jobs()) == 0


def test_load_schedule_duplicate_entries(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with duplicate entries (all fields identical)."""
    yaml_file = tmp_path / "duplicate_schedule.yaml"
    yaml_file.write_text(
        "schedules:\n"
        "  - type: system\n"
        "    command: echo 'hello'\n"
        "    time: '14:10'\n"
        "    delay: 0\n"
        "    repetitions: 0\n"
        "    interval: -1\n"
        "  - type: system\n"
        "    command: echo 'hello'\n"
        "    time: '14:10'\n"
        "    delay: 0\n"
        "    repetitions: 0\n"
        "    interval: -1\n"
        "  - type: system\n"
        "    command: echo 'goodbye'\n"
        "    time: '15:00'\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.WARNING)

    scheduler.load_schedule()

    assert "Duplicate entry detected" in caplog.text
    assert (
        "type='system', command='echo 'hello'', time='14:10', delay=0, "
        "repetitions=0, interval=-1" in caplog.text
    )
    # Verify only unique entries were scheduled (2 unique entries)
    assert len(scheduler._job_registry.get_jobs()) == 2


def test_scheduler_run(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Test Scheduler.run() method."""
    yaml_file = tmp_path / "test_schedule.yaml"
    yaml_file.write_text(
        "schedules:\n  - type: system\n    command: echo 'test'\n    time: '14:30'\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    with (
        patch("scheduler_run.scheduler.time.sleep") as mock_sleep,
        patch.object(scheduler, "_terminate_running_processes") as mock_terminate,
        patch.object(scheduler, "_reap_finished_processes"),
    ):
        # Make sleep raise KeyboardInterrupt to exit the loop
        mock_sleep.side_effect = KeyboardInterrupt()

        scheduler.run()

        assert "Loading schedule from" in caplog.text
        assert "Scheduler started" in caplog.text
        assert "Scheduler stopped by user" in caplog.text
        mock_terminate.assert_called_once()


def test_load_schedule_empty_list(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with an empty schedules list."""
    yaml_file = tmp_path / "empty_schedule.yaml"
    yaml_file.write_text("schedules: []\n")

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    scheduler.load_schedule()

    assert "Loading schedule from" in caplog.text
    assert "Scheduled commands:" in caplog.text
    assert len(scheduler.scheduled_commands) == 0


def test_load_schedule_missing_type_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with entry missing 'type' key raises ValidationError."""
    yaml_file = tmp_path / "missing_type.yaml"
    yaml_file.write_text("schedules:\n  - command: echo 'test'\n    time: '14:30'\n")

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    with pytest.raises(ValidationError):
        scheduler.load_schedule()

    assert "Invalid entry" in caplog.text


def test_load_schedule_missing_command_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with entry missing 'command' key raises ValidationError."""
    yaml_file = tmp_path / "missing_command.yaml"
    yaml_file.write_text("schedules:\n  - type: system\n    time: '14:30'\n")

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    with pytest.raises(ValidationError):
        scheduler.load_schedule()

    assert "Invalid entry" in caplog.text


def test_load_schedule_missing_time_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with entry missing 'time' key raises ValidationError."""
    yaml_file = tmp_path / "missing_time.yaml"
    yaml_file.write_text("schedules:\n  - type: system\n    command: echo 'test'\n")

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    with pytest.raises(ValidationError):
        scheduler.load_schedule()

    assert "Invalid entry" in caplog.text


def test_load_schedule_unsupported_type(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with unsupported type raises ValidationError."""
    yaml_file = tmp_path / "unsupported_type.yaml"
    yaml_file.write_text(
        "schedules:\n  - type: systm\n    command: echo 'test'\n    time: '14:30'\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    with pytest.raises(ValidationError, match="Unsupported command type"):
        scheduler.load_schedule()

    assert "Invalid entry" in caplog.text


def test_schedule_command_with_delay(caplog: pytest.LogCaptureFixture) -> None:
    """Test _schedule_command with configured delay."""
    scheduler = Scheduler()
    caplog.set_level(logging.INFO)

    with patch("scheduler_run.scheduler.random.gauss") as mock_gauss:
        mock_gauss.return_value = 12.3

        scheduler._schedule_command("system", "echo 'test'", "14:30", delay=10)

        mock_gauss.assert_called_once_with(mu=10, sigma=1.5)
        # 14:30 + 12 seconds = 14:30:12
        assert len(scheduler.scheduled_commands) == 1
        assert scheduler.scheduled_commands[0].command_type == "system"
        assert scheduler.scheduled_commands[0].command == "echo 'test'"
        assert scheduler.scheduled_commands[0].time == "14:30:12"
        assert scheduler.scheduled_commands[0].delay == 12
        expected_msg = (
            "Scheduled system command 'echo 'test'' (execution 1/1) "
            "at 14:30:12 with calculated delay 12s"
        )
        assert expected_msg in caplog.text
        # Verify the job was registered
        assert len(scheduler._job_registry.get_jobs()) == 1
        job = scheduler._job_registry.get_jobs()[0]
        assert job.target_time_str == "14:30:12"


def test_load_schedule_with_delay(tmp_path: Path) -> None:
    """Test load_schedule with an entry that includes a delay."""
    yaml_file = tmp_path / "delay_schedule.yaml"
    yaml_file.write_text(
        "schedules:\n"
        "  - type: system\n"
        "    command: echo 'hello'\n"
        "    time: '14:10'\n"
        "    delay: 45\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)

    with patch("scheduler_run.scheduler.random.gauss") as mock_gauss:
        mock_gauss.return_value = 45.0

        scheduler.load_schedule()

        assert len(scheduler.scheduled_commands) == 1
        assert scheduler.scheduled_commands[0].command_type == "system"
        assert scheduler.scheduled_commands[0].command == "echo 'hello'"
        assert scheduler.scheduled_commands[0].time == "14:10:45"
        assert scheduler.scheduled_commands[0].delay == 45
        # Verify the job was registered
        assert len(scheduler._job_registry.get_jobs()) == 1


def test_calculate_actual_time() -> None:
    """Test _calculate_actual_time method of Scheduler."""
    scheduler = Scheduler()
    # Simple cases
    assert scheduler._calculate_actual_time("14:10", 10) == "14:10:10"
    assert scheduler._calculate_actual_time("08:00", 0) == "08:00:00"
    # Rollover minute
    assert scheduler._calculate_actual_time("14:10", 75) == "14:11:15"
    # Rollover day
    assert scheduler._calculate_actual_time("23:59", 75) == "00:00:15"


def test_calculate_next_run() -> None:
    """Test _calculate_next_run method of Scheduler."""
    scheduler = Scheduler()
    now = datetime.datetime(2026, 5, 22, 11, 58, 55)

    # 1. Target time is later today
    assert scheduler._calculate_next_run("14:10:00", now=now) == "2026-05-22 14:10:00"

    # 2. Target time is earlier today (already passed)
    assert scheduler._calculate_next_run("08:00:00", now=now) == "2026-05-23 08:00:00"

    # 3. Target time is exactly now
    assert scheduler._calculate_next_run("11:58:55", now=now) == "2026-05-23 11:58:55"

    # 4. Target time in HH:MM format
    assert scheduler._calculate_next_run("14:10", now=now) == "2026-05-22 14:10:00"
    assert scheduler._calculate_next_run("08:00", now=now) == "2026-05-23 08:00:00"


def test_load_schedule_logging(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test logging output in load_schedule with mock datetime."""
    yaml_file = tmp_path / "logging_schedule.yaml"
    yaml_file.write_text(
        "schedules:\n"
        "  - type: system\n"
        "    command: echo 'hello world'\n"
        "    time: '14:10'\n"
        "    delay: 10\n"
        "  - type: system\n"
        "    command: echo 'good morning'\n"
        "    time: '08:00'\n"
        "    delay: 0\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    fake_now = datetime.datetime(2026, 5, 22, 11, 58, 55)

    with (
        patch("scheduler_run.scheduler.random.gauss") as mock_gauss,
        patch("scheduler_run.scheduler.datetime.datetime") as mock_dt,
    ):
        # We need mock_gauss to return 10 for the first
        mock_gauss.return_value = 10.0

        # Mock datetime.now() to return fake_now
        mock_dt.now.return_value = fake_now

        scheduler.load_schedule()

        # Inspect the logs
        log_text = caplog.text
        assert "Scheduled commands:" in log_text
        assert (
            "system • echo 'hello world' • 2026-05-22 14:10:10 • delay: 10s" in log_text
        )
        assert (
            "system • echo 'good morning' • 2026-05-23 08:00:00 • delay: 0s" in log_text
        )


def test_schedule_command_with_repetitions(caplog: pytest.LogCaptureFixture) -> None:
    """Test _schedule_command with repetitions."""
    scheduler = Scheduler()
    caplog.set_level(logging.INFO)

    with patch("scheduler_run.scheduler.random.gauss") as mock_gauss:
        # Return different delays for each repetition
        mock_gauss.side_effect = [5.0, 10.0, 15.0]

        scheduler._schedule_command(
            "system", "echo 'test'", "14:30", delay=10, repetitions=2, interval=60
        )

        # Should schedule 3 times (1 + 2 repetitions)
        assert len(scheduler.scheduled_commands) == 3
        assert len(scheduler._job_registry.get_jobs()) == 3

        # Verify each execution was logged
        assert "(execution 1/3)" in caplog.text
        assert "(execution 2/3)" in caplog.text
        assert "(execution 3/3)" in caplog.text

        # Verify gauss was called 3 times (delay recalculated for each repetition)
        assert mock_gauss.call_count == 3


def test_schedule_command_no_repetitions(caplog: pytest.LogCaptureFixture) -> None:
    """Test _schedule_command with repetitions=0 (default behavior)."""
    scheduler = Scheduler()
    caplog.set_level(logging.INFO)

    scheduler._schedule_command("system", "echo 'test'", "14:30", repetitions=0)

    # Should schedule only once
    assert len(scheduler.scheduled_commands) == 1
    assert len(scheduler._job_registry.get_jobs()) == 1


def test_load_schedule_with_repetitions(tmp_path: Path) -> None:
    """Test load_schedule with an entry that includes repetitions."""
    yaml_file = tmp_path / "repetition_schedule.yaml"
    yaml_file.write_text(
        "schedules:\n"
        "  - type: system\n"
        "    command: echo 'hello'\n"
        "    time: '14:10'\n"
        "    delay: 10\n"
        "    repetitions: 2\n"
        "    interval: 60\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)

    with patch("scheduler_run.scheduler.random.gauss") as mock_gauss:
        mock_gauss.side_effect = [10.0, 15.0, 20.0]

        scheduler.load_schedule()

        # Should schedule 3 times (1 + 2 repetitions)
        assert len(scheduler.scheduled_commands) == 3
        assert len(scheduler._job_registry.get_jobs()) == 3


def test_load_schedule_with_repetitions_no_interval(tmp_path: Path) -> None:
    """Test load_schedule with repetitions but default interval."""
    yaml_file = tmp_path / "repetition_no_interval.yaml"
    yaml_file.write_text(
        "schedules:\n"
        "  - type: system\n"
        "    command: echo 'hello'\n"
        "    time: '14:10'\n"
        "    repetitions: 1\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)

    scheduler.load_schedule()

    # Should schedule 2 times (1 + 1 repetition)
    assert len(scheduler.scheduled_commands) == 2
    assert len(scheduler._job_registry.get_jobs()) == 2


def test_schedule_command_auto_calculate_interval(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test _schedule_command with auto-calculated interval."""
    scheduler = Scheduler()
    caplog.set_level(logging.INFO)

    # repetitions=3 should auto-calculate interval to
    # 24*3600/4 = 21600 seconds (6 hours)
    scheduler._schedule_command(
        "system", "echo 'test'", "00:00", repetitions=3, interval=-1
    )

    # Should schedule 4 times (1 + 3 repetitions)
    assert len(scheduler.scheduled_commands) == 4
    assert len(scheduler._job_registry.get_jobs()) == 4

    # Verify auto-calculation was logged
    assert "Auto-calculated interval: 21600s" in caplog.text
    assert "spread 4 executions evenly throughout the day" in caplog.text

    # Verify the scheduled times are spaced 6 hours apart
    # 00:00, 06:00, 12:00, 18:00
    scheduled_times = [cmd.time for cmd in scheduler.scheduled_commands]
    assert "00:00:00" in scheduled_times
    assert "06:00:00" in scheduled_times
    assert "12:00:00" in scheduled_times
    assert "18:00:00" in scheduled_times


def test_schedule_command_auto_calculate_interval_with_delay(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test _schedule_command with auto-calculated interval and delay."""
    scheduler = Scheduler()
    caplog.set_level(logging.INFO)

    with patch("scheduler_run.scheduler.random.gauss") as mock_gauss:
        # Return same delay for all executions
        mock_gauss.return_value = 30.0

        # repetitions=1 should auto-calculate interval to
        # 24*3600/2 = 43200 seconds (12 hours)
        scheduler._schedule_command(
            "system", "echo 'test'", "00:00", delay=10, repetitions=1, interval=-1
        )

        # Should schedule 2 times (1 + 1 repetition)
        assert len(scheduler.scheduled_commands) == 2
        assert len(scheduler._job_registry.get_jobs()) == 2

        # Verify auto-calculation was logged
        assert "Auto-calculated interval: 43200s" in caplog.text

        # Verify the scheduled times include the delay
        # 00:00:30, 12:00:30
        scheduled_times = [cmd.time for cmd in scheduler.scheduled_commands]
        assert "00:00:30" in scheduled_times
        assert "12:00:30" in scheduled_times


def test_load_schedule_with_auto_calculated_interval(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with auto-calculated interval."""
    yaml_file = tmp_path / "auto_interval_schedule.yaml"
    yaml_file.write_text(
        "schedules:\n"
        "  - type: system\n"
        "    command: echo 'hello'\n"
        "    time: '00:00'\n"
        "    repetitions: 3\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    scheduler.load_schedule()

    # Should schedule 4 times (1 + 3 repetitions)
    assert len(scheduler.scheduled_commands) == 4
    assert len(scheduler._job_registry.get_jobs()) == 4

    # Verify auto-calculation was logged
    assert "Auto-calculated interval: 21600s" in caplog.text


def test_load_schedule_multiple_files(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with multiple YAML files."""
    yaml_file1 = tmp_path / "schedule1.yaml"
    yaml_file1.write_text(
        "schedules:\n  - type: system\n    command: echo 'hello'\n    time: '14:10'\n"
    )
    yaml_file2 = tmp_path / "schedule2.yaml"
    yaml_file2.write_text(
        "schedules:\n  - type: system\n    command: echo 'goodbye'\n    time: '15:00'\n"
    )

    config = Config(yaml_path=[yaml_file1, yaml_file2])
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    scheduler.load_schedule()

    assert "Loading schedule from 2 YAML file(s)" in caplog.text
    assert f"Loading schedule from {yaml_file1}" in caplog.text
    assert f"Loading schedule from {yaml_file2}" in caplog.text
    # Should schedule 2 commands (one from each file)
    assert len(scheduler._job_registry.get_jobs()) == 2
    assert len(scheduler.scheduled_commands) == 2


def test_load_schedule_multiple_files_duplicate_detection(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with duplicate entries across multiple files."""
    yaml_file1 = tmp_path / "schedule1.yaml"
    yaml_file1.write_text(
        "schedules:\n  - type: system\n    command: echo 'hello'\n    "
        "time: '14:10'\n    delay: 0\n    repetitions: 0\n    interval: -1\n"
    )
    yaml_file2 = tmp_path / "schedule2.yaml"
    yaml_file2.write_text(
        "schedules:\n  - type: system\n    command: echo 'hello'\n    "
        "time: '14:10'\n    delay: 0\n    repetitions: 0\n    interval: -1\n"
    )

    config = Config(yaml_path=[yaml_file1, yaml_file2])
    scheduler = Scheduler(config)
    caplog.set_level(logging.WARNING)

    scheduler.load_schedule()

    assert "Duplicate entry detected" in caplog.text
    # Should only schedule 1 unique entry
    assert len(scheduler._job_registry.get_jobs()) == 1
    assert len(scheduler.scheduled_commands) == 1


def test_max_concurrent_queues_when_at_limit(caplog: pytest.LogCaptureFixture) -> None:
    """Test that commands are queued when max_concurrent limit is reached."""
    config = Config(max_concurrent=2)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    mock_process1 = MagicMock(spec=subprocess.Popen)
    mock_process1.poll.return_value = None
    mock_process1.args = ["sleep", "10"]

    mock_process2 = MagicMock(spec=subprocess.Popen)
    mock_process2.poll.return_value = None
    mock_process2.args = ["sleep", "20"]

    with patch("scheduler_run.scheduler.subprocess.Popen") as mock_popen:
        mock_popen.side_effect = [mock_process1, mock_process2]

        # Start 2 commands (at limit)
        scheduler._run_system_command("sleep 10")
        scheduler._run_system_command("sleep 20")

        assert len(scheduler._running_processes) == 2
        assert len(scheduler._pending_queue) == 0

        # Start 3rd command (should be queued)
        scheduler._run_system_command("sleep 30")

        assert len(scheduler._running_processes) == 2
        assert len(scheduler._pending_queue) == 1
        assert "Throttling: queuing command 'sleep 30'" in caplog.text


def test_max_concurrent_processes_queue_on_finish(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that queued commands start when slots become available."""
    config = Config(max_concurrent=2)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    mock_process1 = MagicMock(spec=subprocess.Popen)
    mock_process1.poll.return_value = None
    mock_process1.args = ["sleep", "10"]

    mock_process2 = MagicMock(spec=subprocess.Popen)
    mock_process2.poll.return_value = None
    mock_process2.args = ["sleep", "20"]

    mock_process3 = MagicMock(spec=subprocess.Popen)
    mock_process3.poll.return_value = None
    mock_process3.args = ["sleep", "30"]

    with patch("scheduler_run.scheduler.subprocess.Popen") as mock_popen:
        mock_popen.side_effect = [mock_process1, mock_process2, mock_process3]

        # Start 2 commands (at limit)
        scheduler._run_system_command("sleep 10")
        scheduler._run_system_command("sleep 20")

        # Queue 3rd command
        scheduler._run_system_command("sleep 30")

        assert len(scheduler._running_processes) == 2
        assert len(scheduler._pending_queue) == 1

        # Mark first process as finished
        mock_process1.poll.return_value = 0

        # Reap finished processes (should start queued command)
        scheduler._reap_finished_processes()

        assert len(scheduler._running_processes) == 2
        assert len(scheduler._pending_queue) == 0
        assert "Starting queued command: sleep 30" in caplog.text


def test_max_concurrent_none_unlimited(caplog: pytest.LogCaptureFixture) -> None:
    """Test that max_concurrent=None allows unlimited concurrent processes."""
    config = Config(max_concurrent=None)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    mock_processes = []
    for i in range(5):
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None
        mock_proc.args = ["sleep", str(i)]
        mock_processes.append(mock_proc)

    with patch("scheduler_run.scheduler.subprocess.Popen") as mock_popen:
        mock_popen.side_effect = mock_processes

        # Start 5 commands with no limit
        for i in range(5):
            scheduler._run_system_command(f"sleep {i}")

        assert len(scheduler._running_processes) == 5
        assert len(scheduler._pending_queue) == 0
        assert "Throttling" not in caplog.text


def test_max_concurrent_zero_allows_none(caplog: pytest.LogCaptureFixture) -> None:
    """Test that max_concurrent=0 allows no concurrent processes (all queued)."""
    config = Config(max_concurrent=0)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    # Try to start a command with limit 0
    scheduler._run_system_command("sleep 10")

    assert len(scheduler._running_processes) == 0
    assert len(scheduler._pending_queue) == 1
    assert "Throttling: queuing command 'sleep 10'" in caplog.text


def test_process_pending_queue_no_limit(caplog: pytest.LogCaptureFixture) -> None:
    """Test _process_pending_queue when max_concurrent is None."""
    config = Config(max_concurrent=None)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    # Add commands to queue
    scheduler._pending_queue.append(("system", "echo 'test1'"))
    scheduler._pending_queue.append(("system", "echo 'test2'"))

    mock_process1 = MagicMock(spec=subprocess.Popen)
    mock_process1.poll.return_value = None
    mock_process1.args = ["echo", "test1"]

    mock_process2 = MagicMock(spec=subprocess.Popen)
    mock_process2.poll.return_value = None
    mock_process2.args = ["echo", "test2"]

    with patch("scheduler_run.scheduler.subprocess.Popen") as mock_popen:
        mock_popen.side_effect = [mock_process1, mock_process2]

        scheduler._process_pending_queue()

        assert len(scheduler._pending_queue) == 0
        assert len(scheduler._running_processes) == 2


def test_process_pending_queue_unsupported_type_no_limit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test _process_pending_queue with unsupported command type when no limit."""
    config = Config(max_concurrent=None)
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    # Add unsupported command type to queue
    scheduler._pending_queue.append(("unsupported", "echo 'test'"))

    scheduler._process_pending_queue()

    assert len(scheduler._pending_queue) == 0
    assert len(scheduler._running_processes) == 0
    assert "Unsupported command type in queue: unsupported" in caplog.text


def test_process_pending_queue_unsupported_type_with_limit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test _process_pending_queue with unsupported command type when limit is set."""
    config = Config(max_concurrent=2)
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    # Add unsupported command type to queue
    scheduler._pending_queue.append(("unsupported", "echo 'test'"))

    scheduler._process_pending_queue()

    assert len(scheduler._pending_queue) == 0
    assert len(scheduler._running_processes) == 0
    assert "Unsupported command type in queue: unsupported" in caplog.text


def test_process_pending_queue_with_limit(caplog: pytest.LogCaptureFixture) -> None:
    """Test _process_pending_queue respects max_concurrent limit."""
    config = Config(max_concurrent=2)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    # Start 1 running process
    mock_process1 = MagicMock(spec=subprocess.Popen)
    mock_process1.poll.return_value = None
    mock_process1.args = ["sleep", "10"]
    scheduler._running_processes = [mock_process1]

    # Add 3 commands to queue
    scheduler._pending_queue.append(("system", "echo 'test1'"))
    scheduler._pending_queue.append(("system", "echo 'test2'"))
    scheduler._pending_queue.append(("system", "echo 'test3'"))

    mock_process2 = MagicMock(spec=subprocess.Popen)
    mock_process2.poll.return_value = None
    mock_process2.args = ["echo", "test1"]

    with patch("scheduler_run.scheduler.subprocess.Popen") as mock_popen:
        mock_popen.return_value = mock_process2

        scheduler._process_pending_queue()

        # Should start 1 more (total 2 at limit), leaving 2 queued
        # The second command gets re-queued because _run_system_command checks limit
        assert len(scheduler._running_processes) == 2
        assert len(scheduler._pending_queue) == 2
        assert "Starting queued command: echo 'test1'" in caplog.text


def test_max_concurrent_config_default() -> None:
    """Test that max_concurrent defaults to 5."""
    config = Config()
    assert config.max_concurrent == 5


def test_scheduler_init_with_max_concurrent() -> None:
    """Test Scheduler initialization with max_concurrent config."""
    config = Config(max_concurrent=5)
    scheduler = Scheduler(config)
    assert scheduler.config.max_concurrent == 5


def test_load_schedule_allow_duplicates(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with allow_duplicates=True."""
    yaml_file = tmp_path / "duplicate_schedule.yaml"
    yaml_file.write_text(
        "schedules:\n"
        "  - type: system\n"
        "    command: echo 'hello'\n"
        "    time: '14:10'\n"
        "    delay: 0\n"
        "    repetitions: 0\n"
        "    interval: -1\n"
        "  - type: system\n"
        "    command: echo 'hello'\n"
        "    time: '14:10'\n"
        "    delay: 0\n"
        "    repetitions: 0\n"
        "    interval: -1\n"
        "  - type: system\n"
        "    command: echo 'goodbye'\n"
        "    time: '15:00'\n"
    )

    config = Config(yaml_path=yaml_file, allow_duplicates=True)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    scheduler.load_schedule()

    assert "Allowing duplicate entry" in caplog.text
    # Verify all entries were scheduled (3 entries including duplicates)
    assert len(scheduler._job_registry.get_jobs()) == 3
    assert len(scheduler.scheduled_commands) == 3


def test_process_command_none_args() -> None:
    """Test _process_command when process.args is None."""
    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.args = None
    result = Scheduler._process_command(mock_process)
    assert result == "<unknown>"


def test_process_command_string_args() -> None:
    """Test _process_command when args is a string."""
    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.args = "echo test"
    result = Scheduler._process_command(mock_process)
    assert result == "echo test"


def test_process_command_bytes_args() -> None:
    """Test _process_command when args is bytes."""
    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.args = b"echo test"
    result = Scheduler._process_command(mock_process)
    assert result == "echo test"


def test_process_command_bytearray_args() -> None:
    """Test _process_command when args is bytearray."""
    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.args = bytearray(b"echo test")
    result = Scheduler._process_command(mock_process)
    assert result == "echo test"


def test_process_command_fallback() -> None:
    """Test _process_command fallback case for unknown args type."""
    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.args = 12345  # Not None, str, bytes, bytearray, or Sequence
    result = Scheduler._process_command(mock_process)
    assert result == "12345"


def test_terminate_running_processes_empty() -> None:
    """Test _terminate_running_processes when no processes are running."""
    scheduler = Scheduler()
    scheduler._running_processes = []
    # Should return early without errors
    scheduler._terminate_running_processes()
    assert scheduler._running_processes == []


def test_load_schedule_different_fields_not_duplicates(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test entries differing only in delay/repetitions/interval are not duplicates."""
    yaml_file = tmp_path / "different_fields.yaml"
    yaml_file.write_text(
        "schedules:\n"
        "  - type: system\n"
        "    command: echo 'hello'\n"
        "    time: '14:10'\n"
        "    delay: 0\n"
        "    repetitions: 0\n"
        "    interval: -1\n"
        "  - type: system\n"
        "    command: echo 'hello'\n"
        "    time: '14:10'\n"
        "    delay: 10\n"
        "    repetitions: 0\n"
        "    interval: -1\n"
        "  - type: system\n"
        "    command: echo 'hello'\n"
        "    time: '14:10'\n"
        "    delay: 0\n"
        "    repetitions: 2\n"
        "    interval: 60\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.WARNING)

    scheduler.load_schedule()

    # Should NOT detect duplicates since delay/repetitions/interval differ
    assert "Duplicate entry detected" not in caplog.text
    # All 3 entries should be scheduled
    # (1 + 1 + 3 = 5 executions due to repetitions)
    assert len(scheduler._job_registry.get_jobs()) == 5
    assert len(scheduler.scheduled_commands) == 5


def test_load_schedule_clears_global_registry(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule clears the job registry on reload."""
    yaml_file = tmp_path / "test_schedule.yaml"
    yaml_file.write_text(
        "schedules:\n  - type: system\n    command: echo 'hello'\n    time: '14:10'\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    # Call load_schedule twice
    scheduler.load_schedule()
    first_job_count = len(scheduler._job_registry.get_jobs())
    assert first_job_count == 1

    scheduler.load_schedule()
    second_job_count = len(scheduler._job_registry.get_jobs())

    # Verify registry was cleared and reloaded
    assert second_job_count == 1
    assert len(scheduler.scheduled_commands) == 1


def test_repetition_timing_with_delay(caplog: pytest.LogCaptureFixture) -> None:
    """Test repetition timing uses base_time + (i * interval) + per-run delay."""
    scheduler = Scheduler()
    caplog.set_level(logging.INFO)

    with patch("scheduler_run.scheduler.random.gauss") as mock_gauss:
        # Mock delays: 10s, 20s, 30s for each execution
        mock_gauss.side_effect = [10.0, 20.0, 30.0]

        # Base time: 10:00, interval: 3600s (1 hour), repetitions: 2
        # Expected timing:
        # - Execution 0: 10:00 + 10s = 10:00:10
        # - Execution 1: 10:00 + 3600s + 20s = 11:00:20
        # - Execution 2: 10:00 + 7200s + 30s = 12:00:30
        scheduler._schedule_command(
            "system", "echo 'test'", "10:00", delay=10, repetitions=2, interval=3600
        )

        # Verify 3 executions were scheduled
        assert len(scheduler._job_registry.get_jobs()) == 3
        assert len(scheduler.scheduled_commands) == 3

        # Verify the scheduled times match expected timing
        scheduled_times = [cmd.time for cmd in scheduler.scheduled_commands]
        assert "10:00:10" in scheduled_times
        assert "11:00:20" in scheduled_times
        assert "12:00:30" in scheduled_times

        # Verify delays were recalculated for each execution
        delays = [cmd.delay for cmd in scheduler.scheduled_commands]
        assert delays == [10, 20, 30]


def test_load_schedule_multiple_files_second_missing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule aborts when a later YAML file is missing without partial progress logs."""
    yaml_file1 = tmp_path / "schedule1.yaml"
    yaml_file1.write_text(
        "schedules:\n  - type: system\n    command: echo 'hello'\n    time: '14:10'\n"
    )
    yaml_file2 = tmp_path / "schedule2.yaml"
    # Don't create yaml_file2 - it should be missing

    config = Config(yaml_path=[yaml_file1, yaml_file2])
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    with pytest.raises(FileNotFoundError):
        scheduler.load_schedule()

    # Verify NO progress logs appear (atomic failure - no partial state)
    assert f"Loading schedule from {yaml_file1}" not in caplog.text
    assert f"YAML file not found: {yaml_file2}" in caplog.text
    # Verify no commands were scheduled due to atomicity
    assert len(scheduler._job_registry.get_jobs()) == 0
    assert len(scheduler.scheduled_commands) == 0


def test_load_schedule_non_dict_list_item(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with non-dict YAML list items (e.g., - 'oops')."""
    yaml_file = tmp_path / "invalid_list.yaml"
    yaml_file.write_text(
        "schedules:\n  - 'oops'\n  - type: system\n    "
        "command: echo 'test'\n    time: '14:30'\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    with pytest.raises(ValueError, match="expected dict"):
        scheduler.load_schedule()

    assert "Invalid entry" in caplog.text
    # Verify no commands were scheduled due to atomicity
    assert len(scheduler._job_registry.get_jobs()) == 0
    assert len(scheduler.scheduled_commands) == 0


def test_load_schedule_unsupported_type_explicit(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with explicitly unsupported type (not just typo)."""
    yaml_file = tmp_path / "unsupported_type.yaml"
    yaml_file.write_text(
        "schedules:\n  - type: shell\n    command: echo 'test'\n    time: '14:30'\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    with pytest.raises(ValidationError, match="Unsupported command type"):
        scheduler.load_schedule()

    assert "Invalid entry" in caplog.text
    assert "shell" in caplog.text
    # Verify no commands were scheduled due to atomicity
    assert len(scheduler._job_registry.get_jobs()) == 0
    assert len(scheduler.scheduled_commands) == 0


def test_load_schedule_clears_schedule_actually(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule clears scheduled_commands on reload without mocks."""
    yaml_file = tmp_path / "test_schedule.yaml"
    yaml_file.write_text(
        "schedules:\n  - type: system\n    command: echo 'hello'\n    time: '14:10'\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    # First load
    scheduler.load_schedule()
    assert len(scheduler.scheduled_commands) == 1
    first_command = scheduler.scheduled_commands[0]

    # Second load (reload)
    scheduler.load_schedule()
    assert len(scheduler.scheduled_commands) == 1
    second_command = scheduler.scheduled_commands[0]

    # Verify the scheduled_commands list was actually cleared
    # (not just appended to)
    assert first_command == second_command
    assert len(scheduler._job_registry.get_jobs()) == 1


def test_load_schedule_interval_zero_with_repetitions(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with interval=0 and repetitions>0 raises ValidationError."""
    yaml_file = tmp_path / "invalid_interval.yaml"
    yaml_file.write_text(
        "schedules:\n"
        "  - type: system\n"
        "    command: echo 'test'\n"
        "    time: '14:30'\n"
        "    repetitions: 3\n"
        "    interval: 0\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    with pytest.raises(ValidationError, match="Interval cannot be 0"):
        scheduler.load_schedule()

    assert "Invalid entry" in caplog.text
    # Verify no commands were scheduled due to atomicity
    assert len(scheduler._job_registry.get_jobs()) == 0
    assert len(scheduler.scheduled_commands) == 0


def test_load_schedule_interval_negative_with_repetitions(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule rejects negative interval when repetitions > 0."""
    yaml_file = tmp_path / "invalid_interval_negative.yaml"
    yaml_file.write_text(
        "schedules:\n"
        "  - type: system\n"
        "    command: echo 'test'\n"
        "    time: '14:30'\n"
        "    repetitions: 3\n"
        "    interval: -5\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    with pytest.raises(ValidationError, match="Interval cannot be negative"):
        scheduler.load_schedule()

    assert "Invalid entry" in caplog.text
    # Verify no commands were scheduled due to atomicity
    assert len(scheduler._job_registry.get_jobs()) == 0
    assert len(scheduler.scheduled_commands) == 0


def test_job_should_run_previous_day() -> None:
    """Test Job.should_run() when last_run was on a previous day."""
    from scheduler_run.scheduler import Job

    # Create a job for 14:30:00
    job = Job(lambda: None, "14:30:00")

    # Set last_run to yesterday
    yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
    job.last_run = yesterday

    # Set current time to after the target time today
    now = datetime.datetime.now().replace(hour=15, minute=0, second=0, microsecond=0)

    # Job should run
    assert job.should_run(now) is True


def test_job_should_run_false_already_ran_today() -> None:
    """Test Job.should_run() returns False when already ran today before target time."""
    from scheduler_run.scheduler import Job

    # Create a job for 14:30:00
    job = Job(lambda: None, "14:30:00")

    # Set last_run to today before the target time
    today = datetime.datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    job.last_run = today

    # Set current time to before the target time
    now = datetime.datetime.now().replace(hour=11, minute=0, second=0, microsecond=0)

    # Job should not run
    assert job.should_run(now) is False


def test_job_run_updates_last_run() -> None:
    """Test Job.run() executes function and updates last_run."""
    from scheduler_run.scheduler import Job

    # Track if function was called
    called = []

    def test_func() -> None:
        called.append(True)

    job = Job(test_func, "14:30:00")
    assert job.last_run is None

    job.run()

    assert len(called) == 1
    assert job.last_run is not None


def test_job_registry_schedule_daily_hhmm_format() -> None:
    """Test JobRegistry.schedule_daily() converts HH:MM to HH:MM:SS."""
    from scheduler_run.scheduler import JobRegistry

    registry = JobRegistry()

    def test_func() -> None:
        pass

    # Schedule with HH:MM format (2 parts)
    job = registry.schedule_daily(test_func, "14:30")

    # Verify time was converted to HH:MM:SS
    assert job.target_time_str == "14:30:00"


def test_job_registry_run_pending_exception_handling(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test JobRegistry.run_pending() handles job execution failures."""
    from scheduler_run.scheduler import JobRegistry

    registry = JobRegistry()
    caplog.set_level(logging.ERROR)

    def failing_func() -> None:
        raise ValueError("Test error")

    # Schedule a job that will fail
    registry.schedule_daily(failing_func, "00:00:00")

    # Set next_run to past so it should run
    past = datetime.datetime.now() - datetime.timedelta(seconds=1)
    for job in registry.get_jobs():
        job.next_run = past

    # Run pending - should handle exception gracefully
    registry.run_pending()

    # Verify error was logged
    assert "Job execution failed" in caplog.text
    assert "Test error" in caplog.text
