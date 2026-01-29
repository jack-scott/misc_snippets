#!/usr/bin/env python3
"""Monitor docker container stats from cAdvisor.

Displays CPU, memory, network, and disk usage for docker containers
with time-period aggregations (1 minute, 1 hour averages).
"""

import argparse
import os
import sys
import time
from datetime import datetime

from cadvisor_monitor.cadvisor import CAdvisorClient, ContainerSummary, ContainerStats

DEFAULT_URL = "http://beelinkmini:8060"


def clear_screen():
    """Clear terminal screen."""
    os.system('clear' if os.name == 'posix' else 'cls')


def format_bytes(b: float) -> str:
    """Format bytes to human readable."""
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.0f}{unit}"
        b /= 1024
    return f"{b:.1f}TB"


def format_rate(bps: float) -> str:
    """Format bytes per second."""
    if bps < 1024:
        return f"{bps:.0f}B/s"
    elif bps < 1024 * 1024:
        return f"{bps/1024:.1f}KB/s"
    else:
        return f"{bps/(1024*1024):.1f}MB/s"


def format_cpu(millicores: int) -> str:
    """Format CPU millicores."""
    if millicores < 1000:
        return f"{millicores}m"
    return f"{millicores/1000:.1f}"


class NetworkRateTracker:
    """Track network rates by computing deltas between samples."""

    def __init__(self):
        self._prev_stats: dict[str, dict] = {}
        self._prev_time: float = 0

    def compute_rates(self, stats: list[ContainerStats]) -> dict[str, tuple[float, float]]:
        """Compute RX/TX rates from stats.

        Returns:
            Dict mapping container name to (rx_rate, tx_rate) in bytes/sec.
        """
        current_time = time.time()
        elapsed = current_time - self._prev_time if self._prev_time else 0
        rates = {}

        for s in stats:
            rx_rate = 0.0
            tx_rate = 0.0

            if s.name in self._prev_stats and elapsed > 0:
                prev = self._prev_stats[s.name]
                rx_rate = max(0, (s.net_rx_bytes - prev["rx"]) / elapsed)
                tx_rate = max(0, (s.net_tx_bytes - prev["tx"]) / elapsed)

            rates[s.name] = (rx_rate, tx_rate)
            self._prev_stats[s.name] = {"rx": s.net_rx_bytes, "tx": s.net_tx_bytes}

        self._prev_time = current_time
        return rates


def print_compact(summaries: list[ContainerSummary]):
    """Print compact CPU/memory view."""
    # Sort by current CPU usage
    summaries = sorted(summaries, key=lambda s: s.cpu_millicores, reverse=True)

    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"Container Stats @ {timestamp}")
    print(f"{'Container':<20} {'CPU Now':>8} {'CPU 1m':>8} {'CPU 1h':>8} {'MEM Now':>10} {'MEM 1m':>10} {'MEM 1h':>10}")
    print("-" * 86)

    for s in summaries:
        print(
            f"{s.name:<20} "
            f"{format_cpu(s.cpu_millicores):>8} "
            f"{format_cpu(s.cpu_1m_mean):>8} "
            f"{format_cpu(s.cpu_1h_mean):>8} "
            f"{format_bytes(s.memory_bytes):>10} "
            f"{format_bytes(s.memory_1m_mean):>10} "
            f"{format_bytes(s.memory_1h_mean):>10}"
        )


def print_full(
    summaries: list[ContainerSummary],
    stats: list[ContainerStats],
    net_rates: dict[str, tuple[float, float]],
):
    """Print full view with network and disk."""
    # Build combined data
    stats_by_name = {s.name: s for s in stats}

    # Sort by memory usage
    summaries = sorted(summaries, key=lambda s: s.memory_bytes, reverse=True)

    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"Container Stats @ {timestamp}")
    print("=" * 110)

    # CPU & Memory section
    print(f"\n{'CONTAINER':<18} {'CPU NOW':>7} {'CPU 1m':>7} {'CPU 1h':>7} {'MEM NOW':>9} {'MEM 1m':>9} {'MEM 1h':>9}")
    print("-" * 110)

    for s in summaries:
        print(
            f"{s.name:<18} "
            f"{format_cpu(s.cpu_millicores):>7} "
            f"{format_cpu(s.cpu_1m_mean):>7} "
            f"{format_cpu(s.cpu_1h_mean):>7} "
            f"{format_bytes(s.memory_bytes):>9} "
            f"{format_bytes(s.memory_1m_mean):>9} "
            f"{format_bytes(s.memory_1h_mean):>9}"
        )

    # Network section
    print(f"\n{'CONTAINER':<18} {'RX RATE':>10} {'TX RATE':>10} {'RX TOTAL':>12} {'TX TOTAL':>12}")
    print("-" * 110)

    for s in summaries:
        st = stats_by_name.get(s.name)
        rx_rate, tx_rate = net_rates.get(s.name, (0, 0))
        print(
            f"{s.name:<18} "
            f"{format_rate(rx_rate):>10} "
            f"{format_rate(tx_rate):>10} "
            f"{format_bytes(st.net_rx_bytes if st else 0):>12} "
            f"{format_bytes(st.net_tx_bytes if st else 0):>12}"
        )

    # Disk section
    print(f"\n{'CONTAINER':<18} {'FS USAGE':>12} {'READ TOTAL':>12} {'WRITE TOTAL':>12}")
    print("-" * 110)

    for s in summaries:
        st = stats_by_name.get(s.name)
        print(
            f"{s.name:<18} "
            f"{format_bytes(st.fs_usage_bytes if st else 0):>12} "
            f"{format_bytes(st.disk_read_bytes if st else 0):>12} "
            f"{format_bytes(st.disk_write_bytes if st else 0):>12}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Monitor docker container stats from cAdvisor"
    )
    parser.add_argument(
        "-u", "--url",
        default=DEFAULT_URL,
        help=f"cAdvisor URL (default: {DEFAULT_URL})"
    )
    parser.add_argument(
        "-i", "--interval",
        type=float,
        default=1.0,
        help="Poll interval in seconds (default: 1.0)"
    )
    parser.add_argument(
        "-1", "--once",
        action="store_true",
        help="Run once and exit"
    )
    parser.add_argument(
        "-a", "--all",
        action="store_true",
        help="Show all stats (CPU, memory, network, disk)"
    )
    args = parser.parse_args()

    client = CAdvisorClient(args.url)
    net_tracker = NetworkRateTracker()

    # Initial container name fetch
    print("Fetching container names...")
    names = client.get_container_names()
    print(f"Found {len(names)} containers")

    try:
        while True:
            summaries = client.get_summaries()

            clear_screen()

            if args.all:
                stats = client.get_stats()
                net_rates = net_tracker.compute_rates(stats)
                print_full(summaries, stats, net_rates)
            else:
                print_compact(summaries)

            if args.once:
                break

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
