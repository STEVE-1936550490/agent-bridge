"""Compatibility wrapper for python -m moma_proxy."""

from __future__ import annotations

import sys

from agent_bridge.main import main

if __name__ == "__main__":
    sys.exit(main())
