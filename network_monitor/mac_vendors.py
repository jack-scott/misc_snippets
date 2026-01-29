#!/usr/bin/env python3
"""
MAC Address Vendor Lookup
Uses mac-vendor-lookup library for comprehensive vendor lookups

Dependencies:
    pip install mac-vendor-lookup

The mac-vendor-lookup library provides a comprehensive OUI database.
If not found, returns "Unknown Vendor" as expected by the network monitor.
"""

# Import mac-vendor-lookup library
try:
    from mac_vendor_lookup import MacLookup
    MAC_LOOKUP = MacLookup()
    MAC_LOOKUP_AVAILABLE = True
except ImportError:
    MAC_LOOKUP_AVAILABLE = False
    MAC_LOOKUP = None
    print("Warning: mac-vendor-lookup not installed. Run: pip install mac-vendor-lookup")

def lookup_mac_vendor(mac_address: str) -> str:
    """
    Look up the vendor for a MAC address

    Args:
        mac_address: MAC address in any common format (AA:BB:CC:DD:EE:FF, AA-BB-CC, etc)

    Returns:
        Vendor name or "Unknown Vendor"
    """
    if not mac_address:
        return "Unknown Vendor"

    # Normalize MAC address
    mac_clean = mac_address.replace(':', '').replace('-', '').replace('.', '').upper()

    if len(mac_clean) < 6:
        return "Unknown Vendor"

    # Use mac-vendor-lookup library
    if MAC_LOOKUP_AVAILABLE:
        try:
            vendor = MAC_LOOKUP.lookup(mac_address)
            if vendor:
                return vendor
        except (KeyError, ValueError):
            # Not found in database
            return "Unknown Vendor"
        except Exception:
            # Any other error
            return "Unknown Vendor"

    # Library not available
    return "Unknown Vendor"

def get_device_type_hint(vendor: str) -> str:
    """Get a hint about what type of device this might be based on vendor"""
    if not vendor or vendor == "Unknown Vendor":
        return ""

    vendor_lower = vendor.lower()

    if "raspberry pi" in vendor_lower:
        return "SBC/IoT"
    elif "arduino" in vendor_lower:
        return "Microcontroller"
    elif "nvidia" in vendor_lower:
        return "AI/Robotics"
    elif "robot" in vendor_lower:
        return "Robot"
    elif "cisco" in vendor_lower or "ubiquiti" in vendor_lower:
        return "Network Equipment"
    elif "vmware" in vendor_lower or "virtualbox" in vendor_lower or "parallels" in vendor_lower:
        return "Virtual Machine"
    elif "axis" in vendor_lower or "hikvision" in vendor_lower:
        return "IP Camera"
    elif "espressif" in vendor_lower:
        return "IoT/ESP Device"
    elif "siemens" in vendor_lower or "bosch" in vendor_lower or "fanuc" in vendor_lower or "abb" in vendor_lower:
        return "Industrial/Robot"
    elif "apple" in vendor_lower or "samsung" in vendor_lower or "google" in vendor_lower:
        return "Consumer Device"
    elif "dell" in vendor_lower or "hp" in vendor_lower or "lenovo" in vendor_lower or "intel" in vendor_lower:
        return "Server/PC"
    else:
        return ""

# For testing
if __name__ == "__main__":
    test_macs = [
        "B8:27:EB:12:34:56",  # Raspberry Pi
        "24:0A:C4:AA:BB:CC",  # ESP32
        "00:00:0C:12:34:56",  # Cisco
        "6c:6e:07:10:66:c1",  # CE LINK LIMITED
        "96:25:30:23:0a:9c",  # Unknown
    ]

    print("MAC Vendor Lookup Test")
    print("-" * 60)
    for mac in test_macs:
        vendor = lookup_mac_vendor(mac)
        device_type = get_device_type_hint(vendor)
        if device_type:
            print(f"{mac} -> {vendor} [{device_type}]")
        else:
            print(f"{mac} -> {vendor}")
