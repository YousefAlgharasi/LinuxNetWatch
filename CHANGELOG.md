# Changelog

All notable changes to DataPulse (formerly LinuxNetWatch) are documented here.

## [0.3.0] - 2026-07-12

### Added
- Renamed the app from LinuxNetWatch to DataPulse, with a custom icon
  (shield + pulse waveform) replacing the generic system icon.
- First-run prerequisite checks (`nethogs`, `iptables`, `tc`, `pkexec`,
  `net_cls` cgroup controller) with a clear in-app warning banner and
  collector startup log messages for anything missing.
- AppStream metadata (`.metainfo.xml`) for Software store listings.
- MIT license.

### Fixed
- `install.sh` now migrates an existing old-named LinuxNetWatch install
  (disables/removes the old service and launcher files) instead of leaving
  stale duplicates behind.
- The `.deb` package declares `Conflicts`/`Replaces: linuxnetwatch` so
  upgrading from the old package name is handled by `apt` automatically.

## [0.2.2] - 2026-07-12

### Fixed
- Tray icon "randomly not appearing" was actually a second tray instance
  silently failing to register its AppIndicator over DBus (a side effect
  of repeated Ctrl+C'd manual test runs). The tray now takes a single-
  instance lock and refuses to start a duplicate with a clear message.
- Added a time-range picker directly in the tray menu (5m through 30d,
  defaulting to 1h) instead of a fixed last-24h total.

## [0.2.1] - 2026-07-12

### Fixed
- The collector could silently die permanently after boot: if `nethogs`
  failed to find a network interface before it was up yet, the collector's
  read loop ended with a "successful" exit code, which `Restart=on-failure`
  doesn't treat as a failure worth restarting. The collector now loops
  forever and restarts `nethogs` itself if it ever exits, `nethogs`'s
  stderr is now logged instead of discarded, and the systemd service uses
  `Restart=always` plus waits for `network-online.target`.
- Added `X-GNOME-Autostart-Delay=15` to the `.desktop` launcher to avoid a
  race where the tray starts before the AppIndicator shell extension is
  ready at login.

## [0.2.0] - 2026-07-12

### Added
- **Rules** dialog: a single list of every app with an active block/limit/
  cap, instead of checking each app individually.
- **Kill Switch**: block all outbound traffic except an allow-listed set
  of apps.
- Per-app 24-hour usage bar chart in the detail popup.
- CSV export of the selected time range's raw history.
- Desktop notifications (via `notify-send`) when an app gets auto-blocked
  for hitting its daily cap.
- Tray icon showing a live combined download/upload total, with
  "Open DataPulse" to launch the full window on demand; autostart on
  login.

### Changed
- Daily data caps now reset at local midnight instead of a rolling 24-hour
  window; a cap-triggered block is automatically lifted the next day
  (manual blocks are left alone).

## [0.1.0] - 2026-07-11

### Added
- Initial release: per-app bandwidth monitoring via `nethogs`, SQLite-
  backed history with selectable time ranges (5m through 30d), and a GTK
  viewer window.
- Per-app network blocking (`iptables` + `net_cls` cgroups) and upload
  rate limiting (`tc`/htb), controlled via `pkexec` from the GUI.
- `.deb` packaging and an `install.sh` for development installs.
