"""Tests for the config module."""

from pathlib import Path

import pytest

from scheduler_run.config import Config, ScheduleEntry


def test_config_default() -> None:
    """Test Config with default values."""
    config = Config()
    assert config.yaml_path == [Path("schedule.yaml")]


def test_config_custom_path() -> None:
    """Test Config with custom yaml_path."""
    custom_path = Path("custom/schedule.yaml")
    config = Config(yaml_path=custom_path)
    assert config.yaml_path == [custom_path]


def test_config_model_title() -> None:
    """Test Config model title."""
    config = Config()
    assert config.model_config["title"] == "Scheduler Config"


def test_schedule_entry_valid() -> None:
    """Test ScheduleEntry with valid data."""
    entry = ScheduleEntry(type="system", command="echo 'hello'", time="14:30")
    assert entry.type == "system"
    assert entry.command == "echo 'hello'"
    assert entry.time == "14:30"


def test_schedule_entry_valid_time_formats() -> None:
    """Test ScheduleEntry with various valid time formats."""
    valid_times = [
        "00:00",
        "01:00",
        "09:00",
        "12:00",
        "13:00",
        "23:59",
        "08:00",
        "9:00",
    ]
    for time_str in valid_times:
        entry = ScheduleEntry(type="system", command="echo test", time=time_str)
        assert entry.time == time_str


def test_schedule_entry_invalid_time_format() -> None:
    """Test ScheduleEntry with invalid time format."""
    invalid_times = ["24:00", "25:00", "14:60", "14:9", "14", "14:30:00", "ab:cd"]
    for time_str in invalid_times:
        with pytest.raises(ValueError, match="Invalid time format"):
            ScheduleEntry(type="system", command="echo test", time=time_str)


def test_schedule_entry_empty_command() -> None:
    """Test ScheduleEntry with empty command."""
    with pytest.raises(ValueError, match="Command cannot be empty"):
        ScheduleEntry(type="system", command="", time="14:30")

    with pytest.raises(ValueError, match="Command cannot be empty"):
        ScheduleEntry(type="system", command="   ", time="14:30")


def test_schedule_entry_empty_type() -> None:
    """Test ScheduleEntry with empty type."""
    with pytest.raises(ValueError, match="Type cannot be empty"):
        ScheduleEntry(type="", command="echo test", time="14:30")

    with pytest.raises(ValueError, match="Type cannot be empty"):
        ScheduleEntry(type="   ", command="echo test", time="14:30")


def test_schedule_entry_unsupported_type() -> None:
    """Test ScheduleEntry with unsupported type."""
    with pytest.raises(ValueError, match="Unsupported command type: 'unsupported'"):
        ScheduleEntry(type="unsupported", command="echo test", time="14:30")

    with pytest.raises(ValueError, match="Unsupported command type: 'systm'"):
        ScheduleEntry(type="systm", command="echo test", time="14:30")


def test_schedule_entry_delay_valid() -> None:
    """Test ScheduleEntry with valid delay."""
    entry = ScheduleEntry(type="system", command="echo test", time="14:30", delay=10)
    assert entry.delay == 10

    # Default delay should be 0
    entry_default = ScheduleEntry(type="system", command="echo test", time="14:30")
    assert entry_default.delay == 0


def test_schedule_entry_delay_negative() -> None:
    """Test ScheduleEntry with negative delay."""
    with pytest.raises(ValueError, match="Delay must be a non-negative integer"):
        ScheduleEntry(type="system", command="echo test", time="14:30", delay=-5)


def test_schedule_entry_repetitions_valid() -> None:
    """Test ScheduleEntry with valid repetitions."""
    entry = ScheduleEntry(
        type="system", command="echo test", time="14:30", repetitions=3
    )
    assert entry.repetitions == 3

    # Default repetitions should be 0
    entry_default = ScheduleEntry(type="system", command="echo test", time="14:30")
    assert entry_default.repetitions == 0


def test_schedule_entry_repetitions_negative() -> None:
    """Test ScheduleEntry with negative repetitions."""
    with pytest.raises(ValueError, match="Repetitions must be a non-negative integer"):
        ScheduleEntry(type="system", command="echo test", time="14:30", repetitions=-5)


def test_schedule_entry_interval_valid() -> None:
    """Test ScheduleEntry with valid interval."""
    entry = ScheduleEntry(
        type="system", command="echo test", time="14:30", repetitions=3, interval=60
    )
    assert entry.interval == 60

    # Default interval should be -1
    entry_default = ScheduleEntry(type="system", command="echo test", time="14:30")
    assert entry_default.interval == -1


def test_schedule_entry_interval_zero_with_repetitions() -> None:
    """Test ScheduleEntry with interval=0 and repetitions>0 raises error."""
    with pytest.raises(ValueError, match="Interval cannot be 0 when repetitions > 0"):
        ScheduleEntry(
            type="system", command="echo test", time="14:30", repetitions=3, interval=0
        )


def test_schedule_entry_interval_negative_with_repetitions() -> None:
    """Test ScheduleEntry rejects negative interval when repetitions > 0."""
    with pytest.raises(
        ValueError,
        match="Interval cannot be negative \\(except -1\\) when repetitions > 0",
    ):
        ScheduleEntry(
            type="system", command="echo test", time="14:30", repetitions=3, interval=-5
        )


def test_schedule_entry_interval_positive_without_repetitions() -> None:
    """Test ScheduleEntry with positive interval and repetitions=0 raises error."""
    with pytest.raises(
        ValueError, match=r"Interval .* is ignored when repetitions == 0"
    ):
        ScheduleEntry(
            type="system", command="echo test", time="14:30", repetitions=0, interval=60
        )


def test_schedule_entry_interval_valid_with_repetitions() -> None:
    """Test ScheduleEntry with valid interval and repetitions combinations."""
    # interval=-1 with repetitions>0 (auto-calculation)
    entry1 = ScheduleEntry(
        type="system", command="echo test", time="14:30", repetitions=3, interval=-1
    )
    assert entry1.interval == -1
    assert entry1.repetitions == 3

    # interval>0 with repetitions>0
    entry2 = ScheduleEntry(
        type="system", command="echo test", time="14:30", repetitions=3, interval=60
    )
    assert entry2.interval == 60
    assert entry2.repetitions == 3

    # interval=-1 with repetitions=0 (default)
    entry3 = ScheduleEntry(type="system", command="echo test", time="14:30")
    assert entry3.interval == -1
    assert entry3.repetitions == 0


def test_config_list_of_paths() -> None:
    """Test Config with a list of paths."""
    paths = [Path("schedule1.yaml"), Path("schedule2.yaml")]
    config = Config(yaml_path=paths)
    assert config.yaml_path == paths


def test_config_string_path() -> None:
    """Test Config with a string path (converted to Path)."""
    config = Config(yaml_path="custom.yaml")
    assert config.yaml_path == [Path("custom.yaml")]


def test_config_list_of_strings() -> None:
    """Test Config with a list of strings (converted to Paths)."""
    config = Config(yaml_path=["schedule1.yaml", "schedule2.yaml"])
    assert config.yaml_path == [Path("schedule1.yaml"), Path("schedule2.yaml")]


def test_config_allow_duplicates_default() -> None:
    """Test Config default allow_duplicates value."""
    config = Config()
    assert config.allow_duplicates is False


def test_config_allow_duplicates_true() -> None:
    """Test Config with allow_duplicates set to True."""
    config = Config(allow_duplicates=True)
    assert config.allow_duplicates is True


def test_config_yaml_paths_from_string() -> None:
    """Test yaml_paths when yaml_path is a raw string (bypasses validator)."""
    config = Config.model_construct(yaml_path="foo.yaml")
    assert config.yaml_paths == [Path("foo.yaml")]


def test_config_yaml_paths_from_path() -> None:
    """Test yaml_paths when yaml_path is a raw Path (bypasses validator)."""
    path = Path("bar.yaml")
    config = Config.model_construct(yaml_path=path)
    assert config.yaml_paths == [path]


def test_config_yaml_paths_from_list() -> None:
    """Test yaml_paths when yaml_path is a mixed list (bypasses validator)."""
    config = Config.model_construct(yaml_path=[Path("a.yaml"), "b.yaml"])
    assert config.yaml_paths == [Path("a.yaml"), Path("b.yaml")]


def test_config_yaml_paths_fallback() -> None:
    """Test yaml_paths fallback for unexpected runtime types (mypy guard)."""
    config = Config.model_construct(yaml_path=123)
    assert config.yaml_paths == [Path("schedule.yaml")]


def test_config_normalize_yaml_path_mixed_list() -> None:
    """Test validator converts string items in a mixed path list to Path."""
    config = Config(yaml_path=[Path("a.yaml"), "b.yaml"])
    assert config.yaml_path == [Path("a.yaml"), Path("b.yaml")]


def test_config_normalize_yaml_path_invalid_type() -> None:
    """Test validator rejects invalid yaml_path types."""
    with pytest.raises(TypeError, match="Invalid type for yaml_path"):
        Config(yaml_path=123)  # type: ignore[arg-type]


def test_schedule_entry_command_list() -> None:
    """Test ScheduleEntry with command as list is normalized to string."""
    entry = ScheduleEntry(
        type="system",
        command=["sh", "-c", "echo 'hello'"],  # type: ignore[arg-type]
        time="14:30",
    )
    assert entry.command == "sh -c 'echo '\"'\"'hello'\"'\"''"
    assert isinstance(entry.command, str)


def test_schedule_entry_command_string() -> None:
    """Test ScheduleEntry with command as string remains string."""
    entry = ScheduleEntry(type="system", command="echo 'hello'", time="14:30")
    assert entry.command == "echo 'hello'"
    assert isinstance(entry.command, str)


def test_schedule_entry_command_empty_list() -> None:
    """Test ScheduleEntry with empty command list raises error."""
    with pytest.raises(ValueError, match="Command cannot be empty"):
        ScheduleEntry(type="system", command=[], time="14:30")  # type: ignore[arg-type]
