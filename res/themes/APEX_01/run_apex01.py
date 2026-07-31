#!/usr/bin/env python3
"""Launcher for APEX 01 Theme."""
from pathlib import Path
import sys

THEME_DIR = Path(__file__).resolve().parent
if str(THEME_DIR) not in sys.path:
    sys.path.insert(0, str(THEME_DIR))

from apex01.app import main

if __name__ == "__main__":
    sys.exit(main())
