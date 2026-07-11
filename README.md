# LinuxNetWatch

A per-app internet usage monitor for Zorin OS — see how much data each
application has downloaded/uploaded, filterable by time range (5m, 10m, 1h,
3h, 7h, 1d, 2d, 7d, 30d).

This is **stage 1** of the project: monitoring and history. Per-app network
blocking and bandwidth/data limits are planned next (see Roadmap).

## How it works

- **Collector** (`netwatch/collector.py`): a small background service that
  runs [`nethogs`](https://github.com/raboof/nethogs) in trace mode, which
  reports live per-process send/receive rates. It integrates those rates
  into byte counts and logs them to a SQLite database
  (`/var/lib/linuxnetwatch/usage.db`) every 5 seconds. Runs as a root
  systemd service (`nethogs` needs raw socket access).
- **Viewer** (`netwatch/window.py`): a GTK app you run as your normal user.
  Lists every app with download/upload/total for the selected time range,
  plus a combined total at the top. Double-click any app for a detail
  popup (block/limit controls are present but disabled for now — coming in
  a later update).

## Install

```bash
git clone https://github.com/YousefAlgharasi/LinuxNetWatch
cd LinuxNetWatch
chmod +x install.sh
./install.sh
```

This installs `nethogs` + GTK dependencies, sets up and starts the collector
as a systemd service, and installs the `linuxnetwatch` viewer command plus
an app-menu shortcut.

## Run

Launch **LinuxNetWatch** from the app menu, or run `linuxnetwatch`. Pick a
time range from the dropdown, and double-click any app row for details.

Check the collector is healthy any time with:

```bash
systemctl status linuxnetwatch-collector.service
```

## Roadmap

- **Block an app's network access**: via an `nftables` rule matched on the
  app's cgroup (needs the app launched/tracked in its own systemd scope).
- **Per-app bandwidth throttle / hard data cap**: via `tc` (traffic control)
  cgroup shaping, or an auto-block once a configured MB limit is hit within
  a period — this is what the "Set bandwidth/data limit" button in the
  detail popup will wire up to.
- **Tray icon** with live combined speed, not just the main window.
