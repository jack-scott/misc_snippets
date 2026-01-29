#!/bin/bash
# Setup script for Battery Monitor

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="battery-monitor.service"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
BIN_DIR="${HOME}/.local/bin"

echo "Setting up Battery Monitor..."
echo "=============================="

# Make the Python script executable
chmod +x "${SCRIPT_DIR}/battery_monitor.py"
echo "✓ Made battery_monitor.py executable"

# Make the battery_time CLI tool executable
chmod +x "${SCRIPT_DIR}/battery_time"
echo "✓ Made battery_time executable"

# Create bin directory if it doesn't exist
mkdir -p "${BIN_DIR}"
echo "✓ Created ${BIN_DIR}"

# Create symlink for battery_time
if [ -L "${BIN_DIR}/battery_time" ]; then
    rm "${BIN_DIR}/battery_time"
fi
ln -s "${SCRIPT_DIR}/battery_time" "${BIN_DIR}/battery_time"
echo "✓ Created symlink: ${BIN_DIR}/battery_time -> ${SCRIPT_DIR}/battery_time"

# Create symlink for battery_monitor_service
if [ -L "${BIN_DIR}/battery_monitor_service" ]; then
    rm "${BIN_DIR}/battery_monitor_service"
fi
ln -s "${SCRIPT_DIR}/battery_monitor.py" "${BIN_DIR}/battery_monitor_service"
echo "✓ Created symlink: ${BIN_DIR}/battery_monitor_service -> ${SCRIPT_DIR}/battery_monitor.py"

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
    echo ""
    echo "⚠ WARNING: ${BIN_DIR} is not in your PATH"
    echo "  Add this line to your ~/.bashrc or ~/.zshrc:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

# Create systemd user directory if it doesn't exist
mkdir -p "${SYSTEMD_USER_DIR}"
echo "✓ Created systemd user directory"

# Copy service file to systemd user directory
cp "${SCRIPT_DIR}/${SERVICE_FILE}" "${SYSTEMD_USER_DIR}/"
echo "✓ Copied service file to ${SYSTEMD_USER_DIR}"

# Reload systemd daemon
systemctl --user daemon-reload
echo "✓ Reloaded systemd daemon"

# Enable the service to start on boot
systemctl --user enable battery-monitor.service
echo "✓ Enabled battery-monitor service"

# Start the service
systemctl --user start battery-monitor.service
echo "✓ Started battery-monitor service"

echo ""
echo "Setup complete!"
echo ""
echo "Useful commands:"
echo "  Monitor Status:  systemctl --user status battery-monitor"
echo "  Stop Monitor:    systemctl --user stop battery-monitor"
echo "  Start Monitor:   systemctl --user start battery-monitor"
echo "  View Logs:       journalctl --user -u battery-monitor -f"
echo "  Disable Monitor: systemctl --user disable battery-monitor"
echo ""
echo "Battery Time CLI Tool:"
echo "  battery_time        # Show estimated time remaining"
echo "  battery_time -v     # Verbose mode with detailed statistics"
echo "  battery_time -g     # Graph mode with visual battery data"
echo ""
echo "Battery logs are stored in: ~/.local/share/battery_monitor/"
echo "  - All data: battery_statistics.csv"
