#!/usr/bin/env python3
"""Entry point kept for backward compatibility with the workflow. Runs kill_pv2 v2."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from killpv2.app import main  # noqa: E402

if __name__ == "__main__":
    main()
