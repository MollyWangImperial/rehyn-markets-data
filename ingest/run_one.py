"""Runs one collection function: python -I ingest/run_one.py <module> <function>. Used by daily.py, one process per source."""
import importlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from core import init_db  # noqa: E402

if __name__ == "__main__":
    mod, fn = sys.argv[1], sys.argv[2]
    getattr(importlib.import_module(mod), fn)(init_db())
