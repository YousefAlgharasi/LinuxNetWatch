"""SQLite storage for per-app bandwidth samples."""
import sqlite3
import time

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


def earliest_sample_ts(conn):
    row = conn.execute("SELECT MIN(ts) FROM usage_samples").fetchone()
    return row[0]
