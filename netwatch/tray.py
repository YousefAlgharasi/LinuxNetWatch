#!/usr/bin/env python3
"""DataPulse tray icon: shows live combined bandwidth total, opens the full viewer."""
import fcntl
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
from gi.repository import AppIndicator3, GLib, Gtk

from netwatch import db, netctl, prefs
from netwatch.window import RANGE_LABELS, NetWatchWindow, human_bytes

APP_ID = "datapulse"
REFRESH_MS = 5000
DEFAULT_RANGE = "1h"
LOCK_PATH = os.path.expanduser("~/.cache/datapulse-tray.lock")


def acquire_single_instance_lock():
    """Refuse to start a second tray instance.

    AppIndicator registers over DBus under a fixed app id; a second instance
    (e.g. a leftover from a Ctrl+C'd manual test) silently fails to show an
    icon instead of erroring, which looks like "the icon randomly doesn't
    appear" rather than what it actually is.
    """
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    lock_file = open(LOCK_PATH, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("DataPulse tray is already running.", file=sys.stderr)
        sys.exit(1)
    return lock_file  # keep a reference so the lock isn't released by GC


class NetWatchTray:
    def __init__(self):
        self.indicator = AppIndicator3.Indicator.new(
            APP_ID, "datapulse", AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

        try:
            self.conn = db.connect()
        except Exception:
            self.conn = None

        self.window = None
        saved_range = prefs.get_range(DEFAULT_RANGE)
        self.range_key = saved_range if saved_range in RANGE_LABELS else DEFAULT_RANGE
        self._last_event_check = time.time()

        self.menu = Gtk.Menu()

        self.totals_item = Gtk.MenuItem(label="Download: --   Upload: --")
        self.totals_item.set_sensitive(False)
        self.menu.append(self.totals_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        range_label_item = Gtk.MenuItem(label="Show total for:")
        range_label_item.set_sensitive(False)
        self.menu.append(range_label_item)

        self.range_items = {}
        group = None
        for label in RANGE_LABELS:
            item = Gtk.RadioMenuItem.new_with_label_from_widget(group, label)
            group = item
            item.set_active(label == self.range_key)
            item.connect("toggled", self.on_range_toggled, label)
            self.menu.append(item)
            self.range_items[label] = item

        self.menu.append(Gtk.SeparatorMenuItem())

        open_item = Gtk.MenuItem(label="Open DataPulse")
        open_item.connect("activate", self.on_open)
        self.menu.append(open_item)

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", Gtk.main_quit)
        self.menu.append(quit_item)

        self.menu.show_all()
        self.indicator.set_menu(self.menu)

        GLib.timeout_add(REFRESH_MS, self.refresh)
        self.refresh()

    def on_range_toggled(self, widget, label):
        if not widget.get_active():
            return
        self.range_key = label
        prefs.set_range(label)
        self.refresh()

    def on_open(self, _widget):
        if self.window is not None:
            self.window.present()
            return
        self.window = NetWatchWindow()
        self.window.connect("destroy", self.on_window_destroy)

    def on_window_destroy(self, _widget):
        self.window = None

    def refresh(self):
        if self.conn is None:
            return True
        sent, recv = db.grand_totals(self.conn, self.range_key)
        label = f"↓{human_bytes(recv)} ↑{human_bytes(sent)}"
        self.indicator.set_label(label, "")
        self.totals_item.set_label(
            f"{self.range_key}: Download {human_bytes(recv)}   Upload {human_bytes(sent)}"
        )
        self._check_events()
        return True

    def _check_events(self):
        try:
            events = netctl.get_events_since(self._last_event_check)
        except (OSError, ValueError):
            return
        self._last_event_check = time.time()
        for event in events:
            self._notify(
                f"DataPulse: {event['app_name']} blocked",
                event["reason"].capitalize(),
            )

    def _notify(self, title, body):
        try:
            subprocess.run(["notify-send", title, body], check=False)
        except FileNotFoundError:
            pass


def main():
    lock = acquire_single_instance_lock()
    NetWatchTray()
    Gtk.main()
    del lock


if __name__ == "__main__":
    main()
