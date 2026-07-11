#!/usr/bin/env python3
"""LinuxNetWatch: per-app bandwidth usage monitor."""
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from netwatch import db

REFRESH_MS = 5000
RANGE_LABELS = ["5m", "10m", "1h", "3h", "7h", "1d", "2d", "7d", "30d"]


def human_bytes(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def human_duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h {minutes % 60}m"
    days = hours // 24
    return f"{days}d {hours % 24}h"


class NetWatchWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="LinuxNetWatch")
        self.set_default_size(640, 420)
        self.set_border_width(8)

        try:
            self.conn = db.connect()
        except Exception as exc:
            self.conn = None
            self._db_error = str(exc)
        else:
            self._db_error = None

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(root)

        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        root.pack_start(top_bar, False, False, 0)

        top_bar.pack_start(Gtk.Label(label="Time range:"), False, False, 0)
        self.range_combo = Gtk.ComboBoxText()
        for label in RANGE_LABELS:
            self.range_combo.append_text(label)
        self.range_combo.set_active(RANGE_LABELS.index("1h"))
        self.range_combo.connect("changed", lambda _w: self.refresh())
        top_bar.pack_start(self.range_combo, False, False, 0)

        self.totals_label = Gtk.Label(label="")
        top_bar.pack_end(self.totals_label, False, False, 0)

        self.status_label = Gtk.Label(label="", xalign=0)
        self.status_label.get_style_context().add_class("dim-label")
        root.pack_start(self.status_label, False, False, 0)

        # App, Download, Upload, Total
        self.store = Gtk.ListStore(str, str, str, str, int)
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_fixed_height_mode(True)
        for i, title in enumerate(["App", "Download", "Upload", "Total"]):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=i)
            column.set_resizable(True)
            column.set_sort_column_id(i if i == 0 else 4)
            column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            if i == 0:
                renderer.set_property("ellipsize", 3)  # PANGO_ELLIPSIZE_END
                column.set_fixed_width(320)
                column.set_expand(True)
            else:
                column.set_fixed_width(100)
            self.view.append_column(column)
        self.view.connect("row-activated", self.on_row_activated)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(self.view)
        root.pack_start(scroller, True, True, 0)

        if self._db_error:
            root.pack_start(
                Gtk.Label(label=f"Database unavailable: {self._db_error}\n"
                                 "Is the linuxnetwatch collector service running?"),
                False, False, 0,
            )

        self.show_all()
        GLib.timeout_add(REFRESH_MS, self._on_timeout)
        self.refresh()

    def _on_timeout(self):
        self.refresh()
        return True

    def current_range(self):
        return self.range_combo.get_active_text() or "1h"

    def refresh(self):
        if self.conn is None:
            return
        range_key = self.current_range()
        self.store.clear()
        for app_name, sent, recv in db.totals_by_app(self.conn, range_key):
            sent = sent or 0
            recv = recv or 0
            self.store.append([
                app_name,
                human_bytes(recv),
                human_bytes(sent),
                human_bytes(sent + recv),
                sent + recv,
            ])
        total_sent, total_recv = db.grand_totals(self.conn, range_key)
        self.totals_label.set_text(
            f"Total download: {human_bytes(total_recv)}   "
            f"Total upload: {human_bytes(total_sent)}   "
            f"Combined: {human_bytes(total_sent + total_recv)}"
        )
        self._update_status_label(range_key)

    def _update_status_label(self, range_key):
        earliest = db.earliest_sample_ts(self.conn)
        if earliest is None:
            self.status_label.set_text("No data collected yet.")
            return
        collecting_seconds = time.time() - earliest
        range_seconds = db.TIME_RANGES[range_key]
        started = datetime.fromtimestamp(earliest).strftime("%H:%M:%S")
        if collecting_seconds < range_seconds:
            self.status_label.set_text(
                f"Collecting since {started} — only {human_duration(collecting_seconds)} of "
                f"data so far, less than the selected {range_key} range."
            )
        else:
            self.status_label.set_text(f"Collecting since {started}.")

    def on_row_activated(self, view, path, column):
        model = view.get_model()
        app_name = model[path][0]
        download = model[path][1]
        upload = model[path][2]
        total = model[path][3]
        self.show_app_dialog(app_name, download, upload, total)

    def show_app_dialog(self, app_name, download, upload, total):
        dialog = Gtk.Dialog(title=app_name, transient_for=self, modal=True)
        dialog.set_default_size(360, 200)
        box = dialog.get_content_area()
        box.set_border_width(12)
        box.set_spacing(6)

        box.add(Gtk.Label(label=f"Download ({self.current_range()}): {download}", xalign=0))
        box.add(Gtk.Label(label=f"Upload ({self.current_range()}): {upload}", xalign=0))
        box.add(Gtk.Label(label=f"Total: {total}", xalign=0))
        box.add(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        note = Gtk.Label(
            label="Blocking network access and setting bandwidth/data limits\n"
                  "for this app are coming in a future update.",
            xalign=0,
        )
        note.set_line_wrap(True)
        box.add(note)

        block_button = Gtk.Button(label="Disable network access (coming soon)")
        block_button.set_sensitive(False)
        box.add(block_button)

        limit_button = Gtk.Button(label="Set bandwidth/data limit (coming soon)")
        limit_button.set_sensitive(False)
        box.add(limit_button)

        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        dialog.show_all()
        dialog.run()
        dialog.destroy()


def main():
    win = NetWatchWindow()
    win.connect("destroy", Gtk.main_quit)
    Gtk.main()


if __name__ == "__main__":
    main()
