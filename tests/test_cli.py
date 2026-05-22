"""Tests for the CLI module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from scheduler_run.cli import app

runner = CliRunner()


def test_run_command_default_path() -> None:
    """Test CLI run command with default YAML path."""
    with patch("scheduler_run.cli.Config") as mock_config_class:
        mock_config = MagicMock()
        mock_config_class.return_value = mock_config

        with patch("scheduler_run.cli.Scheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler_class.return_value = mock_scheduler

            result = runner.invoke(app, [])

            assert result.exit_code == 0
            mock_config_class.assert_called_once()
            call_kwargs = mock_config_class.call_args.kwargs
            assert call_kwargs["yaml_path"] == [Path("schedule.yaml")]
            assert call_kwargs["allow_duplicates"] is False
            mock_scheduler.run.assert_called_once()


def test_run_command_custom_path() -> None:
    """Test CLI run command with custom YAML path."""
    custom_path = "custom/schedule.yaml"

    with patch("scheduler_run.cli.Config") as mock_config_class:
        mock_config = MagicMock()
        mock_config_class.return_value = mock_config

        with patch("scheduler_run.cli.Scheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler_class.return_value = mock_scheduler

            result = runner.invoke(app, [custom_path])

            assert result.exit_code == 0
            mock_config_class.assert_called_once()
            call_kwargs = mock_config_class.call_args.kwargs
            assert call_kwargs["yaml_path"] == [Path(custom_path)]
            assert call_kwargs["allow_duplicates"] is False
            mock_scheduler.run.assert_called_once()


def test_run_command_multiple_files() -> None:
    """Test CLI run command with multiple YAML files."""
    file1 = "custom/schedule1.yaml"
    file2 = "custom/schedule2.yaml"

    with patch("scheduler_run.cli.Config") as mock_config_class:
        mock_config = MagicMock()
        mock_config_class.return_value = mock_config

        with patch("scheduler_run.cli.Scheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler_class.return_value = mock_scheduler

            result = runner.invoke(app, [file1, file2])

            assert result.exit_code == 0
            mock_config_class.assert_called_once()
            call_kwargs = mock_config_class.call_args.kwargs
            assert call_kwargs["yaml_path"] == [Path(file1), Path(file2)]
            assert call_kwargs["allow_duplicates"] is False
            mock_scheduler.run.assert_called_once()


def test_app_help() -> None:
    """Test CLI help command."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Scheduler" in result.output


def test_run_command_help() -> None:
    """Test run command help."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "FILES" in result.output


def test_run_command_allow_duplicates() -> None:
    """Test CLI run command with --allow-duplicates flag."""
    with patch("scheduler_run.cli.Config") as mock_config_class:
        mock_config = MagicMock()
        mock_config_class.return_value = mock_config

        with patch("scheduler_run.cli.Scheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler_class.return_value = mock_scheduler

            result = runner.invoke(app, ["--allow-duplicates"])

            assert result.exit_code == 0
            mock_config_class.assert_called_once()
            call_kwargs = mock_config_class.call_args.kwargs
            assert call_kwargs["yaml_path"] == [Path("schedule.yaml")]
            assert call_kwargs["allow_duplicates"] is True
            mock_scheduler.run.assert_called_once()
