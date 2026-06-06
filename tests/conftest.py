"""Pytest hooks: newer sqlite for Chroma on hosts with system sqlite < 3.35."""

import sys

try:
    __import__("pysqlite3")
    sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
    pass
