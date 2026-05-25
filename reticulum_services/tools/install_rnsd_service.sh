#!/usr/bin/env bash
set -e

SERVICE_FILE="$HOME/.config/systemd/user/rnsd.service"

if [ "${1}" == "--uninstall" ]; then
    if [ ! -f "$SERVICE_FILE" ]; then
        echo "rnsd service is not installed."
        exit 0
    fi
    systemctl --user stop rnsd.service
    systemctl --user disable rnsd.service
    rm "$SERVICE_FILE"
    systemctl --user daemon-reload
    echo "rnsd service removed."
    exit 0
fi

RNSD_BIN=$(which rnsd)
if [ -z "$RNSD_BIN" ]; then
    echo "Error: rnsd not found. Run this task inside the pixi environment (pixi run install_rnsd_service)."
    exit 1
fi

mkdir -p "$(dirname "$SERVICE_FILE")"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Reticulum Network Stack Daemon
After=default.target

[Service]
Type=simple
Restart=always
RestartSec=3
ExecStart=$RNSD_BIN --service

[Install]
WantedBy=default.target
EOF

echo "Wrote $SERVICE_FILE"

systemctl --user daemon-reload
systemctl --user enable rnsd.service
systemctl --user start rnsd.service

echo "rnsd service enabled and started."
echo "To check status: systemctl --user status rnsd.service"
echo ""
echo "To start automatically without login, run:"
echo "  sudo loginctl enable-linger $USER"
