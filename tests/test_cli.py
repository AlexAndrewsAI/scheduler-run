"""Tests for the CLI module."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from scheduler_run.cli import app

runner = CliRunner()


def test_run_command_default_path() -> None:
    """Test CLI run command with default YAML path."""
    with (
        patch("scheduler_run.cli.Scheduler") as mock_scheduler_class,
        patch("scheduler_run.cli.Config"),
    ):
        mock_scheduler = MagicMock()
        mock_scheduler_class.return_value = mock_scheduler

        result = runner.invoke(app, [])

        assert result.exit_code == 0
        mock_scheduler_class.assert_called_once()
        mock_scheduler.run.assert_called_once()


def test_run_command_custom_path() -> None:
    """Test CLI run command with custom YAML path."""
    custom_path = "custom/schedule.yaml"

    with (
        patch("scheduler_run.cli.Scheduler") as mock_scheduler_class,
        patch("scheduler_run.cli.Config"),
    ):
        mock_scheduler = MagicMock()
        mock_scheduler_class.return_value = mock_scheduler

        result = runner.invoke(app, ["--input", custom_path])

        assert result.exit_code == 0
        mock_scheduler_class.assert_called_once()
        mock_scheduler.run.assert_called_once()


def test_run_command_short_option() -> None:
    """Test CLI run command with short option -i."""
    custom_path = "custom/schedule.yaml"

    with (
        patch("scheduler_run.cli.Scheduler") as mock_scheduler_class,
        patch("scheduler_run.cli.Config"),
    ):
        mock_scheduler = MagicMock()
        mock_scheduler_class.return_value = mock_scheduler

        result = runner.invoke(app, ["-i", custom_path])

        assert result.exit_code == 0
        mock_scheduler_class.assert_called_once()


def test_app_help() -> None:
    """Test CLI help command."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Scheduler" in result.output


def test_run_command_help() -> None:
    """Test run command help."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "input" in result.output
