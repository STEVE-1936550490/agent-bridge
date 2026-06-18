"""Allow running as python -m moma_proxy."""

import sys

from .main import main

if __name__ == "__main__":
    sys.exit(main())
