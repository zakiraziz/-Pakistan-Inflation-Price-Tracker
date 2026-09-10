"""
scheduler.py
------------
Scheduled ingestion using APScheduler.

- Weekly cron (default Saturday 06:00) runs the validated ingestion pipeline.
- `python scheduler.py --once` performs a single run and exits (CI-friendly).
- `python scheduler.py` starts the long-running scheduler (deployment).

Production notes:
    In a multi-process deployment, run this as its own container/process (or
    swap to cron / GitHub Actions / Celery beat) so it is not tied to the web
    process lifetime.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import date

import db
import log
from job import add_next_week

logger = log.get_logger("scheduler")

CRON_DAY_OF_WEEK = os.environ.get("INGEST_CRON_DOW", "sat")
CRON_HOUR = os.environ.get("INGEST_CRON_HOUR", "6")


def run_ingest() -> dict:
    """One ingestion run: fetch -> validate -> stage/approve -> alerts."""
    con = db.init_db()
    try:
        inserted, snap, counts = add_next_week(con, date.today())
        pending = db.count_status(con, db.STATUS_PENDING)
        logger.info("ingestion finished: inserted=%s for_week=%s counts=%s "
                    "pending=%s", inserted, snap, counts, pending)
        return {"inserted": inserted, "for_week": snap.isoformat(),
                "counts": counts, "pending": pending}
    finally:
        con.close()


def main() -> int:
    if "--once" in sys.argv:
        result = run_ingest()
        print("one-shot ingest:", result)
        return 0

    from apscheduler.schedulers.background import BackgroundScheduler
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(run_ingest, "cron", day_of_week=CRON_DAY_OF_WEEK,
                  hour=int(CRON_HOUR), minute=0, id="weekly-price-ingest")
    sched.start()
    logger.info("scheduler started (cron %s %s:00 UTC). Ctrl+C to stop.",
                CRON_DAY_OF_WEEK, CRON_HOUR)
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown(wait=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())