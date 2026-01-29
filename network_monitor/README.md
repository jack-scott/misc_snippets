# Network Monitor

Terminal UI for monitoring network infrastructure with subnet scanning, device auto-discovery, MAC vendor identification, and real-time traffic monitoring.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
./network_monitor.py
```

Or:

```bash
python3 network_monitor.py
```

A default `network_monitor_config.json` will be created on first run.

## Features

- **Auto-Discovery**: Scan subnets (e.g., 192.168.1.0/24) to discover active devices via ARP table
- **MAC Vendor Lookup**: Automatically identify device manufacturers using mac-vendor-lookup library
  - Recognizes 100K+ vendors including robotics equipment, IoT devices, and industrial controllers
- **Device Details**: Click into any discovered device to see continuous ping statistics
- **Traffic Monitoring**: Real-time TX/RX rates per network interface
- **Multi-Page Interface**: Navigate between overview, interface details, subnet scans, and device details
- **Interactive Config**: Add/remove subnets, devices, and subdomains through the TUI

## Keyboard Controls

### Overview Page
- `1-9`: View interface details
- `e`: Configuration editor
- `q`: Quit

### Interface Page
- `s`: Scan subnet for devices
- `1-9` or `0`: View device details
- `b`: Back to overview
- `e`: Configuration editor

### Device Detail Page
- `f`: Set friendly name for device MAC
- `r`: Restart ping test
- `b`: Back to interface

### Configuration Editor
- `s`: Add subdomain
- `d`: Add device
- `n`: Add subnet
- `a-z`: View subnet details
- `x`: Delete selected item
- `↑/↓`: Navigate items
- `b`: Back to overview

## Configuration

Edit `network_monitor_config.json` or use the interactive editor (press `e`):

```json
{
  "subdomains": ["google.com", "github.com"],
  "devices": [
    {
      "name": "Router",
      "ip": "192.168.1.1",
      "hostname": ""
    }
  ],
  "subnets": ["192.168.1.0/24"],
  "mac_friendly_names": {
    "AA:BB:CC:DD:EE:FF": "my-device-name"
  }
}
```

**Note**: `mac_friendly_names` is auto-populated when you set friendly names via the UI (press `f` on device detail page).

## Implementation Details

### MAC Vendor Lookup
Uses the [mac-vendor-lookup](https://pypi.org/project/mac-vendor-lookup/) library for comprehensive OUI database lookups. Returns "Unknown Vendor" for locally administered or unregistered MACs.

On first run, mac-vendor-lookup downloads the latest vendor database (~3MB). Subsequent runs work offline.

### Traffic Statistics
Reads interface statistics from `/sys/class/net` on Linux. Rates calculated by comparing byte counts between refresh intervals (every 5 seconds).

### Subnet Scanning
- Uses parallel ping (50 threads) for speed
- ARP table provides instant MAC address information
- Automatically resolves hostnames for discovered devices

### Device Discovery
Devices are discovered through:
1. **ARP Table**: Reads `ip neigh` for recently active devices
2. **Subnet Scan**: Active ICMP ping sweep of configured subnets
3. **Manual Entry**: Add specific devices via config

## Requirements

- Python 3.6+
- Linux/macOS/Windows (traffic stats Linux-only)
- System commands: `ping`, `traceroute` (optional)

## Troubleshooting

### Missing mac-vendor-lookup
The vendor database downloads automatically on first run. If behind a firewall:
```bash
python3 -c "from mac_vendor_lookup import MacLookup; MacLookup().update_vendors()"
```

### Permission Issues
Most features work without root. Ping and ARP table reading use standard system tools.

### Terminal Size
Minimum 80x24 recommended for optimal display.
