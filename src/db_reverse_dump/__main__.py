"""Entry point for running as a module: python -m db_reverse_dump"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
