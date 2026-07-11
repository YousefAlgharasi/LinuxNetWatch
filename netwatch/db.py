"""SQLite storage for per-app bandwidth samples."""
import sqlite3
import time
from datetime import datetime

DB_PATH = "/var/lib/linuxnetwatch/usage.db"

TIME_RANGES = {
    "5m": 5 * 60,
    "10m": 10 * 60,
    "1h": 60 * 60,
    "3h": 3 * 60 * 60,
    "7h": 7 * 60 * 60,
    "1d": 24 * 60 * 60,
    "2d": 2 * 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60,
    "30d": 30 * 24 * 60 * 60,
}


def connect(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            app_name TEXT NOT NULL,
            sent_bytes INTEGER NOT NULL,
            recv_bytes INTEGER NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage_samples (ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_app ON usage_samples (app_name)")
    conn.commit()
    return conn


def insert_sample(conn, app_name, sent_bytes, recv_bytes, ts=None):
    conn.execute(
        "INSERT INTO usage_samples (ts, app_name, sent_bytes, recv_bytes) VALUES (?, ?, ?, ?)",
        (ts if ts is not None else time.time(), app_name, sent_bytes, recv_bytes),
    )


def totals_by_app(conn, range_key):
    """Return list of (app_name, total_sent, total_recv) for the given time range, newest usage first."""
    seconds = TIME_RANGES[range_key]
    since = time.time() - seconds
    cursor = conn.execute(
        """
        SELECT app_name, SUM(sent_bytes), SUM(recv_bytes)
        FROM usage_samples
        WHERE ts >= ?
        GROUP BY app_name
        ORDER BY (SUM(sent_bytes) + SUM(recv_bytes)) DESC
        """,
        (since,),
    )
    return cursor.fetchall()


def grand_totals(conn, range_key):
    seconds = TIME_RANGES[range_key]
    since = time.time() - seconds
    row = conn.execute(
        "SELECT SUM(sent_bytes), SUM(recv_bytes) FROM usage_samples WHERE ts >= ?",
        (since,),
    ).fetchone()
    return row[0] or 0, row[1] or 0


def prune_older_than(conn, seconds):
    conn.execute("DELETE FROM usage_samples WHERE ts < ?", (time.time() - seconds,))


def app_totals_since(conn, app_name, since_ts):
    row = conn.execute(
        "SELECT SUM(sent_bytes), SUM(recv_bytes) FROM usage_samples WHERE app_name = ? AND ts >= ?",
        (app_name, since_ts),
    ).fetchone()
    return row[0] or 0, row[1] or 0


def earliest_sample_ts(conn):
    row = conn.execute("SELECT MIN(ts) FROM usage_samples").fetchone()
    return row[0]


def today_midnight_ts():
    """Start of the current calendar day, local time."""
    now = datetime.now()
    return datetime(now.year, now.month, now.day).timestamp()


def app_totals_today(conn, app_name):
    """Usage since local midnight, for calendar-day data caps."""
    return app_totals_since(conn, app_name, today_midnight_ts())


def hourly_buckets(conn, app_name, hours=24):
    """Return (hour_start_ts, sent_bytes, recv_bytes) for each of the last N hours, oldest first."""
    since = time.time() - hours * 3600
    rows = conn.execute(
        "SELECT ts, sent_bytes, recv_bytes FROM usage_samples WHERE app_name = ? AND ts >= ?",
        (app_name, since),
    ).fetchall()
    buckets = {}
    for ts, sent, recv in rows:
        bucket = int(ts // 3600) * 3600
        b_sent, b_recv = buckets.get(bucket, (0, 0))
        buckets[bucket] = (b_sent + sent, b_recv + recv)
    now_bucket = int(time.time() // 3600) * 3600
    result = []
    for i in range(hours - 1, -1, -1):
        bucket = now_bucket - i * 3600
        sent, recv = buckets.get(bucket, (0, 0))
        result.append((bucket, sent, recv))
    return result


def rows_for_export(conn, range_key):
    """Return (ts, app_name, sent_bytes, recv_bytes) rows for the given time range, oldest first."""
    seconds = TIME_RANGES[range_key]
    since = time.time() - seconds
    return conn.execute(
        "SELECT ts, app_name, sent_bytes, recv_bytes FROM usage_samples WHERE ts >= ? ORDER BY ts",
        (since,),
    ).fetchall()
