"""Provide safe standard streams for PyInstaller windowed applications.

PyInstaller's --windowed mode may set stdout/stderr to None on Windows. Some
third-party packages assume those streams exist, so direct their output to the
null device instead of allowing an AttributeError during startup.
"""

import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")
