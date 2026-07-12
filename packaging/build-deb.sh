#!/usr/bin/env bash
# Builds datapulse_<version>_all.deb from the repo source.
set -euo pipefail

VERSION="${1:-0.1.0}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$(mktemp -d)"
PKG_DIR="$BUILD_DIR/datapulse_${VERSION}_all"

echo "==> Staging package tree in $PKG_DIR"
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/usr/lib/datapulse"
mkdir -p "$PKG_DIR/usr/bin"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/etc/xdg/autostart"
mkdir -p "$PKG_DIR/lib/systemd/system"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/scalable/apps"

# DEBIAN control files
sed "s/__VERSION__/$VERSION/" "$REPO_ROOT/packaging/debian/control" > "$PKG_DIR/DEBIAN/control"
cp "$REPO_ROOT/packaging/debian/postinst" "$PKG_DIR/DEBIAN/postinst"
cp "$REPO_ROOT/packaging/debian/prerm" "$PKG_DIR/DEBIAN/prerm"
cp "$REPO_ROOT/packaging/debian/postrm" "$PKG_DIR/DEBIAN/postrm"
chmod 755 "$PKG_DIR/DEBIAN/postinst" "$PKG_DIR/DEBIAN/prerm" "$PKG_DIR/DEBIAN/postrm"

# Application code
cp -r "$REPO_ROOT/netwatch" "$PKG_DIR/usr/lib/datapulse/"
find "$PKG_DIR/usr/lib/datapulse" -name "__pycache__" -type d -exec rm -rf {} +
find "$PKG_DIR/usr/lib/datapulse" -name "*.py" -exec chmod 644 {} \;

# Launcher
cat > "$PKG_DIR/usr/bin/datapulse" <<'EOF'
#!/usr/bin/env bash
export PYTHONPATH="/usr/lib/datapulse:$PYTHONPATH"
exec python3 -m netwatch.tray
EOF
chmod 755 "$PKG_DIR/usr/bin/datapulse"

# Desktop entry: app menu + system-wide autostart for every user (a .deb
# postinst can't write into individual users' ~/.config, so we use the XDG
# system autostart directory instead, which every user session picks up)
cp "$REPO_ROOT/datapulse.desktop" "$PKG_DIR/usr/share/applications/"
cp "$REPO_ROOT/datapulse.desktop" "$PKG_DIR/etc/xdg/autostart/"

# Icons
for size in 16 22 24 32 48 64 128 256; do
    mkdir -p "$PKG_DIR/usr/share/icons/hicolor/${size}x${size}/apps"
    cp "$REPO_ROOT/icons/datapulse-${size}.png" \
        "$PKG_DIR/usr/share/icons/hicolor/${size}x${size}/apps/datapulse.png"
done
cp "$REPO_ROOT/icons/datapulse.svg" "$PKG_DIR/usr/share/icons/hicolor/scalable/apps/datapulse.svg"

# systemd service
cp "$REPO_ROOT/packaging/debian/datapulse-collector.service" \
    "$PKG_DIR/lib/systemd/system/"

echo "==> Building .deb"
dpkg-deb --build --root-owner-group "$PKG_DIR" "$REPO_ROOT/datapulse_${VERSION}_all.deb"

rm -rf "$BUILD_DIR"
echo "==> Done: $REPO_ROOT/datapulse_${VERSION}_all.deb"
