"""Tests for the hello module.
"""

import logging

from scheduler_run import Config, HelloWorld


def test_default_name(caplog):
    """Test HelloWorld with default name.

    Args:
        caplog: Pytest fixture for capturing log output.
    """
    caplog.set_level(logging.INFO)
    hello_world = HelloWorld()
    greeting = hello_world.greet()
    assert greeting == "Hello, World!"
    assert len(caplog.records) == 1
    assert caplog.records[0].message == "hello World"
    assert caplog.records[0].levelname == "INFO"


def test_custom_name(caplog):
    """Test HelloWorld with custom name.

    Args:
        caplog: Pytest fixture for capturing log output.
    """
    caplog.set_level(logging.INFO)
    hello_world = HelloWorld(Config(name="Alice"))
    greeting = hello_world.greet()
    assert greeting == "Hello, Alice!"
    assert len(caplog.records) == 1
    assert caplog.records[0].message == "hello Alice"
    assert caplog.records[0].levelname == "INFO"
