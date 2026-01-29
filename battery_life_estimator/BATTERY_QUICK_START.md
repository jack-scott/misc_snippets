# Battery Monitor - Quick Start Guide

## Installation

```bash
cd /home/jack/Documents/project/misc_scripts
./setup_battery_monitor.sh
```

**Important**: Make sure `~/.local/bin` is in your PATH. If not, add to `~/.bashrc`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Usage

### Check Battery Time Remaining
```bash
battery_time              # Simple: "04:23 remaining (85%)"
battery_time -v           # Verbose: Detailed stats and predictions
battery_time -g           # Graph: ASCII charts of battery data
```

### Monitor Service Management
```bash
systemctl --user status battery-monitor    # Check status
systemctl --user stop battery-monitor      # Stop logging
systemctl --user start battery-monitor     # Start logging
journalctl --user -u battery-monitor -f    # View live logs
```

## How It Works

1. **Background Service**: Logs battery stats every 5 minutes when discharging
2. **Smart Analysis**: `battery_time` analyzes historical data to predict battery life
3. **Real Measurements**: Calculates actual power consumption between readings (more accurate than system estimates)
4. **Per-Profile Stats**: Tracks different power modes (performance/balanced/power-saver)

## What Makes This Better Than System Estimates?

- System shows instantaneous power draw (fluctuates wildly)
- This measures real energy consumed over time
- Builds historical averages per power profile
- Shows you actual battery life you've experienced, not theoretical estimates

## Data Location

All data stored in: `~/.local/share/battery_monitor/battery_statistics.csv`

## Tips

- Let it run for a few hours to collect data before relying on predictions
- More data = more accurate predictions
- Check `battery_time -v` to see confidence level of estimates
- Use `battery_time -g` to visualize your battery usage patterns

## Example Output

**Simple:**
```
$ battery_time
04:23 remaining (85%)
```

**Verbose:**
```
Current Status:
  Battery Level:     85%
  Energy Remaining:  4250 mAh (48.45 Wh)
  Power Profile:     balanced

Estimated Time Remaining:
  Time:              04:23 (4.38 hours)
  Confidence:        high
  Based on:          47 measurements

Power Profile Statistics:
Profile          Reported   Measured   Accuracy
balanced           10.2 W     11.1 W      91.9%
performance        15.3 W     16.8 W      91.1%
power-saver         7.8 W      8.1 W      96.3%
```

## Files

- `battery_monitor.py` - Background logging service
- `battery_time` - CLI analysis tool
- `battery-monitor.service` - Systemd service file
- `setup_battery_monitor.sh` - Installation script
