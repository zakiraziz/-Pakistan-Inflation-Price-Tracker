"""
scheduler.py
------------
Scheduled ingestion using APScheduler.

Two cadences, one pipeline:

- **Weekly cron** (default: Saturday 06:00 UTC) - the production cadence, since
  the price basket is published weekly.
- **Fixed interval** - ``INGEST_INTERVAL_SECONDS=600`` (or ``--interval 600``)
  runs the same job every N seconds. Useful for demos, and for keeping a
  long-running dashboard visibly live without waiting for Saturday.

Either way the job signals ``core/live.py`` after the write is committed, so
every open dashboard pulls the new week the moment it lands.

- ``python scheduler.py --once``         -> one run, then exit (CI-friendly)
- ``python scheduler.py --interval 300`` -> every 5 minutes until Ctrl+C
- ``python scheduler.py``                -> weekly cron (deployment default)

Production notes:
    In a multi-process deployment, run this as its own container/process (or
    swap to cron / GitHub Actions / Celery beat) so it is not tied to the web
    process lifetime.
"""

from __future__ import annotations

import sys
import time
from datetime import date

import db
import log
from core import live
from core.config import settings
from job import add_next_week

logger = log.get_logger("scheduler")

CRON_DAY_OF_WEEK = settings.ingest_cron_dow
CRON_HOUR = settings.ingest_cron_hour


def run_ingest() -> dict:
    """One ingestion run: fetch -> validate -> stage/approve -> alerts."""
    con = db.init_db()
    try:
        inserted, snap, counts = add_next_week(con, date.today())
        pending = db.count_status(con, db.STATUS_PENDING)
        logger.info(
            "ingestion finished: inserted=%s for_week=%s counts=%s " "pending=%s",
            inserted,
            snap,
            counts,
            pending,
        )
        result = {
            "inserted": inserted,
            "for_week": snap.isoformat(),
            "counts": counts,
            "pending": pending,
        }
    finally:
        con.close()
    # add_next_week() commits internally; only now can readers see the new week,
    # so this is the right moment to tell every connected dashboard to refresh.
    live.bump("scheduled ingest")
    return result


def interval_seconds(argv=None) -> int:
    """``--interval N`` (or ``--interval=N``) overrides the env default."""
    args = list(sys.argv[1:] if argv is None else argv)
    for i, arg in enumerate(args):
        raw = None
        if arg == "--interval" and i + 1 < len(args):
            raw = args[i + 1]
        elif arg.startswith("--interval="):
            raw = arg.split("=", 1)[1]
        if raw is None:
            continue
        try:
            return max(0, int(raw))
        except ValueError:
            logger.warning("ignoring non-numeric --interval value: %s", raw)
            return 0
    return max(0, settings.ingest_interval_seconds)


def main() -> int:
    if "--once" in sys.argv:
        print("one-shot ingest:", run_ingest())
        return 0

    from apscheduler.schedulers.background import BackgroundScheduler

    sched = BackgroundScheduler(timezone="UTC")
    every = interval_seconds()
    if every > 0:
        sched.add_job(
            run_ingest,
            "interval",
            seconds=every,
            id="interval-price-ingest",
            max_instances=1,
            coalesce=True,
        )
        logger.info("scheduler started (ingesting every %ss). Ctrl+C to stop.", every)
    else:
        sched.add_job(
            run_ingest,
            "cron",
            day_of_week=CRON_DAY_OF_WEEK,
            hour=CRON_HOUR,
            minute=0,
            id="weekly-price-ingest",
            max_instances=1,
            coalesce=True,
        )
        logger.info(
            "scheduler started (cron %s %s:00 UTC). Ctrl+C to stop.", CRON_DAY_OF_WEEK, CRON_HOUR
        )
    sched.start()
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown(wait=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
