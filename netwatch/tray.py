#!/usr/bin/env python3
"""LinuxNetWatch tray icon: shows live combined bandwidth total, opens the full viewer."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
from gi.repository import AppIndicator3, GLib, Gtk

from netwatch import db
from netwatch.window import NetWatchWindow, human_bytes

APP_ID = "linuxnetwatch"
REFRESH_MS = 5000
LABEL_RANGE = "1d"


class NetWatchTray:
    def __init__(self):
        self.indicator = AppIndicator3.Indicator.new(
            APP_ID, "network-transmit-receive", AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

        try:
            self.conn = db.connect()
        except Exception:
            self.conn = None

        self.window = None

        self.menu = Gtk.Menu()

        self.totals_item = Gtk.MenuItem(label="Download: --   Upload: --")
        self.totals_item.set_sensitive(False)
        self.menu.append(self.totals_item)

        self.menu.append(Gtk.SeparatorMenuItem())

        open_item = Gtk.MenuItem(label="Open LinuxNetWatch")
        open_item.connect("activate", self.on_open)
        self.menu.append(open_item)

        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", Gtk.main_quit)
        self.menu.append(quit_item)

        self.menu.show_all()
        self.indicator.set_menu(self.menu)

        GLib.timeout_add(REFRESH_MS, self.refresh)
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
        sent, recv = db.grand_totals(self.conn, LABEL_RANGE)
        label = f"↓{human_bytes(recv)} ↑{human_bytes(sent)}"
        self.indicator.set_label(label, "")
        self.totals_item.set_label(
            f"Last 24h: Download {human_bytes(recv)}   Upload {human_bytes(sent)}"
        )
        return True


def main():
    NetWatchTray()
    Gtk.main()


if __name__ == "__main__":
    main()
