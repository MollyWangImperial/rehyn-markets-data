"""Fills the 30 day sentiment history once any run in progress has finished, then exits. Started detached, so it keeps
going if the window that started it closes. Batches already processed are skipped, so it resumes where it stopped.

  python -I ingest/run_backfill.py [days]
"""
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import s_sentiment  # noqa: E402
import sentiment_job  # noqa: E402

days = int(sys.argv[1]) if len(sys.argv) > 1 else 31
while s_sentiment._locked():
    time.sleep(20)
sentiment_job.main(backfill_days=days)
