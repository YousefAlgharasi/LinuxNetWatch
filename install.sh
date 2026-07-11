#!/usr/bin/env bash
# Installs LinuxNetWatch (per-app bandwidth monitor) on Zorin/Ubuntu.
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
    echo "Run this as your normal user, not root (it will ask for sudo when needed)." >&2
    exit 1
fi

echo "==> Installing system dependencies"
sudo apt update
sudo apt install -y python3-gi gir1.2-gtk-3.0 nethogs iptables iproute2 policykit-1

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Installing the collector service (runs as root, needed for nethogs)"
INSTALL_DIR="/opt/linuxnetwatch"
sudo mkdir -p "$INSTALL_DIR"
sudo cp -r "$SRC_DIR/netwatch" "$INSTALL_DIR/"

sudo sed "s|__INSTALL_DIR__|$INSTALL_DIR|" "$SRC_DIR/linuxnetwatch-collector.service" \
    | sudo tee /etc/systemd/system/linuxnetwatch-collector.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now linuxnetwatch-collector.service

echo "==> Installing the LinuxNetWatch viewer (runs as your user)"
VIEWER_DIR="$HOME/.local/share/linuxnetwatch"
mkdir -p "$VIEWER_DIR"
cp -r "$SRC_DIR/netwatch" "$VIEWER_DIR/"

BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/linuxnetwatch" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$VIEWER_DIR:\$PYTHONPATH"
exec python3 -m netwatch.window
EOF
chmod +x "$BIN_DIR/linuxnetwatch"

DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cp "$SRC_DIR/linuxnetwatch.desktop" "$DESKTOP_DIR/"

echo
echo "Done. The collector service is running in the background as root, logging"
echo "per-app bandwidth to /var/lib/linuxnetwatch/usage.db."
echo "Make sure $BIN_DIR is on your PATH, then launch LinuxNetWatch from the app"
echo "menu or run 'linuxnetwatch' in a terminal."
echo
echo "Check the collector is running with:"
echo "  systemctl status linuxnetwatch-collector.service"
