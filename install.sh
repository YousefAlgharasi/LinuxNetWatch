#!/usr/bin/env bash
# Installs DataPulse (per-app bandwidth monitor, formerly LinuxNetWatch) on Zorin/Ubuntu.
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
    echo "Run this as your normal user, not root (it will ask for sudo when needed)." >&2
    exit 1
fi

echo "==> Installing system dependencies"
sudo apt update
sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-appindicator3-0.1 \
    nethogs iptables iproute2 policykit-1 libnotify-bin

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

if systemctl list-unit-files linuxnetwatch-collector.service > /dev/null 2>&1 \
    && systemctl is-enabled linuxnetwatch-collector.service > /dev/null 2>&1; then
    echo "==> Migrating from the old LinuxNetWatch service name"
    sudo systemctl disable --now linuxnetwatch-collector.service || true
    sudo rm -f /etc/systemd/system/linuxnetwatch-collector.service
    rm -f "$HOME/.local/bin/linuxnetwatch" \
          "$HOME/.local/share/applications/linuxnetwatch.desktop" \
          "$HOME/.config/autostart/linuxnetwatch.desktop"
fi

echo "==> Installing the collector service (runs as root, needed for nethogs)"
INSTALL_DIR="/opt/datapulse"
sudo mkdir -p "$INSTALL_DIR"
sudo cp -r "$SRC_DIR/netwatch" "$INSTALL_DIR/"

sudo sed "s|__INSTALL_DIR__|$INSTALL_DIR|" "$SRC_DIR/datapulse-collector.service" \
    | sudo tee /etc/systemd/system/datapulse-collector.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now datapulse-collector.service

echo "==> Installing icons"
for size in 16 22 24 32 48 64 128 256; do
    sudo mkdir -p "/usr/share/icons/hicolor/${size}x${size}/apps"
    sudo cp "$SRC_DIR/icons/datapulse-${size}.png" \
        "/usr/share/icons/hicolor/${size}x${size}/apps/datapulse.png"
done
sudo mkdir -p /usr/share/icons/hicolor/scalable/apps
sudo cp "$SRC_DIR/icons/datapulse.svg" /usr/share/icons/hicolor/scalable/apps/datapulse.svg
sudo gtk-update-icon-cache -f /usr/share/icons/hicolor > /dev/null 2>&1 || true

echo "==> Installing AppStream metadata"
sudo mkdir -p /usr/share/metainfo
sudo cp "$SRC_DIR/packaging/metainfo/io.github.yousefalgharasi.datapulse.metainfo.xml" \
    /usr/share/metainfo/

echo "==> Installing the DataPulse viewer (runs as your user)"
VIEWER_DIR="$HOME/.local/share/datapulse"
mkdir -p "$VIEWER_DIR"
cp -r "$SRC_DIR/netwatch" "$VIEWER_DIR/"

BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/datapulse" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$VIEWER_DIR:\$PYTHONPATH"
exec python3 -m netwatch.tray
EOF
chmod +x "$BIN_DIR/datapulse"

DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cp "$SRC_DIR/datapulse.desktop" "$DESKTOP_DIR/"

echo "==> Enabling autostart on login"
AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cp "$SRC_DIR/datapulse.desktop" "$AUTOSTART_DIR/"

echo
echo "Done. The collector service is running in the background as root, logging"
echo "per-app bandwidth to /var/lib/linuxnetwatch/usage.db (storage path kept"
echo "as-is from before the rename, so existing history is preserved)."
echo "Make sure $BIN_DIR is on your PATH, then launch DataPulse from the app"
echo "menu or run 'datapulse' in a terminal. It will now also start"
echo "automatically on login, showing a tray icon with live totals."
echo
echo "Check the collector is running with:"
echo "  systemctl status datapulse-collector.service"
