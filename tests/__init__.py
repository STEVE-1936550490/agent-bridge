"""Test package initialization."""

from agent_bridge import __version__


def test_version():
    """Test package version is defined."""
    assert __version__ == "0.1.0"
