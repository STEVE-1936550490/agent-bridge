"""Allow running as python -m agent_bridge."""

import sys

from .main import main

if __name__ == "__main__":
    sys.exit(main())
