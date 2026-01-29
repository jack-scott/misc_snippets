#!/usr/bin/env python3

import curses
import time
import socket
import subprocess
import threading
import json
import os
import netifaces
import ipaddress
import concurrent.futures
from datetime import datetime
from collections import defaultdict, deque
from typing import Dict, List, Set, Optional

# Import MAC vendor lookup
try:
    from mac_vendors import lookup_mac_vendor, get_device_type_hint
except ImportError:
    # Fallback if mac_vendors.py not found
    def lookup_mac_vendor(mac):
        return "Unknown Vendor"
    def get_device_type_hint(vendor):
        return ""

class NetworkTrafficMonitor:
    """Monitor network traffic statistics per interface"""
    def __init__(self):
        self.interface_stats = {}
        self.last_check = {}

    def get_interface_stats(self, interface: str) -> Dict:
        """Get network traffic stats for an interface"""
        stats = {
            'bytes_sent': 0,
            'bytes_recv': 0,
            'packets_sent': 0,
            'packets_recv': 0,
            'bytes_sent_rate': 0,
            'bytes_recv_rate': 0
        }

        try:
            # Read from /sys/class/net for Linux
            base_path = f"/sys/class/net/{interface}/statistics"

            if os.path.exists(base_path):
                with open(f"{base_path}/tx_bytes") as f:
                    stats['bytes_sent'] = int(f.read().strip())
                with open(f"{base_path}/rx_bytes") as f:
                    stats['bytes_recv'] = int(f.read().strip())
                with open(f"{base_path}/tx_packets") as f:
                    stats['packets_sent'] = int(f.read().strip())
                with open(f"{base_path}/rx_packets") as f:
                    stats['packets_recv'] = int(f.read().strip())

                # Calculate rates
                current_time = time.time()
                if interface in self.last_check:
                    time_delta = current_time - self.last_check[interface]['time']
                    if time_delta > 0:
                        stats['bytes_sent_rate'] = (stats['bytes_sent'] - self.last_check[interface]['bytes_sent']) / time_delta
                        stats['bytes_recv_rate'] = (stats['bytes_recv'] - self.last_check[interface]['bytes_recv']) / time_delta

                self.last_check[interface] = {
                    'time': current_time,
                    'bytes_sent': stats['bytes_sent'],
                    'bytes_recv': stats['bytes_recv']
                }
        except Exception:
            pass

        return stats

class SubnetScanner:
    """Scan and monitor subnets for active devices"""
    def __init__(self):
        self.subnet_devices = {}
        self.scanning = {}
        self.interface_devices = {}  # Devices discovered per interface

    def get_arp_table(self) -> List[Dict]:
        """Get ARP table entries to discover local devices"""
        devices = []
        try:
            # Try ip neigh first (modern Linux)
            result = subprocess.run(['ip', 'neigh'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if not line.strip():
                        continue
                    parts = line.split()
                    if len(parts) >= 5 and parts[0]:
                        ip = parts[0]
                        interface = parts[2] if len(parts) > 2 else 'unknown'
                        mac = parts[4] if len(parts) > 4 and ':' in parts[4] else None
                        state = parts[5] if len(parts) > 5 else 'UNKNOWN'

                        if state in ['REACHABLE', 'STALE', 'DELAY', 'PROBE']:
                            devices.append({
                                'ip': ip,
                                'mac': mac,
                                'interface': interface,
                                'state': state
                            })
        except:
            # Fallback to arp command
            try:
                result = subprocess.run(['arp', '-a'], capture_output=True, text=True, timeout=2)
                for line in result.stdout.split('\n'):
                    if '(' in line and ')' in line:
                        ip = line.split('(')[1].split(')')[0]
                        mac_parts = line.split()
                        mac = None
                        for part in mac_parts:
                            if ':' in part and len(part) == 17:
                                mac = part
                                break
                        if ip:
                            devices.append({
                                'ip': ip,
                                'mac': mac,
                                'interface': 'unknown',
                                'state': 'REACHABLE'
                            })
            except:
                pass

        return devices

    def get_subnet_from_interface(self, interface_info: Dict) -> Optional[str]:
        """Calculate subnet from interface IP and netmask"""
        try:
            if interface_info.get('ipv4'):
                ipv4 = interface_info['ipv4'][0]
                ip = ipv4.get('addr')
                netmask = ipv4.get('netmask')

                if ip and netmask:
                    # Create network from IP and netmask
                    interface = ipaddress.IPv4Interface(f"{ip}/{netmask}")
                    network = interface.network
                    return str(network)
        except:
            pass
        return None

    def ping_host(self, ip: str, timeout: int = 1) -> Dict:
        """Ping a single host and return status"""
        result = {
            'ip': ip,
            'online': False,
            'hostname': None,
            'response_time': None
        }

        try:
            # Ping the host
            proc = subprocess.run(
                ['ping', '-c', '1', '-W', str(timeout), ip],
                capture_output=True,
                text=True,
                timeout=timeout + 1
            )

            if proc.returncode == 0:
                result['online'] = True

                # Extract response time
                for line in proc.stdout.split('\n'):
                    if 'time=' in line:
                        time_str = line.split('time=')[1].split()[0]
                        result['response_time'] = float(time_str)
                        break

                # Try to resolve hostname
                try:
                    hostname = socket.gethostbyaddr(ip)[0]
                    result['hostname'] = hostname
                except:
                    pass

        except:
            pass

        return result

    def scan_subnet(self, subnet: str) -> List[Dict]:
        """Scan entire subnet and return list of active devices"""
        try:
            network = ipaddress.ip_network(subnet, strict=False)
            hosts = list(network.hosts())

            # For large subnets, limit to first 254 hosts
            if len(hosts) > 254:
                hosts = hosts[:254]

            # Scan in parallel for speed
            results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
                future_to_ip = {executor.submit(self.ping_host, str(ip)): ip for ip in hosts}
                for future in concurrent.futures.as_completed(future_to_ip):
                    try:
                        result = future.result()
                        results.append(result)
                    except:
                        pass

            return results

        except Exception as e:
            return []

    def get_subnet_summary(self, subnet: str) -> Dict:
        """Get summary of subnet status"""
        devices = self.subnet_devices.get(subnet, [])
        online_count = sum(1 for d in devices if d['online'])
        total_count = len(devices)

        return {
            'subnet': subnet,
            'online': online_count,
            'total': total_count,
            'devices': devices,
            'scanning': self.scanning.get(subnet, False)
        }

class NetworkMonitor:
    def __init__(self, subdomains: List[str] = None, devices: List[Dict] = None, subnets: List[str] = None):
        self.subdomains = subdomains or []
        self.devices = devices or []
        self.subnets = subnets or []
        self.mac_friendly_names = {}  # MAC address -> friendly name mapping
        self.ip_history = defaultdict(list)
        self.duplicate_ips = set()
        self.network_loops = []
        self.internet_status = True
        self.subdomain_info = {}
        self.device_info = {}
        self.local_interfaces = {}
        self.traffic_monitor = NetworkTrafficMonitor()
        self.subnet_scanner = SubnetScanner()
        self.logs = deque(maxlen=100)
        self.running = True
        self.config_modified = False

    def log(self, message: str):
        """Add a timestamped log entry"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")

    def get_local_interfaces(self) -> Dict:
        """Get all network interfaces and their IP addresses"""
        interfaces = {}
        try:
            for interface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(interface)
                interface_info = {
                    'name': interface,
                    'ipv4': [],
                    'ipv6': [],
                    'mac': None,
                    'status': 'up'
                }

                if netifaces.AF_INET in addrs:
                    for addr in addrs[netifaces.AF_INET]:
                        interface_info['ipv4'].append({
                            'addr': addr.get('addr'),
                            'netmask': addr.get('netmask'),
                            'broadcast': addr.get('broadcast')
                        })

                if netifaces.AF_INET6 in addrs:
                    for addr in addrs[netifaces.AF_INET6]:
                        interface_info['ipv6'].append({
                            'addr': addr.get('addr'),
                            'netmask': addr.get('netmask')
                        })

                if netifaces.AF_LINK in addrs:
                    interface_info['mac'] = addrs[netifaces.AF_LINK][0].get('addr')

                if interface_info['ipv4'] or interface_info['ipv6']:
                    interfaces[interface] = interface_info

        except Exception as e:
            self.log(f"Error getting interfaces: {str(e)}")

        return interfaces

    def check_internet_connectivity(self) -> bool:
        """Check if internet is accessible"""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return True
        except OSError:
            return False

    def detect_network_loops(self) -> List[str]:
        """Detect potential network loops using traceroute analysis"""
        loops = []
        try:
            result = subprocess.run(
                ['traceroute', '-m', '15', '-w', '1', '8.8.8.8'],
                capture_output=True,
                text=True,
                timeout=20
            )

            hops = result.stdout.split('\n')
            hop_ips = []

            for hop in hops:
                parts = hop.split()
                for part in parts:
                    if part.count('.') == 3:
                        try:
                            socket.inet_aton(part)
                            hop_ips.append(part)
                            break
                        except:
                            continue

            seen = set()
            for ip in hop_ips:
                if ip in seen:
                    loops.append(f"Loop detected: {ip} appears multiple times in route")
                seen.add(ip)

        except Exception as e:
            self.log(f"Error checking network loops: {str(e)}")

        return loops

    def check_duplicate_ips(self) -> Set[str]:
        """Check for duplicate IPs across different hostnames"""
        ip_to_hosts = defaultdict(list)
        duplicates = set()

        for subdomain in self.subdomains:
            try:
                ip = socket.gethostbyname(subdomain)
                ip_to_hosts[ip].append(subdomain)

                if len(ip_to_hosts[ip]) > 1:
                    duplicates.add(f"{ip} -> {', '.join(ip_to_hosts[ip])}")
            except Exception as e:
                self.log(f"Error resolving {subdomain}: {str(e)}")

        return duplicates

    def get_subdomain_info(self, subdomain: str) -> Dict:
        """Get detailed information about a subdomain"""
        info = {
            'hostname': subdomain,
            'ip': None,
            'reachable': False,
            'response_time': None,
            'status': 'Unknown'
        }

        try:
            ip = socket.gethostbyname(subdomain)
            info['ip'] = ip

            start = time.time()
            sock = socket.create_connection((subdomain, 80), timeout=3)
            sock.close()
            info['response_time'] = round((time.time() - start) * 1000, 2)
            info['reachable'] = True
            info['status'] = 'OK'
        except socket.gaierror:
            info['status'] = 'DNS Failed'
        except socket.timeout:
            info['status'] = 'Timeout'
        except ConnectionRefusedError:
            info['status'] = 'Connection Refused'
            info['reachable'] = False
        except Exception as e:
            info['status'] = f'Error: {str(e)[:20]}'

        return info

    def check_device(self, device: Dict) -> Dict:
        """Check if a local device is reachable"""
        hostname = device.get('hostname', '')
        ip = device.get('ip', '')
        name = device.get('name', hostname or ip)

        info = {
            'name': name,
            'hostname': hostname,
            'ip': ip,
            'resolved_ip': None,
            'reachable': False,
            'response_time': None,
            'status': 'Unknown'
        }

        try:
            if hostname:
                resolved_ip = socket.gethostbyname(hostname)
                info['resolved_ip'] = resolved_ip
                target = hostname
            elif ip:
                info['resolved_ip'] = ip
                target = ip
            else:
                info['status'] = 'No hostname or IP'
                return info

            result = subprocess.run(
                ['ping', '-c', '1', '-W', '2', target],
                capture_output=True,
                text=True,
                timeout=3
            )

            if result.returncode == 0:
                info['reachable'] = True
                info['status'] = 'Online'

                for line in result.stdout.split('\n'):
                    if 'time=' in line:
                        time_str = line.split('time=')[1].split()[0]
                        info['response_time'] = float(time_str)
                        break
            else:
                info['status'] = 'Offline'
                info['reachable'] = False

        except socket.gaierror:
            info['status'] = 'DNS Failed'
        except subprocess.TimeoutExpired:
            info['status'] = 'Timeout'
        except Exception as e:
            info['status'] = f'Error: {str(e)[:20]}'

        return info

    def scan_subnet_async(self, subnet: str):
        """Scan a subnet in the background"""
        self.subnet_scanner.scanning[subnet] = True
        self.log(f"Scanning subnet: {subnet}")

        results = self.subnet_scanner.scan_subnet(subnet)
        self.subnet_scanner.subnet_devices[subnet] = results

        online_count = sum(1 for r in results if r['online'])
        self.log(f"Subnet {subnet} scan complete: {online_count} devices online")
        self.subnet_scanner.scanning[subnet] = False

    def monitor_loop(self):
        """Main monitoring loop that runs in background"""
        loop_check_counter = 0
        interface_check_counter = 0
        subnet_check_counter = 0

        while self.running:
            interface_check_counter += 1
            if interface_check_counter >= 6:
                old_interfaces = set(self.local_interfaces.keys())
                self.local_interfaces = self.get_local_interfaces()
                new_interfaces = set(self.local_interfaces.keys())

                added = new_interfaces - old_interfaces
                removed = old_interfaces - new_interfaces
                if added:
                    for iface in added:
                        self.log(f"Interface added: {iface}")
                if removed:
                    for iface in removed:
                        self.log(f"Interface removed: {iface}")

                interface_check_counter = 0
            elif not self.local_interfaces:
                self.local_interfaces = self.get_local_interfaces()

            internet_status = self.check_internet_connectivity()
            if internet_status != self.internet_status:
                self.internet_status = internet_status
                if internet_status:
                    self.log("Internet connection restored")
                else:
                    self.log("Internet connection lost!")

            for subdomain in self.subdomains:
                info = self.get_subdomain_info(subdomain)
                old_info = self.subdomain_info.get(subdomain, {})

                if old_info.get('status') != info['status']:
                    self.log(f"{subdomain}: {info['status']}")

                self.subdomain_info[subdomain] = info

            for device in self.devices:
                device_key = device.get('name') or device.get('hostname') or device.get('ip')
                info = self.check_device(device)
                old_info = self.device_info.get(device_key, {})

                if old_info.get('status') != info['status']:
                    self.log(f"{device_key}: {info['status']}")

                self.device_info[device_key] = info

            # Scan subnets periodically
            subnet_check_counter += 1
            if subnet_check_counter >= 12:  # Every 60 seconds
                for subnet in self.subnets:
                    if not self.subnet_scanner.scanning.get(subnet, False):
                        # Run subnet scan in separate thread
                        scan_thread = threading.Thread(target=self.scan_subnet_async, args=(subnet,), daemon=True)
                        scan_thread.start()
                subnet_check_counter = 0

            self.duplicate_ips = self.check_duplicate_ips()

            loop_check_counter += 1
            if loop_check_counter >= 10:
                self.network_loops = self.detect_network_loops()
                loop_check_counter = 0

            time.sleep(5)

class NetworkMonitorUI:
    def __init__(self, stdscr, monitor: NetworkMonitor):
        self.stdscr = stdscr
        self.monitor = monitor
        self.current_page = 'overview'
        self.interface_list = []
        self.edit_mode = False
        self.edit_field = None
        self.edit_input = ""
        self.selected_item = 0
        self.interface_device_list = []  # Devices on current interface
        self.selected_device_ip = None  # For device detail view
        self.selected_device_mac = None  # MAC being edited for friendly name
        self.ping_results = []  # Store ping results for device detail
        self.ping_thread = None  # Background ping thread
        self.ping_running = False  # Flag to control ping thread
        self.device_info_cache = {}  # Cache for device info (hostname, mac, vendor, etc.)
        self.device_info_thread = None  # Background thread for device info loading
        self.device_info_loading = False  # Flag for device info loading

        curses.start_color()
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(6, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(7, curses.COLOR_BLACK, curses.COLOR_WHITE)

        self.stdscr.nodelay(True)
        curses.curs_set(0)

    def format_bytes(self, bytes_val: float) -> str:
        """Format bytes to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.2f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.2f} PB"

    def draw(self):
        """Draw the UI based on current page"""
        if self.current_page == 'overview':
            self.draw_overview()
        elif self.current_page.startswith('interface:'):
            interface_name = self.current_page.split(':', 1)[1]
            self.draw_interface_page(interface_name)
        elif self.current_page.startswith('device:'):
            # Format: device:interface_name:ip
            parts = self.current_page.split(':', 2)
            if len(parts) == 3:
                interface_name = parts[1]
                device_ip = parts[2]
                self.draw_device_detail_page(interface_name, device_ip)
        elif self.current_page.startswith('subnet:'):
            subnet = self.current_page.split(':', 1)[1]
            self.draw_subnet_page(subnet)
        elif self.current_page == 'config':
            self.draw_config_page()

    def draw_overview(self):
        """Draw the overview page"""
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()
        row = 0

        title = "Network Monitor - Overview"
        self.stdscr.addstr(row, (width - len(title)) // 2, title,
                          curses.color_pair(4) | curses.A_BOLD)
        row += 2

        status_text = "Internet: "
        self.stdscr.addstr(row, 0, status_text)
        if self.monitor.internet_status:
            self.stdscr.addstr("CONNECTED", curses.color_pair(1) | curses.A_BOLD)
        else:
            self.stdscr.addstr("DISCONNECTED", curses.color_pair(2) | curses.A_BOLD)
        row += 2

        self.stdscr.addstr(row, 0, "Network Interfaces (Press 1-9 for details):", curses.A_BOLD)
        row += 1

        self.interface_list = list(self.monitor.local_interfaces.keys())

        if self.monitor.local_interfaces:
            for idx, (iface_name, iface_info) in enumerate(list(self.monitor.local_interfaces.items())[:9]):
                if row >= height - 12:
                    break

                self.stdscr.addstr(row, 2, f"[{idx + 1}] {iface_name}", curses.color_pair(4) | curses.A_BOLD)
                row += 1

                if iface_info['ipv4']:
                    ipv4 = iface_info['ipv4'][0]
                    self.stdscr.addstr(row, 6, f"IPv4: {ipv4['addr']}", curses.color_pair(1))
                    row += 1

                stats = self.monitor.traffic_monitor.get_interface_stats(iface_name)
                tx_rate = self.format_bytes(stats['bytes_sent_rate']) + "/s"
                rx_rate = self.format_bytes(stats['bytes_recv_rate']) + "/s"
                self.stdscr.addstr(row, 6, f"TX: {tx_rate} | RX: {rx_rate}", curses.color_pair(3))
                row += 1
                row += 1
        else:
            self.stdscr.addstr(row, 2, "Loading...", curses.color_pair(3))
            row += 1

        log_start_row = height - 8
        if log_start_row > row:
            row = log_start_row

        self.stdscr.addstr(row, 0, "Recent Logs:", curses.A_BOLD)
        row += 1
        self.stdscr.addstr(row, 0, "-" * (width - 1))
        row += 1

        logs_to_show = list(self.monitor.logs)[-4:]
        for log in logs_to_show:
            if row >= height - 1:
                break
            self.stdscr.addstr(row, 0, log[:width-1])
            row += 1

        help_text = "1-9: Interface | 'e': Edit Config | 'q': Quit | 'r': Refresh"
        if height > 2:
            self.stdscr.addstr(height - 1, 0, help_text[:width-1], curses.color_pair(5))

        self.stdscr.refresh()

    def draw_interface_page(self, interface_name: str):
        """Draw detailed interface page with discovered devices"""
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()
        row = 0

        if interface_name not in self.monitor.local_interfaces:
            self.stdscr.addstr(row, 0, f"Interface {interface_name} not found")
            self.stdscr.refresh()
            return

        iface_info = self.monitor.local_interfaces[interface_name]
        stats = self.monitor.traffic_monitor.get_interface_stats(interface_name)

        title = f"Interface: {interface_name}"
        self.stdscr.addstr(row, (width - len(title)) // 2, title,
                          curses.color_pair(4) | curses.A_BOLD)
        row += 2

        # Interface info (condensed)
        if iface_info['ipv4']:
            ipv4 = iface_info['ipv4'][0]
            addr_line = f"IP: {ipv4['addr']}/{ipv4.get('netmask', 'N/A')}"
            self.stdscr.addstr(row, 0, addr_line, curses.color_pair(1))

            # Show detected subnet
            subnet = self.monitor.subnet_scanner.get_subnet_from_interface(iface_info)
            if subnet:
                self.stdscr.addstr(row, 35, f"Subnet: {subnet}", curses.color_pair(3))
            row += 1

        if iface_info.get('mac'):
            self.stdscr.addstr(row, 0, f"MAC: {iface_info['mac']}", curses.color_pair(3))
            row += 1

        # Traffic stats (compact)
        tx_rate = self.format_bytes(stats['bytes_sent_rate']) + "/s"
        rx_rate = self.format_bytes(stats['bytes_recv_rate']) + "/s"
        self.stdscr.addstr(row, 0, f"TX: {tx_rate} | RX: {rx_rate} | Total TX: {self.format_bytes(stats['bytes_sent'])}", curses.color_pair(3))
        row += 2

        # Get devices on this interface from ARP table
        arp_devices = self.monitor.subnet_scanner.get_arp_table()
        interface_devices = [d for d in arp_devices if d['interface'] == interface_name or d['interface'] == 'unknown']

        self.stdscr.addstr(row, 0, f"Devices on this Interface ({len(interface_devices)}): [Press 1-9 or 0 for details]", curses.A_BOLD)
        row += 1

        # Color key legend
        legend = "Color Key: "
        self.stdscr.addstr(row, 2, legend, curses.color_pair(5))
        col = 2 + len(legend)
        self.stdscr.addstr(row, col, "Green", curses.color_pair(1) | curses.A_BOLD)
        col += 5
        self.stdscr.addstr(row, col, "=Reachable ", curses.color_pair(5))
        col += 11
        self.stdscr.addstr(row, col, "Yellow", curses.color_pair(3) | curses.A_BOLD)
        col += 6
        self.stdscr.addstr(row, col, "=Stale ", curses.color_pair(5))
        col += 7
        self.stdscr.addstr(row, col, "White", curses.color_pair(5) | curses.A_BOLD)
        col += 5
        self.stdscr.addstr(row, col, "=Other", curses.color_pair(5))
        row += 1

        # Store device list for selection
        self.interface_device_list = interface_devices[:9]

        if not interface_devices:
            self.stdscr.addstr(row, 2, "No devices discovered yet.", curses.color_pair(3))
            row += 1
            self.stdscr.addstr(row, 2, "Try: Press 's' to scan subnet", curses.color_pair(3))
            row += 1
        else:
            for idx, device in enumerate(self.interface_device_list):
                if row >= height - 5:
                    break

                ip = device['ip']
                mac = device.get('mac', 'Unknown')
                state = device.get('state', 'UNKNOWN')

                # Use cached info if available, otherwise use fast local lookups only
                if ip in self.device_info_cache:
                    cached = self.device_info_cache[ip]
                    hostname = cached.get('hostname')
                    vendor = cached.get('vendor', 'Unknown')
                    device_type = cached.get('device_type', '')
                    friendly_name = cached.get('friendly_name', '')
                else:
                    # Don't do slow hostname lookup on interface page - just use MAC info
                    hostname = None
                    vendor = "Unknown"
                    device_type = ""
                    friendly_name = ""
                    if mac and mac != 'Unknown':
                        vendor = lookup_mac_vendor(mac)
                        device_type = get_device_type_hint(vendor)
                        friendly_name = self.monitor.mac_friendly_names.get(mac, "")

                # Format device line - prioritize friendly name, then hostname
                number = idx + 1 if idx < 9 else 0
                if friendly_name:
                    device_line = f"  [{number}] {ip:15} | {friendly_name[:20]}"
                elif hostname:
                    device_line = f"  [{number}] {ip:15} | {hostname[:20]}"
                else:
                    device_line = f"  [{number}] {ip:15}"

                # Color based on state
                if state == 'REACHABLE':
                    color = curses.color_pair(1)
                elif state == 'STALE':
                    color = curses.color_pair(3)
                else:
                    color = curses.color_pair(5)

                self.stdscr.addstr(row, 2, device_line[:width-4], color)
                row += 1

                # Show vendor/type on next line if available
                if vendor != "Unknown Vendor" or device_type:
                    vendor_line = f"      └─ {vendor}"
                    if device_type:
                        vendor_line += f" [{device_type}]"
                    self.stdscr.addstr(row, 2, vendor_line[:width-4], curses.color_pair(6))
                    row += 1

        help_text = "'s': Scan Subnet | 1-9/0: Device Details | 'b': Back | 'e': Config | 'q': Quit"
        if height > 2:
            self.stdscr.addstr(height - 1, 0, help_text[:width-1], curses.color_pair(5))

        self.stdscr.refresh()

    def load_device_info(self, device_ip: str):
        """Background thread to load device info (hostname, MAC, vendor)"""
        self.device_info_loading = True

        info = {
            'hostname': None,
            'mac': None,
            'vendor': 'Unknown Vendor',
            'device_type': '',
            'friendly_name': '',
            'arp_state': None,
            'arp_interface': None,
            'loaded': False
        }

        try:
            # Get hostname (this can be slow)
            try:
                info['hostname'] = socket.gethostbyaddr(device_ip)[0]
            except:
                pass

            # Get ARP info (fast, local)
            arp_devices = self.monitor.subnet_scanner.get_arp_table()
            for dev in arp_devices:
                if dev['ip'] == device_ip:
                    info['mac'] = dev.get('mac')
                    info['arp_state'] = dev.get('state', 'UNKNOWN')
                    info['arp_interface'] = dev.get('interface', 'unknown')
                    break

            # Get vendor info (fast, local lookup)
            if info['mac']:
                info['vendor'] = lookup_mac_vendor(info['mac'])
                info['device_type'] = get_device_type_hint(info['vendor'])
                info['friendly_name'] = self.monitor.mac_friendly_names.get(info['mac'], "")

            info['loaded'] = True
        except Exception as e:
            pass

        # Store in cache
        self.device_info_cache[device_ip] = info
        self.device_info_loading = False

    def continuous_ping(self, device_ip: str, max_pings: int = 20):
        """Background thread for continuous ping"""
        self.ping_results = []
        for i in range(max_pings):
            if not self.ping_running:
                break

            try:
                result = subprocess.run(
                    ['ping', '-c', '1', '-W', '1', device_ip],
                    capture_output=True,
                    text=True,
                    timeout=2
                )

                if result.returncode == 0:
                    # Extract ping time
                    ping_time = None
                    for line in result.stdout.split('\n'):
                        if 'time=' in line:
                            time_str = line.split('time=')[1].split()[0]
                            ping_time = float(time_str)
                            break

                    if ping_time:
                        self.ping_results.append({
                            'success': True,
                            'time': ping_time,
                            'msg': f"{ping_time:.2f} ms"
                        })
                    else:
                        self.ping_results.append({
                            'success': True,
                            'time': None,
                            'msg': "Replied (no time)"
                        })
                else:
                    self.ping_results.append({
                        'success': False,
                        'time': None,
                        'msg': "TIMEOUT"
                    })

            except Exception as e:
                self.ping_results.append({
                    'success': False,
                    'time': None,
                    'msg': f"ERROR: {str(e)[:20]}"
                })

            time.sleep(0.5)  # Small delay between pings

    def draw_device_detail_page(self, interface_name: str, device_ip: str):
        """Draw detailed device page with continuous ping stats"""
        # Start ping thread if not running
        if not self.ping_running:
            self.ping_running = True
            self.ping_results = []
            self.ping_thread = threading.Thread(
                target=self.continuous_ping,
                args=(device_ip, 20),
                daemon=True
            )
            self.ping_thread.start()

        # Start device info loading thread if not in cache
        if device_ip not in self.device_info_cache:
            # Initialize with loading placeholders
            self.device_info_cache[device_ip] = {
                'hostname': None,
                'mac': None,
                'vendor': 'Unknown Vendor',
                'device_type': '',
                'friendly_name': '',
                'arp_state': None,
                'arp_interface': None,
                'loaded': False
            }
            # Start background loading
            if not self.device_info_loading:
                self.device_info_thread = threading.Thread(
                    target=self.load_device_info,
                    args=(device_ip,),
                    daemon=True
                )
                self.device_info_thread.start()

        # Get cached device info (may be loading)
        info = self.device_info_cache.get(device_ip, {})
        hostname = info.get('hostname')
        mac = info.get('mac')
        vendor = info.get('vendor', 'Unknown Vendor')
        device_type = info.get('device_type', '')
        friendly_name = info.get('friendly_name', '')
        arp_state = info.get('arp_state')
        arp_interface = info.get('arp_interface')
        loaded = info.get('loaded', False)

        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()
        row = 0

        title = f"Device: {device_ip} on {interface_name}"
        self.stdscr.addstr(row, (width - len(title)) // 2, title,
                          curses.color_pair(4) | curses.A_BOLD)
        row += 2

        # Basic info
        self.stdscr.addstr(row, 0, "Device Information:", curses.A_BOLD)
        if not loaded:
            self.stdscr.addstr(row, 22, "[LOADING...]", curses.color_pair(3))
        row += 1
        self.stdscr.addstr(row, 2, f"IP Address:  {device_ip}", curses.color_pair(1))
        row += 1

        # Hostname - show loading or actual value
        if loaded:
            if hostname:
                self.stdscr.addstr(row, 2, f"Hostname:    {hostname}", curses.color_pair(1))
                row += 1
        else:
            self.stdscr.addstr(row, 2, f"Hostname:    [LOADING...]", curses.color_pair(3))
            row += 1

        # MAC and related info
        if mac:
            self.stdscr.addstr(row, 2, f"MAC Address: {mac}", curses.color_pair(3))
            row += 1
            if friendly_name:
                self.stdscr.addstr(row, 2, f"Friendly:    {friendly_name}", curses.color_pair(4) | curses.A_BOLD)
                row += 1
            self.stdscr.addstr(row, 2, f"Vendor:      {vendor}", curses.color_pair(6))
            row += 1
            if device_type:
                self.stdscr.addstr(row, 2, f"Type:        {device_type}", curses.color_pair(6))
                row += 1
            if arp_state:
                # Color code ARP state: green for REACHABLE, yellow for STALE/DELAY, cyan for others
                if arp_state == 'REACHABLE':
                    state_color = curses.color_pair(1)
                elif arp_state in ['STALE', 'DELAY']:
                    state_color = curses.color_pair(3)
                else:
                    state_color = curses.color_pair(5)
                self.stdscr.addstr(row, 2, f"ARP State:   {arp_state}", state_color)
                row += 1
        else:
            if loaded:
                self.stdscr.addstr(row, 2, "MAC Address: Not in ARP table", curses.color_pair(2))
            else:
                self.stdscr.addstr(row, 2, "MAC Address: [LOADING...]", curses.color_pair(3))
            row += 1
        row += 1

        # Show edit prompt if in friendly name edit mode
        if self.edit_mode and self.edit_field == 'friendly_name':
            curses.curs_set(1)
            self.stdscr.addstr(row, 0, "Set Friendly Name:", curses.A_BOLD | curses.color_pair(4))
            row += 1
            self.stdscr.addstr(row, 0, "(Leave empty to remove) > " + self.edit_input[:width-30])
            row += 2
            self.stdscr.addstr(row, 0, "Press Enter to save, Esc to cancel", curses.color_pair(3))
            row += 2
        else:
            curses.curs_set(0)

        # Continuous ping test results
        ping_count = len(self.ping_results)
        max_display = min(15, height - row - 10)

        if self.ping_running:
            status = "[RUNNING...]"
        else:
            status = "[STOPPED]"

        self.stdscr.addstr(row, 0, f"Ping Statistics {status}:", curses.A_BOLD)
        row += 1

        # Show recent ping results
        start_idx = max(0, ping_count - max_display)
        for i in range(start_idx, ping_count):
            if row >= height - 8:
                break

            result = self.ping_results[i]
            status_line = f"  [{i+1:2}] {result['msg']}"

            if result['success']:
                color = curses.color_pair(1)
            else:
                color = curses.color_pair(2)

            self.stdscr.addstr(row, 2, status_line[:width-4], color)
            row += 1

        if ping_count == 0:
            self.stdscr.addstr(row, 2, "Waiting for ping results...", curses.color_pair(3))
            row += 1

        # Stats summary
        successful_pings = [r for r in self.ping_results if r['success'] and r['time'] is not None]
        if successful_pings:
            row += 1
            times = [r['time'] for r in successful_pings]
            avg = sum(times) / len(times)
            min_ping = min(times)
            max_ping = max(times)
            loss = ((ping_count - len(successful_pings)) / max(ping_count, 1)) * 100

            self.stdscr.addstr(row, 0, "Summary:", curses.A_BOLD)
            row += 1
            self.stdscr.addstr(row, 2, f"Packets:     {ping_count} sent, {len(successful_pings)} received", curses.color_pair(3))
            row += 1
            self.stdscr.addstr(row, 2, f"Average:     {avg:.2f} ms", curses.color_pair(3))
            row += 1
            self.stdscr.addstr(row, 2, f"Min/Max:     {min_ping:.2f} / {max_ping:.2f} ms", curses.color_pair(3))
            row += 1
            self.stdscr.addstr(row, 2, f"Packet Loss: {loss:.1f}%", curses.color_pair(1 if loss == 0 else 2))

        if mac:
            help_text = "'f': Set Friendly Name | 'b': Back | 'r': Restart ping | 'q': Quit"
        else:
            help_text = "'b': Back (stops ping) | 'r': Restart ping | 'q': Quit"
        if height > 2:
            self.stdscr.addstr(height - 1, 0, help_text[:width-1], curses.color_pair(5))

        self.stdscr.refresh()

    def draw_subnet_page(self, subnet: str):
        """Draw subnet monitoring page with device grid"""
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()
        row = 0

        title = f"Subnet Monitor: {subnet}"
        self.stdscr.addstr(row, (width - len(title)) // 2, title,
                          curses.color_pair(4) | curses.A_BOLD)
        row += 2

        summary = self.monitor.subnet_scanner.get_subnet_summary(subnet)

        # Summary stats
        status_text = f"Online: {summary['online']}/{summary['total']} devices"
        if summary['scanning']:
            status_text += " [SCANNING...]"
        self.stdscr.addstr(row, 0, status_text, curses.color_pair(3) | curses.A_BOLD)
        row += 2

        # Device list
        devices = summary['devices']
        if not devices:
            self.stdscr.addstr(row, 2, "No scan data yet. Scanning...", curses.color_pair(3))
            row += 1
        else:
            # Sort devices: online first, then by IP
            online_devices = [d for d in devices if d['online']]
            offline_devices = [d for d in devices if not d['online']]

            # Show online devices
            if online_devices:
                self.stdscr.addstr(row, 0, f"Online Devices ({len(online_devices)}):", curses.A_BOLD)
                row += 1

                for device in online_devices[:min(15, height - row - 10)]:
                    ip = device['ip']
                    hostname = device.get('hostname', 'Unknown')
                    ping = device.get('response_time', 'N/A')

                    # Check for friendly name via MAC
                    friendly_name = ""
                    arp_devices = self.monitor.subnet_scanner.get_arp_table()
                    for arp_dev in arp_devices:
                        if arp_dev['ip'] == ip and arp_dev.get('mac'):
                            friendly_name = self.monitor.mac_friendly_names.get(arp_dev['mac'], "")
                            break

                    # Prioritize: friendly name > hostname > just IP
                    if friendly_name:
                        device_line = f"  [{ip:15}] {friendly_name[:30]}"
                    elif hostname and hostname != 'Unknown':
                        device_line = f"  [{ip:15}] {hostname[:30]}"
                    else:
                        device_line = f"  [{ip:15}]"

                    if ping != 'N/A':
                        device_line += f" - {ping:.1f}ms"

                    self.stdscr.addstr(row, 2, device_line[:width-4], curses.color_pair(1))
                    row += 1

                if len(online_devices) > 15:
                    self.stdscr.addstr(row, 2, f"... and {len(online_devices) - 15} more", curses.color_pair(3))
                    row += 1

            row += 1

            # Show summary of offline devices
            if offline_devices and row < height - 5:
                self.stdscr.addstr(row, 0, f"Offline: {len(offline_devices)} devices", curses.color_pair(2))
                row += 1

        help_text = "Press 'b' to go back | 'r': Rescan Now | 'q': Quit"
        if height > 2:
            self.stdscr.addstr(height - 1, 0, help_text[:width-1], curses.color_pair(5))

        self.stdscr.refresh()

    def draw_config_page(self):
        """Draw configuration edit page"""
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()
        row = 0

        title = "Configuration Editor"
        self.stdscr.addstr(row, (width - len(title)) // 2, title,
                          curses.color_pair(4) | curses.A_BOLD)
        row += 2

        if self.edit_mode:
            curses.curs_set(1)
            self.stdscr.addstr(row, 0, f"Adding {self.edit_field}:", curses.A_BOLD)
            row += 1

            if self.edit_field == 'subdomain':
                self.stdscr.addstr(row, 0, "Enter subdomain (e.g., google.com): ")
            elif self.edit_field == 'device':
                self.stdscr.addstr(row, 0, "Enter device (format: name,ip,hostname): ")
            elif self.edit_field == 'subnet':
                self.stdscr.addstr(row, 0, "Enter subnet (e.g., 192.168.1.0/24): ")

            self.stdscr.addstr(row + 1, 0, "> " + self.edit_input)
            row += 3
        else:
            curses.curs_set(0)

        self.stdscr.addstr(row, 0, "Monitored Subdomains:", curses.A_BOLD)
        row += 1
        if self.monitor.subdomains:
            for idx, subdomain in enumerate(self.monitor.subdomains):
                if row >= height - 15:
                    break
                highlight = curses.color_pair(7) if (not self.edit_mode and self.edit_field == 'subdomain' and idx == self.selected_item) else 0
                self.stdscr.addstr(row, 2, f"[{idx}] {subdomain}", curses.color_pair(4) | highlight)
                row += 1
        else:
            self.stdscr.addstr(row, 2, "None configured", curses.color_pair(3))
            row += 1
        row += 1

        self.stdscr.addstr(row, 0, "Local Devices:", curses.A_BOLD)
        row += 1
        if self.monitor.devices:
            for idx, device in enumerate(self.monitor.devices):
                if row >= height - 12:
                    break
                name = device.get('name', 'Unknown')
                ip = device.get('ip', 'N/A')
                hostname = device.get('hostname', 'N/A')
                highlight = curses.color_pair(7) if (not self.edit_mode and self.edit_field == 'device' and idx == self.selected_item) else 0
                self.stdscr.addstr(row, 2, f"[{idx}] {name} - {ip} / {hostname}", curses.color_pair(4) | highlight)
                row += 1
        else:
            self.stdscr.addstr(row, 2, "None configured", curses.color_pair(3))
            row += 1
        row += 1

        self.stdscr.addstr(row, 0, "Monitored Subnets (Press letter to view):", curses.A_BOLD)
        row += 1
        if self.monitor.subnets:
            for idx, subnet in enumerate(self.monitor.subnets):
                if row >= height - 5:
                    break
                highlight = curses.color_pair(7) if (not self.edit_mode and self.edit_field == 'subnet' and idx == self.selected_item) else 0
                summary = self.monitor.subnet_scanner.get_subnet_summary(subnet)
                status_str = f"({summary['online']}/{summary['total']} online)"
                letter = chr(ord('a') + idx) if idx < 26 else '?'
                self.stdscr.addstr(row, 2, f"[{letter}] {subnet} {status_str}", curses.color_pair(4) | highlight)
                row += 1
        else:
            self.stdscr.addstr(row, 2, "None configured", curses.color_pair(3))
            row += 1

        if not self.edit_mode:
            help_text = "'s': Subdomain | 'd': Device | 'n': Subnet | 'x': Delete | Up/Down | 'b': Back | 'q': Quit"
        else:
            help_text = "Enter: Save | Esc: Cancel"

        if height > 2:
            self.stdscr.addstr(height - 1, 0, help_text[:width-1], curses.color_pair(5))

        self.stdscr.refresh()

    def handle_input(self, key):
        """Handle keyboard input"""
        if self.edit_mode:
            if key == 27:  # ESC
                self.edit_mode = False
                self.edit_input = ""
            elif key == 10:  # Enter
                self.save_edit()
                self.edit_mode = False
                self.edit_input = ""
            elif key == curses.KEY_BACKSPACE or key == 127:
                self.edit_input = self.edit_input[:-1]
            elif 32 <= key <= 126:
                self.edit_input += chr(key)
        else:
            if self.current_page == 'overview':
                if key == ord('e') or key == ord('E'):
                    self.current_page = 'config'
                    self.edit_field = 'subdomain'
                    self.selected_item = 0
                elif ord('1') <= key <= ord('9'):
                    idx = key - ord('1')
                    if idx < len(self.interface_list):
                        self.current_page = f'interface:{self.interface_list[idx]}'
            elif self.current_page.startswith('interface:'):
                interface_name = self.current_page.split(':', 1)[1]
                if key == ord('b') or key == ord('B'):
                    self.current_page = 'overview'
                elif key == ord('e') or key == ord('E'):
                    self.current_page = 'config'
                    self.edit_field = 'subdomain'
                    self.selected_item = 0
                elif key == ord('s') or key == ord('S'):
                    # Scan subnet for this interface
                    iface_info = self.monitor.local_interfaces.get(interface_name)
                    if iface_info:
                        subnet = self.monitor.subnet_scanner.get_subnet_from_interface(iface_info)
                        if subnet:
                            self.monitor.log(f"Scanning {subnet} for {interface_name}")
                            scan_thread = threading.Thread(target=self.monitor.scan_subnet_async, args=(subnet,), daemon=True)
                            scan_thread.start()
                elif ord('1') <= key <= ord('9'):
                    # Navigate to device detail
                    idx = key - ord('1')
                    if idx < len(self.interface_device_list):
                        device_ip = self.interface_device_list[idx]['ip']
                        self.current_page = f'device:{interface_name}:{device_ip}'
                elif key == ord('0'):
                    # Device 10 (0 key)
                    if len(self.interface_device_list) == 10:
                        device_ip = self.interface_device_list[9]['ip']
                        self.current_page = f'device:{interface_name}:{device_ip}'
            elif self.current_page.startswith('device:'):
                if key == ord('b') or key == ord('B'):
                    # Stop ping thread and go back to interface page
                    self.ping_running = False
                    if self.ping_thread and self.ping_thread.is_alive():
                        self.ping_thread.join(timeout=1.0)
                    # Stop device info loading if running
                    self.device_info_loading = False
                    if self.device_info_thread and self.device_info_thread.is_alive():
                        self.device_info_thread.join(timeout=0.5)
                    parts = self.current_page.split(':', 2)
                    if len(parts) >= 2:
                        interface_name = parts[1]
                        self.current_page = f'interface:{interface_name}'
                elif key == ord('r') or key == ord('R'):
                    # Restart ping test
                    self.ping_running = False
                    if self.ping_thread and self.ping_thread.is_alive():
                        self.ping_thread.join(timeout=1.0)
                    # Ping will auto-restart on next draw
                    time.sleep(0.1)
                elif key == ord('f') or key == ord('F'):
                    # Set friendly name for device MAC
                    parts = self.current_page.split(':', 2)
                    if len(parts) >= 3:
                        device_ip = parts[2]
                        # Get MAC address for this device
                        arp_devices = self.monitor.subnet_scanner.get_arp_table()
                        for dev in arp_devices:
                            if dev['ip'] == device_ip and dev.get('mac'):
                                self.edit_mode = True
                                self.edit_field = 'friendly_name'
                                self.edit_input = self.monitor.mac_friendly_names.get(dev['mac'], "")
                                self.selected_device_mac = dev['mac']
                                break
            elif self.current_page.startswith('subnet:'):
                if key == ord('b') or key == ord('B'):
                    self.current_page = 'overview'
                elif key == ord('r') or key == ord('R'):
                    # Trigger immediate rescan
                    subnet = self.current_page.split(':', 1)[1]
                    scan_thread = threading.Thread(target=self.monitor.scan_subnet_async, args=(subnet,), daemon=True)
                    scan_thread.start()
            elif self.current_page == 'config':
                if key == ord('b') or key == ord('B'):
                    self.current_page = 'overview'
                elif key == ord('s') or key == ord('S'):
                    self.edit_mode = True
                    self.edit_field = 'subdomain'
                    self.edit_input = ""
                elif key == ord('d') or key == ord('D'):
                    self.edit_mode = True
                    self.edit_field = 'device'
                    self.edit_input = ""
                elif key == ord('n') or key == ord('N'):
                    self.edit_mode = True
                    self.edit_field = 'subnet'
                    self.edit_input = ""
                elif key == ord('x') or key == ord('X'):
                    self.delete_selected()
                elif key == curses.KEY_UP:
                    if self.selected_item > 0:
                        self.selected_item -= 1
                elif key == curses.KEY_DOWN:
                    if self.edit_field == 'subdomain':
                        max_items = len(self.monitor.subdomains)
                    elif self.edit_field == 'device':
                        max_items = len(self.monitor.devices)
                    else:
                        max_items = len(self.monitor.subnets)
                    if self.selected_item < max_items - 1:
                        self.selected_item += 1
                elif ord('a') <= key <= ord('z'):
                    # Navigate to subnet page
                    idx = key - ord('a')
                    if idx < len(self.monitor.subnets):
                        self.current_page = f'subnet:{self.monitor.subnets[idx]}'

            if key == ord('q') or key == ord('Q'):
                self.ping_running = False
                if self.ping_thread and self.ping_thread.is_alive():
                    self.ping_thread.join(timeout=1.0)
                self.device_info_loading = False
                if self.device_info_thread and self.device_info_thread.is_alive():
                    self.device_info_thread.join(timeout=0.5)
                self.monitor.running = False
            elif key == ord('r') or key == ord('R'):
                if not self.current_page.startswith('subnet:'):
                    self.monitor.log("Manual refresh triggered")

    def save_edit(self):
        """Save the current edit"""
        if self.edit_field == 'friendly_name':
            # Handle friendly name edit (can be empty to remove)
            if self.selected_device_mac:
                if self.edit_input.strip():
                    self.monitor.mac_friendly_names[self.selected_device_mac] = self.edit_input.strip()
                    self.monitor.log(f"Set friendly name for {self.selected_device_mac}: {self.edit_input.strip()}")
                else:
                    # Remove friendly name if empty
                    if self.selected_device_mac in self.monitor.mac_friendly_names:
                        del self.monitor.mac_friendly_names[self.selected_device_mac]
                        self.monitor.log(f"Removed friendly name for {self.selected_device_mac}")
                self.monitor.config_modified = True
                self.save_config()
                self.selected_device_mac = None
            return

        if not self.edit_input.strip():
            return

        if self.edit_field == 'subdomain':
            subdomain = self.edit_input.strip()
            if subdomain not in self.monitor.subdomains:
                self.monitor.subdomains.append(subdomain)
                self.monitor.config_modified = True
                self.monitor.log(f"Added subdomain: {subdomain}")
                self.save_config()
        elif self.edit_field == 'device':
            parts = [p.strip() for p in self.edit_input.split(',')]
            if len(parts) >= 2:
                device = {
                    'name': parts[0],
                    'ip': parts[1] if len(parts) > 1 else '',
                    'hostname': parts[2] if len(parts) > 2 else ''
                }
                self.monitor.devices.append(device)
                self.monitor.config_modified = True
                self.monitor.log(f"Added device: {parts[0]}")
                self.save_config()
        elif self.edit_field == 'subnet':
            subnet = self.edit_input.strip()
            try:
                # Validate subnet format
                ipaddress.ip_network(subnet, strict=False)
                if subnet not in self.monitor.subnets:
                    self.monitor.subnets.append(subnet)
                    self.monitor.config_modified = True
                    self.monitor.log(f"Added subnet: {subnet}")
                    self.save_config()
                    # Trigger immediate scan
                    scan_thread = threading.Thread(target=self.monitor.scan_subnet_async, args=(subnet,), daemon=True)
                    scan_thread.start()
            except ValueError:
                self.monitor.log(f"Invalid subnet format: {subnet}")

    def delete_selected(self):
        """Delete the currently selected item"""
        if self.edit_field == 'subdomain' and self.selected_item < len(self.monitor.subdomains):
            removed = self.monitor.subdomains.pop(self.selected_item)
            self.monitor.log(f"Removed subdomain: {removed}")
            self.monitor.config_modified = True
            self.save_config()
            if self.selected_item > 0:
                self.selected_item -= 1
        elif self.edit_field == 'device' and self.selected_item < len(self.monitor.devices):
            removed = self.monitor.devices.pop(self.selected_item)
            self.monitor.log(f"Removed device: {removed.get('name')}")
            self.monitor.config_modified = True
            self.save_config()
            if self.selected_item > 0:
                self.selected_item -= 1
        elif self.edit_field == 'subnet' and self.selected_item < len(self.monitor.subnets):
            removed = self.monitor.subnets.pop(self.selected_item)
            self.monitor.log(f"Removed subnet: {removed}")
            self.monitor.config_modified = True
            self.save_config()
            if self.selected_item > 0:
                self.selected_item -= 1

    def save_config(self):
        """Save configuration to file"""
        config = {
            'subdomains': self.monitor.subdomains,
            'devices': self.monitor.devices,
            'subnets': self.monitor.subnets,
            'mac_friendly_names': self.monitor.mac_friendly_names
        }
        try:
            with open('network_monitor_config.json', 'w') as f:
                json.dump(config, indent=2, fp=f)
            self.monitor.log("Configuration saved")
        except Exception as e:
            self.monitor.log(f"Error saving config: {str(e)}")

    def run(self):
        """Main UI loop"""
        while self.monitor.running:
            self.draw()

            try:
                key = self.stdscr.getch()
                if key != -1:
                    self.handle_input(key)
            except:
                pass

            time.sleep(0.1)

def load_config():
    """Load configuration from config.json if it exists"""
    config_file = 'network_monitor_config.json'
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            return json.load(f)
    return {'subdomains': [], 'devices': [], 'subnets': [], 'mac_friendly_names': {}}

def save_default_config():
    """Create a default config file"""
    config = {
        'subdomains': [
            'google.com',
            'github.com',
            'cloudflare.com'
        ],
        'devices': [
            {
                'name': 'Router',
                'ip': '192.168.1.1',
                'hostname': ''
            },
            {
                'name': 'Home Server',
                'hostname': 'server.local',
                'ip': ''
            }
        ],
        'subnets': [
            '192.168.1.0/24'
        ],
        'mac_friendly_names': {}
    }
    with open('network_monitor_config.json', 'w') as f:
        json.dump(config, indent=2, fp=f)
    return config

def main(stdscr):
    if not os.path.exists('network_monitor_config.json'):
        config = save_default_config()
        print("Created default config file: network_monitor_config.json")
    else:
        config = load_config()

    monitor = NetworkMonitor(
        subdomains=config.get('subdomains', []),
        devices=config.get('devices', []),
        subnets=config.get('subnets', [])
    )
    monitor.mac_friendly_names = config.get('mac_friendly_names', {})
    monitor.log("Network Monitor started")

    monitor_thread = threading.Thread(target=monitor.monitor_loop, daemon=True)
    monitor_thread.start()

    ui = NetworkMonitorUI(stdscr, monitor)
    ui.run()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        print("\nMonitor stopped by user")
