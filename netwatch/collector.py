#!/usr/bin/env python3
"""Background collector: samples per-process bandwidth via nethogs and stores it in SQLite.

Must run as root (nethogs needs raw socket access). Intended to run as a
systemd service; see install.sh.
"""
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from netwatch import db, netctl

INTERVAL_SECONDS = 5
PRUNE_AFTER_SECONDS = 31 * 24 * 60 * 60  # keep ~31 days
PRUNE_EVERY_N_SAMPLES = 200
DAILY_CAP_SECONDS = 24 * 60 * 60

# nethogs -t line: "<program path>/<pid>/<uid>\t<sent KB/s>\t<recv KB/s>"
LINE_RE = re.compile(r"^(.+)/(\d+)/(\d+)\t([\d.]+)\t([\d.]+)$")


def app_name_from_path(path):
    if path in ("unknown TCP", "TIME_WAIT", "unknown UDP"):
        return path
    # Some sandboxed processes (e.g. Chromium/Brave renderers) report their
    # full command line, flags included, instead of a clean binary path.
    binary = path.split(" ", 1)[0]
    return os.path.basename(binary.rstrip("/")) or path


def run():
    os.makedirs(os.path.dirname(db.DB_PATH), exist_ok=True)
    os.chmod(os.path.dirname(db.DB_PATH), 0o755)
    conn = db.connect()
    os.chmod(db.DB_PATH, 0o644)
    sample_count = 0

    try:
        netctl.apply_all_rules()
    except netctl.NetCtlError as exc:
        print(f"warning: failed to apply saved network rules: {exc}", file=sys.stderr)

    proc = subprocess.Popen(
        ["nethogs", "-t", "-d", str(INTERVAL_SECONDS)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )

    pending = {}

    def flush():
        nonlocal sample_count
        if not pending:
            return
        now = time.time()
        for app_name, (sent_kbps, recv_kbps) in pending.items():
            sent_bytes = int(sent_kbps * 1024 * INTERVAL_SECONDS)
            recv_bytes = int(recv_kbps * 1024 * INTERVAL_SECONDS)
            if sent_bytes or recv_bytes:
                db.insert_sample(conn, app_name, sent_bytes, recv_bytes, ts=now)
        conn.commit()
        pending.clear()
        sample_count += 1
        if sample_count % PRUNE_EVERY_N_SAMPLES == 0:
            db.prune_older_than(conn, PRUNE_AFTER_SECONDS)
            conn.commit()

        rules = netctl.load_rules()
        if rules:
            try:
                netctl.classify_running_processes(rules)
            except OSError:
                pass
            for app_name, entry in rules.items():
                cap_mb = entry.get("daily_cap_mb")
                if not cap_mb or entry.get("blocked"):
                    continue
                sent, recv = db.app_totals_since(conn, app_name, now - DAILY_CAP_SECONDS)
                if (sent + recv) >= cap_mb * 1024 * 1024:
                    try:
                        netctl.set_blocked(app_name, True)
                        print(f"{app_name} hit its {cap_mb}MB daily cap, blocking network access")
                    except netctl.NetCtlError as exc:
                        print(f"warning: failed to auto-block {app_name}: {exc}", file=sys.stderr)

    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        if line == "Refreshing:":
            flush()
            continue
        match = LINE_RE.match(line)
        if not match:
            continue
        path, _pid, _uid, sent_kbps, recv_kbps = match.groups()
        app_name = app_name_from_path(path)
        prev_sent, prev_recv = pending.get(app_name, (0.0, 0.0))
        pending[app_name] = (prev_sent + float(sent_kbps), prev_recv + float(recv_kbps))


if __name__ == "__main__":
    run()
