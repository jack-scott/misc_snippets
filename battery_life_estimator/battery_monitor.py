#!/usr/bin/env python3
"""
Battery Monitor - Logs battery statistics when discharging
Logs: time remaining, power profile, battery capacity (mAh)
"""

import os
import sys
import time
import subprocess
from datetime import datetime
from pathlib import Path
import csv

# Configuration
LOG_DIR = Path.home() / ".local" / "share" / "battery_monitor"
INTERVAL_SECONDS = 300  # 5 minutes
LOG_FILE = "battery_statistics.csv"

# CSV Headers
HEADERS = [
    "timestamp",
    "date",
    "time",
    "battery_percent",
    "time_remaining_hours",
    "power_profile",
    "energy_now_mah",
    "power_draw_watts",
    "voltage_volts"
]


def setup_logging():
    """Create log directory if it doesn't exist"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_battery_info():
    """
    Get battery information from /sys/class/power_supply/BAT*
    Returns dict with battery stats or None if charging/not available
    """
    # Find battery directory (usually BAT0 or BAT1)
    power_supply_dir = Path("/sys/class/power_supply")
    battery_dirs = list(power_supply_dir.glob("BAT*"))

    if not battery_dirs:
        return None

    battery_dir = battery_dirs[0]  # Use first battery found

    try:
        # Read status - only log when discharging
        status_file = battery_dir / "status"
        if status_file.exists():
            status = status_file.read_text().strip()
            if status != "Discharging":
                return None  # Skip if not discharging

        # Read battery percentage
        capacity_file = battery_dir / "capacity"
        battery_percent = int(capacity_file.read_text().strip()) if capacity_file.exists() else None

        # Read energy now (in µWh, convert to mAh)
        # energy_now / voltage_now = charge in mAh
        energy_now_file = battery_dir / "energy_now"
        energy_full_file = battery_dir / "energy_full"
        voltage_now_file = battery_dir / "voltage_now"
        power_now_file = battery_dir / "power_now"

        energy_now_uwh = int(energy_now_file.read_text().strip()) if energy_now_file.exists() else 0
        voltage_now_uv = int(voltage_now_file.read_text().strip()) if voltage_now_file.exists() else 1
        power_now_uw = int(power_now_file.read_text().strip()) if power_now_file.exists() else 0

        # Convert to readable units
        energy_now_wh = energy_now_uwh / 1_000_000
        voltage_now_v = voltage_now_uv / 1_000_000
        power_now_w = power_now_uw / 1_000_000

        # Calculate mAh (milliamp-hours)
        if voltage_now_v > 0:
            energy_now_mah = (energy_now_wh / voltage_now_v) * 1000
        else:
            energy_now_mah = 0

        # Estimate time remaining based on current power draw
        if power_now_w > 0:
            time_remaining_hours = energy_now_wh / power_now_w
        else:
            time_remaining_hours = 0

        return {
            "battery_percent": battery_percent,
            "time_remaining_hours": round(time_remaining_hours, 2),
            "energy_now_mah": round(energy_now_mah, 2),
            "power_draw_watts": round(power_now_w, 2),
            "voltage_volts": round(voltage_now_v, 2)
        }

    except (FileNotFoundError, ValueError, ZeroDivisionError) as e:
        print(f"Error reading battery info: {e}", file=sys.stderr)
        return None


def get_power_profile():
    """
    Get current power profile from power-profiles-daemon
    Returns: 'performance', 'balanced', 'power-saver', or 'unknown'
    """
    try:
        # Try using powerprofilesctl (newer systems)
        result = subprocess.run(
            ["powerprofilesctl", "get"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    try:
        # Fallback: try reading from dbus/system settings
        result = subprocess.run(
            ["gdbus", "call", "--system",
             "--dest", "net.hadess.PowerProfiles",
             "--object-path", "/net/hadess/PowerProfiles",
             "--method", "org.freedesktop.DBus.Properties.Get",
             "net.hadess.PowerProfiles", "ActiveProfile"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            # Parse output like: (<'balanced'>,)
            output = result.stdout.strip()
            if "'" in output:
                return output.split("'")[1]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return "unknown"


def log_battery_data(battery_info, power_profile):
    """
    Log battery data to single CSV file
    """
    now = datetime.now()
    timestamp = now.isoformat()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    # Prepare row data
    row = {
        "timestamp": timestamp,
        "date": date_str,
        "time": time_str,
        "battery_percent": battery_info["battery_percent"],
        "time_remaining_hours": battery_info["time_remaining_hours"],
        "power_profile": power_profile,
        "energy_now_mah": battery_info["energy_now_mah"],
        "power_draw_watts": battery_info["power_draw_watts"],
        "voltage_volts": battery_info["voltage_volts"]
    }

    # Write to log file
    log_file = LOG_DIR / LOG_FILE
    file_exists = log_file.exists()

    with open(log_file, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    print(f"[{timestamp}] Logged: {battery_info['battery_percent']}% | "
          f"{battery_info['time_remaining_hours']}h remaining | "
          f"{power_profile} | "
          f"{battery_info['energy_now_mah']} mAh | "
          f"{battery_info['power_draw_watts']}W")


def main():
    """Main monitoring loop"""
    print("Battery Monitor Started")
    print(f"Logging to: {LOG_DIR / LOG_FILE}")
    print(f"Interval: {INTERVAL_SECONDS} seconds ({INTERVAL_SECONDS // 60} minutes)")
    print("Only logging when battery is discharging...")
    print("-" * 60)

    setup_logging()

    while True:
        try:
            battery_info = get_battery_info()

            if battery_info is not None:
                power_profile = get_power_profile()
                log_battery_data(battery_info, power_profile)
            else:
                print(f"[{datetime.now().isoformat()}] Skipping: Battery is charging or not available")

            time.sleep(INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\nBattery Monitor Stopped")
            sys.exit(0)
        except Exception as e:
            print(f"Error in main loop: {e}", file=sys.stderr)
            time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
