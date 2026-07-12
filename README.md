# DataPulse

*(repo name stayed `LinuxNetWatch` on GitHub; the app itself is called
DataPulse — see below if you're coming from an older install.)*

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
  plus a combined total. Double-click any app for a detail popup with a
  24-hour usage chart, a "Disable network access" checkbox, an upload-limit
  field (KB/s), and a daily data cap field (MB). The toolbar also has:
  - **Rules** — a single list of every app with an active block/limit/cap,
    instead of having to open each app individually to check.
  - **Kill Switch** — block all outbound traffic *except* an allow-list of
    apps you pick (a "only these apps get internet" mode).
  - **Export CSV** — dump the selected time range's raw history to a file.
- **Enforcement** (`netwatch/netctl.py`): matching processes are classified
  into a `net_cls` cgroup per app. `iptables` drops outbound traffic tagged
  with a blocked app's cgroup; `tc` (traffic control, htb) shapes upload
  bandwidth for a rate-limited app's cgroup. The GUI invokes these changes
  as root via `pkexec` (the standard "enter your password once" desktop
  prompt) — there's no need to run the viewer itself as root. Daily data
  caps reset at local midnight (not a rolling 24h window), and an app
  auto-blocked by a cap is automatically un-blocked the next day. Getting
  auto-blocked also triggers a desktop notification from the tray icon.

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

### Option A: .deb package (easiest)

Download the prebuilt package from
[`dist/datapulse_0.3.0_all.deb`](https://github.com/YousefAlgharasi/LinuxNetWatch/raw/main/dist/datapulse_0.3.0_all.deb)
and install it:

```bash
wget https://github.com/YousefAlgharasi/LinuxNetWatch/raw/main/dist/datapulse_0.3.0_all.deb
sudo apt install ./datapulse_0.3.0_all.deb
```

`apt` resolves and installs all dependencies automatically, sets up the
collector as a systemd service, and enables autostart for every user
account on the machine (via `/etc/xdg/autostart`) — no manual steps needed.
To uninstall: `sudo apt remove datapulse` (or `purge` to also delete
collected history).

If you have an old `linuxnetwatch` `.deb` installed from before the rename,
this package `Conflicts`/`Replaces` it, so `apt install` will cleanly swap
it out.

To build the `.deb` yourself instead of downloading it:

```bash
git clone https://github.com/YousefAlgharasi/LinuxNetWatch
cd LinuxNetWatch
./packaging/build-deb.sh 0.3.0
sudo apt install ./datapulse_0.3.0_all.deb
```

### Option B: install script (for development)

```bash
git clone https://github.com/YousefAlgharasi/LinuxNetWatch
cd LinuxNetWatch
chmod +x install.sh
./install.sh
```

This installs the same dependencies and systemd service but only sets up
autostart/shortcuts for your own user account, and copies source files
instead of packaging them — more convenient when you're editing the code.
If it detects an old `linuxnetwatch-collector.service` from before the
rename, it disables/removes it automatically.

## Run

DataPulse starts automatically on login as a **tray icon** showing your
combined download/upload total for a time range you pick right from the tray
menu (defaults to 1h — same range list as the full window: 5m, 10m, 1h, 3h,
7h, 1d, 2d, 7d, 30d). Click "Open DataPulse" for the full window: pick a
time range from the dropdown, and double-click any app row to see details
and set controls. Checking "Disable network access" or clicking "Apply" on a
limit will prompt for your password via `pkexec` the first time.

Only one tray instance can run at a time — starting a second one (e.g. by
running it manually while it's already active) exits immediately with
"DataPulse tray is already running" instead of silently conflicting with
the first and neither one showing an icon.

Check the collector is healthy any time with:

```bash
systemctl status datapulse-collector.service
```

## Updating

Always update by re-running the full install, not by manually copying
individual files — a partial update (e.g. only copying `netwatch/*.py`) can
leave other generated files (like the `datapulse` launcher script) stale
and pointing at old behavior.

**.deb install:**

```bash
git pull
./packaging/build-deb.sh <new-version>
sudo apt install ./datapulse_<new-version>_all.deb
```

**install.sh setup:**

```bash
git pull
./install.sh
```

`install.sh` is safe to re-run any time — it regenerates every file it
manages (including the launcher script) rather than only patching things.

## Publishing (Ubuntu PPA)

The app needs root (systemd service, `iptables`, `net_cls` cgroups), which
rules out sandboxed stores like Flathub/Snap — they don't allow installing
system services or raw firewall/cgroup access. A **PPA (Personal Package
Archive)** on Launchpad is the realistic path to a "browse and install"
experience that still fits how this app works:

1. Create a free account at [launchpad.net](https://launchpad.net) and
   [generate/upload a GPG key](https://help.launchpad.net/YourAccount/ImportingYourPGPKey)
   (needed to sign uploads).
2. Create a PPA from your Launchpad profile page ("Create a new PPA").
3. Build a **source** package (not the binary `.deb` from this repo) using
   `debuild`/`dput` — Launchpad's build farm compiles it for each Ubuntu
   release rather than accepting a prebuilt binary directly. This needs a
   proper `debian/` source package structure (changelog, rules, etc.) which
   is a bit more involved than the binary packaging in `packaging/` here —
   ask me to set this up when you're ready to do this step, it's a
   reasonably sized chunk of work on its own.
4. Once built, users add your PPA and install normally:
   ```bash
   sudo add-apt-repository ppa:<your-launchpad-username>/datapulse
   sudo apt update
   sudo apt install datapulse
   ```
   This also makes it show up as available/upgradable in the Zorin/GNOME
   Software app once the PPA is added, since it has proper `.desktop` +
   icon metadata.

## Known limitations

- Block/limit/cap rules apply to every process with a matching binary name —
  there's no way to distinguish two separately-launched instances of the
  same app.
- If the collector crashes and systemd restarts it, there's a brief window
  where a previously-blocked app could reach the network before rules are
  re-applied.
