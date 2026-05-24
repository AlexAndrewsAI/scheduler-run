"""Tests for the scheduler module."""

import datetime
import logging
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
import yaml
from pydantic import ValidationError

from scheduler_run.config import Config
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


def test_run_system_command_success(caplog: pytest.LogCaptureFixture) -> None:
    """Test _run_system_command starts a background subprocess."""
    scheduler = Scheduler()
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
    """Test _reap_finished_processes logs failure for non-zero exit."""
    scheduler = Scheduler()
    caplog.set_level(logging.ERROR)

    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.poll.return_value = 1
    mock_process.args = ["false"]
    scheduler._running_processes = [mock_process]

    scheduler._reap_finished_processes()

    assert scheduler._running_processes == []
    assert "Command failed: false (exit 1)" in caplog.text


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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        scheduler._schedule_command("system", "echo 'test'", "14:30")

        mock_every.assert_called_once()
        mock_day.at.assert_called_once_with("14:30:00")
        mock_at.do.assert_called_once()
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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        scheduler.load_schedule()

        assert f"Loading schedule from {yaml_file}" in caplog.text
        mock_every.assert_called()


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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        with pytest.raises(ValueError, match="missing 'schedules' key"):
            scheduler.load_schedule()

        assert "Invalid YAML format" in caplog.text
        assert mock_every.call_count == 0
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
        patch("scheduler_run.scheduler.schedule.every") as mock_every,
    ):
        mock_file.side_effect = PermissionError("Permission denied")

        with pytest.raises(PermissionError):
            scheduler.load_schedule()

        assert f"Permission denied reading YAML file: {yaml_file}" in caplog.text
        assert mock_every.call_count == 0
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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        with pytest.raises(yaml.YAMLError):
            scheduler.load_schedule()

        assert f"YAML parsing error in {yaml_file}" in caplog.text
        assert mock_every.call_count == 0
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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        with pytest.raises(ValidationError):
            scheduler.load_schedule()

        assert "Invalid entry" in caplog.text


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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        scheduler.load_schedule()

        assert "Duplicate entry detected" in caplog.text
        assert (
            "type='system', command='echo 'hello'', time='14:10', delay=0, "
            "repetitions=0, interval=-1" in caplog.text
        )
        # Verify only unique entries were scheduled (2 unique entries)
        assert mock_every.call_count == 2


def test_scheduler_run(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Test Scheduler.run() method."""
    yaml_file = tmp_path / "test_schedule.yaml"
    yaml_file.write_text(
        "schedules:\n  - type: system\n    command: echo 'test'\n    time: '14:30'\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        with (
            patch("scheduler_run.scheduler.schedule.run_pending"),
            patch("scheduler_run.scheduler.time.sleep") as mock_sleep,
            patch.object(scheduler, "_terminate_running_processes") as mock_terminate,
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

    with (
        patch("scheduler_run.scheduler.schedule.every") as mock_every,
        patch("scheduler_run.scheduler.random.gauss") as mock_gauss,
    ):
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at
        mock_gauss.return_value = 12.3

        scheduler._schedule_command("system", "echo 'test'", "14:30", delay=10)

        mock_gauss.assert_called_once_with(mu=10, sigma=1.5)
        # 14:30 + 12 seconds = 14:30:12
        mock_day.at.assert_called_once_with("14:30:12")
        mock_at.do.assert_called_once_with(scheduler._run_system_command, "echo 'test'")

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

    with (
        patch("scheduler_run.scheduler.schedule.every") as mock_every,
        patch("scheduler_run.scheduler.random.gauss") as mock_gauss,
    ):
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at
        mock_gauss.return_value = 45.0

        scheduler.load_schedule()

        assert len(scheduler.scheduled_commands) == 1
        assert scheduler.scheduled_commands[0].command_type == "system"
        assert scheduler.scheduled_commands[0].command == "echo 'hello'"
        assert scheduler.scheduled_commands[0].time == "14:10:45"
        assert scheduler.scheduled_commands[0].delay == 45


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
        patch("scheduler_run.scheduler.schedule.every") as mock_every,
        patch("scheduler_run.scheduler.random.gauss") as mock_gauss,
        patch("scheduler_run.scheduler.datetime.datetime") as mock_dt,
    ):
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

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

    with (
        patch("scheduler_run.scheduler.schedule.every") as mock_every,
        patch("scheduler_run.scheduler.random.gauss") as mock_gauss,
    ):
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at
        # Return different delays for each repetition
        mock_gauss.side_effect = [5.0, 10.0, 15.0]

        scheduler._schedule_command(
            "system", "echo 'test'", "14:30", delay=10, repetitions=2, interval=60
        )

        # Should schedule 3 times (1 + 2 repetitions)
        assert mock_every.call_count == 3
        assert len(scheduler.scheduled_commands) == 3

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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        scheduler._schedule_command("system", "echo 'test'", "14:30", repetitions=0)

        # Should schedule only once
        assert mock_every.call_count == 1
        assert len(scheduler.scheduled_commands) == 1


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

    with (
        patch("scheduler_run.scheduler.schedule.every") as mock_every,
        patch("scheduler_run.scheduler.random.gauss") as mock_gauss,
    ):
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at
        mock_gauss.side_effect = [10.0, 15.0, 20.0]

        scheduler.load_schedule()

        # Should schedule 3 times (1 + 2 repetitions)
        assert len(scheduler.scheduled_commands) == 3
        assert mock_every.call_count == 3


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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        scheduler.load_schedule()

        # Should schedule 2 times (1 + 1 repetition)
        assert len(scheduler.scheduled_commands) == 2
        assert mock_every.call_count == 2


def test_schedule_command_auto_calculate_interval(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test _schedule_command with auto-calculated interval."""
    scheduler = Scheduler()
    caplog.set_level(logging.INFO)

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        # repetitions=3 should auto-calculate interval to
        # 24*3600/4 = 21600 seconds (6 hours)
        scheduler._schedule_command(
            "system", "echo 'test'", "00:00", repetitions=3, interval=-1
        )

        # Should schedule 4 times (1 + 3 repetitions)
        assert mock_every.call_count == 4
        assert len(scheduler.scheduled_commands) == 4

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

    with (
        patch("scheduler_run.scheduler.schedule.every") as mock_every,
        patch("scheduler_run.scheduler.random.gauss") as mock_gauss,
    ):
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at
        # Return same delay for all executions
        mock_gauss.return_value = 30.0

        # repetitions=1 should auto-calculate interval to
        # 24*3600/2 = 43200 seconds (12 hours)
        scheduler._schedule_command(
            "system", "echo 'test'", "00:00", delay=10, repetitions=1, interval=-1
        )

        # Should schedule 2 times (1 + 1 repetition)
        assert mock_every.call_count == 2
        assert len(scheduler.scheduled_commands) == 2

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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        scheduler.load_schedule()

        # Should schedule 4 times (1 + 3 repetitions)
        assert len(scheduler.scheduled_commands) == 4
        assert mock_every.call_count == 4

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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        scheduler.load_schedule()

        assert "Loading schedule from 2 YAML file(s)" in caplog.text
        assert f"Loading schedule from {yaml_file1}" in caplog.text
        assert f"Loading schedule from {yaml_file2}" in caplog.text
        # Should schedule 2 commands (one from each file)
        assert mock_every.call_count == 2
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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        scheduler.load_schedule()

        assert "Duplicate entry detected" in caplog.text
        # Should only schedule 1 command (duplicate skipped)
        assert mock_every.call_count == 1
        assert len(scheduler.scheduled_commands) == 1


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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        scheduler.load_schedule()

        assert "Allowing duplicate entry" in caplog.text
        # Verify all entries were scheduled (3 entries including duplicates)
        assert mock_every.call_count == 3
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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        scheduler.load_schedule()

        # Should NOT detect duplicates since delay/repetitions/interval differ
        assert "Duplicate entry detected" not in caplog.text
        # All 3 entries should be scheduled
        # (1 + 1 + 3 = 5 executions due to repetitions)
        assert mock_every.call_count == 5
        assert len(scheduler.scheduled_commands) == 5


def test_load_schedule_clears_global_registry(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule clears the global schedule registry on reload."""
    yaml_file = tmp_path / "test_schedule.yaml"
    yaml_file.write_text(
        "schedules:\n  - type: system\n    command: echo 'hello'\n    time: '14:10'\n"
    )

    config = Config(yaml_path=yaml_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    with (
        patch("scheduler_run.scheduler.schedule.every") as mock_every,
        patch("scheduler_run.scheduler.schedule.clear") as mock_clear,
    ):
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        # Call load_schedule twice
        scheduler.load_schedule()
        first_call_count = mock_every.call_count
        assert first_call_count == 1
        assert mock_clear.call_count == 1

        scheduler.load_schedule()
        second_call_count = mock_every.call_count

        # Verify schedule.clear() was called twice (once for each load_schedule)
        assert second_call_count == 2
        assert mock_clear.call_count == 2
        assert len(scheduler.scheduled_commands) == 1


def test_repetition_timing_with_delay(caplog: pytest.LogCaptureFixture) -> None:
    """Test repetition timing uses base_time + (i * interval) + per-run delay."""
    scheduler = Scheduler()
    caplog.set_level(logging.INFO)

    with (
        patch("scheduler_run.scheduler.schedule.every") as mock_every,
        patch("scheduler_run.scheduler.random.gauss") as mock_gauss,
    ):
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

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
        assert mock_every.call_count == 3
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
    """Test load_schedule aborts when a later YAML file is missing."""
    yaml_file1 = tmp_path / "schedule1.yaml"
    yaml_file1.write_text(
        "schedules:\n  - type: system\n    command: echo 'hello'\n    time: '14:10'\n"
    )
    yaml_file2 = tmp_path / "schedule2.yaml"
    # Don't create yaml_file2 - it should be missing

    config = Config(yaml_path=[yaml_file1, yaml_file2])
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        with pytest.raises(FileNotFoundError):
            scheduler.load_schedule()

        # Verify first file was loaded before error
        assert f"Loading schedule from {yaml_file1}" in caplog.text
        assert f"YAML file not found: {yaml_file2}" in caplog.text
        # Verify no commands were scheduled due to atomicity
        assert mock_every.call_count == 0
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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        with pytest.raises(ValueError, match="expected dict"):
            scheduler.load_schedule()

        assert "Invalid entry" in caplog.text
        # Verify no commands were scheduled due to atomicity
        assert mock_every.call_count == 0
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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        with pytest.raises(ValidationError, match="Unsupported command type"):
            scheduler.load_schedule()

        assert "Invalid entry" in caplog.text
        assert "shell" in caplog.text
        # Verify no commands were scheduled due to atomicity
        assert mock_every.call_count == 0
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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

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
        assert mock_every.call_count == 2


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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        with pytest.raises(ValidationError, match="Interval cannot be 0"):
            scheduler.load_schedule()

        assert "Invalid entry" in caplog.text
        # Verify no commands were scheduled due to atomicity
        assert mock_every.call_count == 0
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

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        with pytest.raises(ValidationError, match="Interval cannot be negative"):
            scheduler.load_schedule()

        assert "Invalid entry" in caplog.text
        # Verify no commands were scheduled due to atomicity
        assert mock_every.call_count == 0
        assert len(scheduler.scheduled_commands) == 0
