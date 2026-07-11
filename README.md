# LinuxNetWatch

A per-app internet usage monitor and controller for Zorin OS — see how much
data each application has downloaded/uploaded (filterable by time range:
5m, 10m, 1h, 3h, 7h, 1d, 2d, 7d, 30d), block an app's network access, cap its
upload speed, or auto-block it once it hits a daily data limit.

## How it works

- **Collector** (`netwatch/collector.py`): a background root systemd service
  that runs [`nethogs`](https://github.com/raboof/nethogs) in trace mode to
  get live per-process send/receive rates, integrates them into byte counts,
  and logs them to SQLite (`/var/lib/linuxnetwatch/usage.db`) every 5
  seconds. It also re-applies saved block/limit rules on startup, keeps
  reclassifying newly spawned processes into their app's control group, and
  auto-blocks an app once it crosses its configured daily data cap.
- **Viewer** (`netwatch/window.py`): a GTK app you run as your normal user.
  Lists every app with download/upload/total for the selected time range,
  plus a combined total. Double-click any app for a detail popup: a
  "Disable network access" checkbox, an upload-limit field (KB/s), and a
  daily data cap field (MB).
- **Enforcement** (`netwatch/netctl.py`): matching processes are classified
  into a `net_cls` cgroup per app. `iptables` drops outbound traffic tagged
  with a blocked app's cgroup; `tc` (traffic control, htb) shapes upload
  bandwidth for a rate-limited app's cgroup. The GUI invokes these changes
  as root via `pkexec` (the standard "enter your password once" desktop
  prompt) — there's no need to run the viewer itself as root.

### Important limitation: upload-only rate limiting

Linux can only classify traffic by cgroup on the way **out** — a socket is
tied to the process that owns it. Incoming (download) packets arrive off
the wire before the kernel has associated them with any process, so
per-app **download throttling isn't achievable** this way (this is a kernel
architecture limitation, not something specific to this tool). What does
work in both directions:

- **Blocking** — cutting outbound traffic also kills downloads in practice,
  since no request means no response.
- **Daily data cap** — counts both download and upload from the same usage
  history, and auto-blocks the app once the cap is hit.

Only the *live rate limit* (KB/s) is upload-only.

## Install

```bash
git clone https://github.com/YousefAlgharasi/LinuxNetWatch
cd LinuxNetWatch
chmod +x install.sh
./install.sh
```

This installs `nethogs`, `iptables`, `iproute2` (for `tc`), `policykit-1`
(for `pkexec`), and GTK dependencies; sets up and starts the collector as a
systemd service; and installs the `linuxnetwatch` viewer command plus an
app-menu shortcut.

## Run

LinuxNetWatch starts automatically on login as a **tray icon** showing your
last-24h combined download/upload total. Click it and choose "Open
LinuxNetWatch" for the full window: pick a time range from the dropdown, and
double-click any app row to see details and set controls. Checking "Disable
network access" or clicking "Apply" on a limit will prompt for your password
via `pkexec` the first time.

Check the collector is healthy any time with:

```bash
systemctl status linuxnetwatch-collector.service
```

## Roadmap

- A dedicated "Rules" view listing every app with an active block/limit,
  instead of only being visible per-app in the detail popup.
