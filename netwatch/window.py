#!/usr/bin/env python3
"""LinuxNetWatch: per-app bandwidth usage monitor."""
import os
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csv

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from netwatch import db, netctl

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

        rules_button = Gtk.Button(label="Rules")
        rules_button.connect("clicked", lambda _w: self.show_rules_dialog())
        top_bar.pack_start(rules_button, False, False, 0)

        killswitch_button = Gtk.Button(label="Kill Switch")
        killswitch_button.connect("clicked", lambda _w: self.show_killswitch_dialog())
        top_bar.pack_start(killswitch_button, False, False, 0)

        export_button = Gtk.Button(label="Export CSV")
        export_button.connect("clicked", lambda _w: self.on_export_csv())
        top_bar.pack_start(export_button, False, False, 0)

        self.totals_label = Gtk.Label(label="")
        top_bar.pack_end(self.totals_label, False, False, 0)

        self.status_label = Gtk.Label(label="", xalign=0)
        self.status_label.get_style_context().add_class("dim-label")
        root.pack_start(self.status_label, False, False, 0)

        self.killswitch_label = Gtk.Label(label="", xalign=0)
        self.killswitch_label.get_style_context().add_class("dim-label")
        root.pack_start(self.killswitch_label, False, False, 0)

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
        self._update_killswitch_label()

    def _update_killswitch_label(self):
        try:
            state = netctl.load_killswitch_state()
        except (OSError, ValueError):
            state = {"enabled": False, "allowed": []}
        if state.get("enabled"):
            allowed = ", ".join(state.get("allowed", [])) or "(none)"
            self.killswitch_label.set_text(f"Kill switch ON — only allowed: {allowed}")
        else:
            self.killswitch_label.set_text("")

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
        rules = netctl.load_rules()
        entry = rules.get(app_name, {})

        dialog = Gtk.Dialog(title=app_name, transient_for=self, modal=True)
        dialog.set_default_size(420, 440)
        box = dialog.get_content_area()
        box.set_border_width(12)
        box.set_spacing(6)

        box.add(Gtk.Label(label=f"Download ({self.current_range()}): {download}", xalign=0))
        box.add(Gtk.Label(label=f"Upload ({self.current_range()}): {upload}", xalign=0))
        box.add(Gtk.Label(label=f"Total: {total}", xalign=0))
        box.add(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        box.add(Gtk.Label(label="Last 24 hours:", xalign=0))
        chart = Gtk.DrawingArea()
        chart.set_size_request(-1, 100)
        chart.connect("draw", self.on_draw_chart, app_name)
        box.add(chart)
        box.add(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        block_check = Gtk.CheckButton(label="Disable network access")
        block_check.set_active(bool(entry.get("blocked")))
        block_check.connect("toggled", self.on_block_toggled, app_name)
        box.add(block_check)

        limit_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        limit_row.add(Gtk.Label(label="Upload limit (KB/s, 0 = unlimited):"))
        limit_spin = Gtk.SpinButton.new_with_range(0, 100000, 10)
        limit_spin.set_value((entry.get("limit_kbps") or 0) / 8)  # stored as kbit/s
        limit_row.pack_start(limit_spin, False, False, 0)
        box.add(limit_row)

        cap_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        cap_row.add(Gtk.Label(label="Daily data cap (MB, 0 = none):"))
        cap_spin = Gtk.SpinButton.new_with_range(0, 1000000, 50)
        cap_spin.set_value(entry.get("daily_cap_mb") or 0)
        cap_row.pack_start(cap_spin, False, False, 0)
        box.add(cap_row)

        note = Gtk.Label(
            label="Note: only upload can be rate-limited (Linux can't classify\n"
                  "incoming traffic by process before it's already received).\n"
                  "Download usage still counts toward the daily data cap.",
            xalign=0,
        )
        note.set_line_wrap(True)
        box.add(note)

        apply_button = Gtk.Button(label="Apply")
        apply_button.connect(
            "clicked", self.on_apply_limits, app_name, limit_spin, cap_spin, dialog
        )
        box.add(apply_button)

        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def on_draw_chart(self, widget, cr, app_name):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()

        cr.set_source_rgb(0.15, 0.15, 0.17)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        if self.conn is None:
            return
        buckets = db.hourly_buckets(self.conn, app_name, hours=24)
        totals = [sent + recv for _ts, sent, recv in buckets]
        max_total = max(totals) if totals and max(totals) > 0 else 1

        n = len(buckets)
        bar_width = width / n
        for i, total in enumerate(totals):
            bar_height = (total / max_total) * (height - 4)
            x = i * bar_width
            cr.set_source_rgb(0.30, 0.55, 0.90)
            cr.rectangle(x + 1, height - bar_height, max(bar_width - 2, 1), bar_height)
            cr.fill()

    def on_block_toggled(self, widget, app_name):
        action = "block" if widget.get_active() else "unblock"
        self.run_ctl(action, app_name)

    def on_apply_limits(self, _button, app_name, limit_spin, cap_spin, dialog):
        kbps = int(limit_spin.get_value()) * 8  # KB/s -> kbit/s for tc
        cap_mb = cap_spin.get_value()
        if kbps > 0:
            self.run_ctl("limit", app_name, str(kbps))
        else:
            self.run_ctl("unlimit", app_name)
        if cap_mb > 0:
            self.run_ctl("daily-cap", app_name, str(cap_mb))
        else:
            self.run_ctl("daily-cap-clear", app_name)
        dialog.destroy()

    def run_ctl(self, *args):
        cli_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ctl_cli.py")
        try:
            subprocess.run(["pkexec", sys.executable, cli_path, *args], check=True)
        except subprocess.CalledProcessError as exc:
            self.show_error(f"Failed to apply network rule: {exc}")
        except FileNotFoundError:
            self.show_error("pkexec not found. Install polkit to use block/limit controls.")

    def show_rules_dialog(self):
        rules = netctl.load_rules()

        dialog = Gtk.Dialog(title="Active Rules", transient_for=self, modal=True)
        dialog.set_default_size(480, 320)
        box = dialog.get_content_area()
        box.set_border_width(12)

        active = {
            name: entry for name, entry in rules.items()
            if entry.get("blocked") or entry.get("limit_kbps") or entry.get("daily_cap_mb")
        }

        if not active:
            box.add(Gtk.Label(label="No apps are currently blocked, limited, or capped."))
        else:
            store = Gtk.ListStore(str, str, str, str)
            for name, entry in active.items():
                store.append([
                    name,
                    "Yes" if entry.get("blocked") else "",
                    f"{entry['limit_kbps'] // 8} KB/s" if entry.get("limit_kbps") else "",
                    f"{entry['daily_cap_mb']:g} MB" if entry.get("daily_cap_mb") else "",
                ])
            view = Gtk.TreeView(model=store)
            for i, title in enumerate(["App", "Blocked", "Upload limit", "Daily cap"]):
                renderer = Gtk.CellRendererText()
                column = Gtk.TreeViewColumn(title, renderer, text=i)
                view.append_column(column)
            view.connect(
                "row-activated",
                lambda v, path, col: (
                    dialog.destroy(),
                    self.show_app_dialog(v.get_model()[path][0], "-", "-", "-"),
                ),
            )
            scroller = Gtk.ScrolledWindow()
            scroller.add(view)
            box.pack_start(scroller, True, True, 0)
            box.add(Gtk.Label(
                label="Double-click a row to edit or clear that app's rules.",
                xalign=0,
            ))

        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def show_killswitch_dialog(self):
        state = netctl.load_killswitch_state()
        known_apps = sorted({name for name, _s, _r in db.totals_by_app(self.conn, "30d")}
                             if self.conn else [])

        dialog = Gtk.Dialog(title="Kill Switch", transient_for=self, modal=True)
        dialog.set_default_size(360, 420)
        box = dialog.get_content_area()
        box.set_border_width(12)
        box.set_spacing(6)

        warning = Gtk.Label(
            label="When enabled, every app EXCEPT the ones checked below loses "
                  "network access (DNS and loopback stay allowed). This affects "
                  "the whole machine, not just apps LinuxNetWatch already knows "
                  "about.",
            xalign=0,
        )
        warning.set_line_wrap(True)
        box.add(warning)

        enabled_check = Gtk.CheckButton(label="Enable kill switch")
        enabled_check.set_active(bool(state.get("enabled")))
        box.add(enabled_check)

        box.add(Gtk.Label(label="Allowed apps:", xalign=0))
        scroller = Gtk.ScrolledWindow()
        scroller.set_size_request(-1, 220)
        allowed_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scroller.add(allowed_list)
        box.pack_start(scroller, True, True, 0)

        checks = {}
        allowed_set = set(state.get("allowed", []))
        for name in known_apps:
            check = Gtk.CheckButton(label=name)
            check.set_active(name in allowed_set)
            allowed_list.pack_start(check, False, False, 0)
            checks[name] = check

        apply_button = Gtk.Button(label="Apply")
        apply_button.connect(
            "clicked", self.on_apply_killswitch, enabled_check, checks, dialog
        )
        box.add(apply_button)

        dialog.add_button("Close", Gtk.ResponseType.CLOSE)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def on_apply_killswitch(self, _button, enabled_check, checks, dialog):
        if enabled_check.get_active():
            allowed = [name for name, check in checks.items() if check.get_active()]
            self.run_ctl("killswitch-enable", ",".join(allowed))
        else:
            self.run_ctl("killswitch-disable")
        dialog.destroy()
        self.refresh()

    def on_export_csv(self):
        chooser = Gtk.FileChooserDialog(
            title="Export usage history as CSV", transient_for=self,
            action=Gtk.FileChooserAction.SAVE,
        )
        chooser.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.OK,
        )
        chooser.set_current_name(f"linuxnetwatch_{self.current_range()}.csv")
        response = chooser.run()
        path = chooser.get_filename()
        chooser.destroy()
        if response != Gtk.ResponseType.OK or not path:
            return
        try:
            rows = db.rows_for_export(self.conn, self.current_range())
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "app_name", "sent_bytes", "recv_bytes"])
                for ts, app_name, sent, recv in rows:
                    writer.writerow([datetime.fromtimestamp(ts).isoformat(), app_name, sent, recv])
        except OSError as exc:
            self.show_error(f"Failed to export CSV: {exc}")

    def show_error(self, message):
        dialog = Gtk.MessageDialog(
            transient_for=self, flags=0, message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK, text=message,
        )
        dialog.run()
        dialog.destroy()


def main():
    win = NetWatchWindow()
    win.connect("destroy", Gtk.main_quit)
    Gtk.main()


if __name__ == "__main__":
    main()
