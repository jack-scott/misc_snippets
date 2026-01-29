#!/usr/bin/env python3
"""
Test script to compare MAC address vendor lookup libraries
Tests: mac-vendor-lookup, manuf, netaddr, and current custom implementation
"""

import json
import time
import sys

# Import current implementation
from mac_vendors import lookup_mac_vendor, get_device_type_hint

def test_mac_vendor_lookup():
    """Test mac-vendor-lookup library"""
    try:
        from mac_vendor_lookup import MacLookup
        mac = MacLookup()
        # Try to update vendors database (will skip if already done recently)
        try:
            mac.update_vendors()
            print("✓ mac-vendor-lookup: Database updated")
        except:
            print("✓ mac-vendor-lookup: Using existing database")
        return mac
    except ImportError:
        print("✗ mac-vendor-lookup: Not installed (pip install mac-vendor-lookup)")
        return None
    except Exception as e:
        print(f"✗ mac-vendor-lookup: Error - {e}")
        return None

def test_manuf():
    """Test manuf library"""
    try:
        from manuf import manuf
        p = manuf.MacParser(update=False)  # Don't auto-update on first run
        print("✓ manuf: Loaded")
        return p
    except ImportError:
        print("✗ manuf: Not installed (pip install manuf)")
        return None
    except Exception as e:
        print(f"✗ manuf: Error - {e}")
        return None

def test_netaddr():
    """Test netaddr library"""
    try:
        from netaddr import EUI
        # Test with a sample MAC
        test_mac = EUI('00:00:00:00:00:00')
        print("✓ netaddr: Loaded")
        return True
    except ImportError:
        print("✗ netaddr: Not installed (pip install netaddr)")
        return None
    except Exception as e:
        print(f"✗ netaddr: Error - {e}")
        return None

def lookup_with_mac_vendor_lookup(mac_lib, mac_addr):
    """Lookup using mac-vendor-lookup"""
    try:
        start = time.time()
        vendor = mac_lib.lookup(mac_addr)
        elapsed = time.time() - start
        return vendor, elapsed
    except Exception as e:
        return f"Error: {str(e)}", 0

def lookup_with_manuf(manuf_parser, mac_addr):
    """Lookup using manuf"""
    try:
        start = time.time()
        vendor = manuf_parser.get_manuf(mac_addr)
        long_name = manuf_parser.get_manuf_long(mac_addr)
        elapsed = time.time() - start
        if long_name and long_name != vendor:
            return f"{vendor} ({long_name})", elapsed
        return vendor if vendor else "Unknown", elapsed
    except Exception as e:
        return f"Error: {str(e)}", 0

def lookup_with_netaddr(mac_addr):
    """Lookup using netaddr"""
    try:
        from netaddr import EUI
        start = time.time()
        mac = EUI(mac_addr)
        org = mac.oui.registration().org
        elapsed = time.time() - start
        return org, elapsed
    except Exception as e:
        return f"Error: {str(e)}", 0

def lookup_with_custom(mac_addr):
    """Lookup using current custom implementation"""
    try:
        start = time.time()
        vendor = lookup_mac_vendor(mac_addr)
        device_type = get_device_type_hint(vendor)
        elapsed = time.time() - start
        if device_type:
            return f"{vendor} [{device_type}]", elapsed
        return vendor, elapsed
    except Exception as e:
        return f"Error: {str(e)}", 0

def main():
    print("=" * 80)
    print("MAC Address Vendor Lookup Library Comparison Test")
    print("=" * 80)
    print("\nInitializing libraries...\n")

    # Initialize libraries
    mac_vendor_lookup_lib = test_mac_vendor_lookup()
    manuf_lib = test_manuf()
    netaddr_available = test_netaddr()

    print("\n" + "=" * 80)

    # Load MAC addresses from config
    try:
        with open('network_monitor_config.json', 'r') as f:
            config = json.load(f)
        mac_addresses = list(config.get('mac_friendly_names', {}).keys())
        friendly_names = config.get('mac_friendly_names', {})
    except Exception as e:
        print(f"\nError loading config: {e}")
        print("Using sample MAC addresses instead...")
        mac_addresses = [
            "00:1E:C0:12:34:56",  # Universal Robots
            "B8:27:EB:12:34:56",  # Raspberry Pi
            "24:0A:C4:12:34:56",  # Espressif
        ]
        friendly_names = {}

    print(f"\nTesting with {len(mac_addresses)} MAC addresses from your network\n")
    print("=" * 80)

    # Test each MAC address
    results = []
    for mac in mac_addresses:
        friendly = friendly_names.get(mac, "")
        print(f"\n{'─' * 80}")
        print(f"MAC Address: {mac}")
        if friendly:
            print(f"Your Name:   {friendly}")
        print(f"{'─' * 80}")

        result = {'mac': mac, 'friendly': friendly}

        # Test current custom implementation
        custom_result, custom_time = lookup_with_custom(mac)
        print(f"Current Custom:      {custom_result:50} ({custom_time*1000:.3f}ms)")
        result['custom'] = custom_result
        result['custom_time'] = custom_time

        # Test mac-vendor-lookup
        if mac_vendor_lookup_lib:
            mvl_result, mvl_time = lookup_with_mac_vendor_lookup(mac_vendor_lookup_lib, mac)
            print(f"mac-vendor-lookup:   {mvl_result:50} ({mvl_time*1000:.3f}ms)")
            result['mac_vendor_lookup'] = mvl_result
            result['mvl_time'] = mvl_time
        else:
            print(f"mac-vendor-lookup:   Not available")
            result['mac_vendor_lookup'] = "N/A"

        # Test manuf
        if manuf_lib:
            manuf_result, manuf_time = lookup_with_manuf(manuf_lib, mac)
            print(f"manuf:               {manuf_result:50} ({manuf_time*1000:.3f}ms)")
            result['manuf'] = manuf_result
            result['manuf_time'] = manuf_time
        else:
            print(f"manuf:               Not available")
            result['manuf'] = "N/A"

        # Test netaddr
        if netaddr_available:
            netaddr_result, netaddr_time = lookup_with_netaddr(mac)
            print(f"netaddr:             {netaddr_result:50} ({netaddr_time*1000:.3f}ms)")
            result['netaddr'] = netaddr_result
            result['netaddr_time'] = netaddr_time
        else:
            print(f"netaddr:             Not available")
            result['netaddr'] = "N/A"

        results.append(result)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    # Calculate average times
    if mac_vendor_lookup_lib:
        avg_mvl = sum(r.get('mvl_time', 0) for r in results) / len(results)
        print(f"\nmac-vendor-lookup average time: {avg_mvl*1000:.3f}ms")

    if manuf_lib:
        avg_manuf = sum(r.get('manuf_time', 0) for r in results) / len(results)
        print(f"manuf average time:             {avg_manuf*1000:.3f}ms")

    if netaddr_available:
        avg_netaddr = sum(r.get('netaddr_time', 0) for r in results) / len(results)
        print(f"netaddr average time:           {avg_netaddr*1000:.3f}ms")

    avg_custom = sum(r.get('custom_time', 0) for r in results) / len(results)
    print(f"Custom implementation time:     {avg_custom*1000:.3f}ms")

    # Count successful lookups (not "Unknown" or "Error")
    print("\nSuccess Rate (non-Unknown/Error results):")

    custom_success = sum(1 for r in results if 'Unknown' not in r['custom'] and 'Error' not in r['custom'])
    print(f"Custom:            {custom_success}/{len(results)} ({custom_success*100/len(results):.1f}%)")

    if mac_vendor_lookup_lib:
        mvl_success = sum(1 for r in results if 'Error' not in r.get('mac_vendor_lookup', '') and r.get('mac_vendor_lookup') != 'N/A')
        print(f"mac-vendor-lookup: {mvl_success}/{len(results)} ({mvl_success*100/len(results):.1f}%)")

    if manuf_lib:
        manuf_success = sum(1 for r in results if 'Unknown' not in r.get('manuf', '') and 'Error' not in r.get('manuf', '') and r.get('manuf') != 'N/A')
        print(f"manuf:             {manuf_success}/{len(results)} ({manuf_success*100/len(results):.1f}%)")

    if netaddr_available:
        netaddr_success = sum(1 for r in results if 'Error' not in r.get('netaddr', '') and r.get('netaddr') != 'N/A')
        print(f"netaddr:           {netaddr_success}/{len(results)} ({netaddr_success*100/len(results):.1f}%)")

    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    print("""
Based on the results:

1. **Speed**: Check which library has the fastest lookup times
2. **Coverage**: See which found the most vendors for your specific MACs
3. **Data Quality**: Compare the vendor names - are they detailed/accurate?

For offline robotics labs:
- If custom caught most of your devices → Keep custom (no dependencies)
- If a library found significantly more → Consider integrating it
- Fastest library → Best for real-time UI updates

Note: Libraries need initial database download but work offline after.
Your custom list is curated for robotics/industrial equipment specifically.
""")

if __name__ == "__main__":
    main()
