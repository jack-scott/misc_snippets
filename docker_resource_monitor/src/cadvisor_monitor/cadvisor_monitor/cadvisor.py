"""cAdvisor API client library.

Provides efficient access to container metrics from cAdvisor.
Optimized for low-bandwidth/CPU environments.

Example usage:
    from cadvisor import CAdvisorClient

    client = CAdvisorClient("http://localhost:8080")

    # Get all container summaries (CPU/memory with time periods)
    summaries = client.get_summaries()

    # Get full stats (includes network/disk)
    stats = client.get_stats()

    # Get specific container summary
    summary = client.get_container_summary("jellyfin")
"""

import time
import requests
from dataclasses import dataclass
from typing import Optional


@dataclass
class ContainerSummary:
    """Container summary with CPU/memory stats across time periods."""
    name: str
    path: str

    # Current values
    cpu_millicores: int
    memory_bytes: int

    # Minute averages
    cpu_1m_mean: int
    cpu_1m_max: int
    memory_1m_mean: int
    memory_1m_max: int

    # Hour averages
    cpu_1h_mean: int
    cpu_1h_max: int
    cpu_1h_p95: int
    memory_1h_mean: int
    memory_1h_max: int


@dataclass
class ContainerStats:
    """Full container stats including network and disk."""
    name: str
    path: str

    # CPU (cumulative nanoseconds)
    cpu_total_ns: int
    cpu_user_ns: int
    cpu_system_ns: int

    # Memory
    memory_usage: int
    memory_working_set: int
    memory_cache: int

    # Network (cumulative bytes)
    net_rx_bytes: int
    net_tx_bytes: int

    # Disk IO (cumulative bytes)
    disk_read_bytes: int
    disk_write_bytes: int

    # Filesystem
    fs_usage_bytes: int


class CAdvisorClient:
    """Client for cAdvisor API.

    Uses efficient v2.0 API endpoints which are ~10x smaller than v1.3.
    Caches container names to reduce API calls.
    """

    def __init__(self, base_url: str, timeout: int = 10, name_cache_ttl: int = 30):
        """Initialize the client.

        Args:
            base_url: cAdvisor URL (e.g., "http://localhost:8080")
            timeout: Request timeout in seconds
            name_cache_ttl: How long to cache container names (seconds)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.name_cache_ttl = name_cache_ttl

        self._container_names: dict[str, str] = {}  # path -> name
        self._container_paths: dict[str, str] = {}  # name -> path
        self._last_name_refresh: float = 0

    def _get(self, endpoint: str) -> dict:
        """Make a GET request to the API."""
        url = f"{self.base_url}{endpoint}"
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def refresh_container_names(self) -> dict[str, str]:
        """Fetch container names from spec endpoint.

        Returns:
            Dict mapping container path to friendly name.
        """
        data = self._get("/api/v2.0/spec?recursive=true")

        names = {}
        paths = {}
        for path, spec in data.items():
            if "docker-" not in path:
                continue

            labels = spec.get("labels", {})
            name = (
                labels.get("com.docker.compose.service") or
                labels.get("name") or
                path.split("/")[-1].replace(".scope", "").replace("docker-", "")[:12]
            )

            names[path] = name
            paths[name] = path

        self._container_names = names
        self._container_paths = paths
        self._last_name_refresh = time.time()
        return names

    def get_container_names(self, force_refresh: bool = False) -> dict[str, str]:
        """Get container path to name mapping.

        Args:
            force_refresh: Force refresh even if cache is valid.

        Returns:
            Dict mapping container path to friendly name.
        """
        if force_refresh or time.time() - self._last_name_refresh > self.name_cache_ttl:
            self.refresh_container_names()
        return self._container_names

    def get_container_path(self, name: str) -> Optional[str]:
        """Get container path by name.

        Args:
            name: Container name.

        Returns:
            Container path or None if not found.
        """
        self.get_container_names()
        return self._container_paths.get(name)

    def get_summaries(self, docker_only: bool = True) -> list[ContainerSummary]:
        """Fetch summaries for all containers.

        Uses the efficient summary endpoint (~72KB for all containers).
        Includes CPU/memory with minute/hour aggregations.

        Args:
            docker_only: Only return docker containers (default True).

        Returns:
            List of ContainerSummary objects.
        """
        names = self.get_container_names()
        data = self._get("/api/v2.0/summary?recursive=true")

        summaries = []
        for path, summary in data.items():
            if docker_only and "docker-" not in path:
                continue

            name = names.get(path, path.split("/")[-1][:15])
            latest = summary.get("latest_usage", {})
            minute = summary.get("minute_usage", {})
            hour = summary.get("hour_usage", {})

            cpu_min = minute.get("cpu", {})
            cpu_hr = hour.get("cpu", {})
            mem_min = minute.get("memory", {})
            mem_hr = hour.get("memory", {})

            summaries.append(ContainerSummary(
                name=name,
                path=path,
                cpu_millicores=latest.get("cpu", 0),
                memory_bytes=latest.get("memory", 0),
                cpu_1m_mean=cpu_min.get("mean", 0) if cpu_min.get("present") else 0,
                cpu_1m_max=cpu_min.get("max", 0) if cpu_min.get("present") else 0,
                memory_1m_mean=int(mem_min.get("mean", 0)) if mem_min.get("present") else 0,
                memory_1m_max=int(mem_min.get("max", 0)) if mem_min.get("present") else 0,
                cpu_1h_mean=cpu_hr.get("mean", 0) if cpu_hr.get("present") else 0,
                cpu_1h_max=cpu_hr.get("max", 0) if cpu_hr.get("present") else 0,
                cpu_1h_p95=cpu_hr.get("ninetyfive", 0) if cpu_hr.get("present") else 0,
                memory_1h_mean=int(mem_hr.get("mean", 0)) if mem_hr.get("present") else 0,
                memory_1h_max=int(mem_hr.get("max", 0)) if mem_hr.get("present") else 0,
            ))

        return summaries

    def get_container_summary(self, name: str) -> Optional[ContainerSummary]:
        """Fetch summary for a specific container by name.

        More efficient than get_summaries() when you only need one container.
        ~1KB per container vs ~72KB for all.

        Args:
            name: Container name.

        Returns:
            ContainerSummary or None if not found.
        """
        path = self.get_container_path(name)
        if not path:
            return None

        data = self._get(f"/api/v2.0/summary{path}")
        summary = data.get(path)
        if not summary:
            return None

        latest = summary.get("latest_usage", {})
        minute = summary.get("minute_usage", {})
        hour = summary.get("hour_usage", {})

        cpu_min = minute.get("cpu", {})
        cpu_hr = hour.get("cpu", {})
        mem_min = minute.get("memory", {})
        mem_hr = hour.get("memory", {})

        return ContainerSummary(
            name=name,
            path=path,
            cpu_millicores=latest.get("cpu", 0),
            memory_bytes=latest.get("memory", 0),
            cpu_1m_mean=cpu_min.get("mean", 0) if cpu_min.get("present") else 0,
            cpu_1m_max=cpu_min.get("max", 0) if cpu_min.get("present") else 0,
            memory_1m_mean=int(mem_min.get("mean", 0)) if mem_min.get("present") else 0,
            memory_1m_max=int(mem_min.get("max", 0)) if mem_min.get("present") else 0,
            cpu_1h_mean=cpu_hr.get("mean", 0) if cpu_hr.get("present") else 0,
            cpu_1h_max=cpu_hr.get("max", 0) if cpu_hr.get("present") else 0,
            cpu_1h_p95=cpu_hr.get("ninetyfive", 0) if cpu_hr.get("present") else 0,
            memory_1h_mean=int(mem_hr.get("mean", 0)) if mem_hr.get("present") else 0,
            memory_1h_max=int(mem_hr.get("max", 0)) if mem_hr.get("present") else 0,
        )

    def get_stats(self, docker_only: bool = True) -> list[ContainerStats]:
        """Fetch full stats for all containers.

        Uses stats endpoint (~375KB for all containers).
        Includes CPU, memory, network, and disk metrics.

        Args:
            docker_only: Only return docker containers (default True).

        Returns:
            List of ContainerStats objects.
        """
        names = self.get_container_names()
        data = self._get("/api/v2.0/stats?count=1&recursive=true")

        stats_list = []
        for path, stat_data in data.items():
            if docker_only and "docker-" not in path:
                continue
            if not stat_data:
                continue

            name = names.get(path, path.split("/")[-1][:15])
            stat = stat_data[0]

            # CPU
            cpu = stat.get("cpu", {}).get("usage", {})

            # Memory
            memory = stat.get("memory", {})

            # Network
            network = stat.get("network", {})
            interfaces = network.get("interfaces", [])
            rx_bytes = sum(iface.get("rx_bytes", 0) for iface in interfaces)
            tx_bytes = sum(iface.get("tx_bytes", 0) for iface in interfaces)

            # Disk IO
            diskio = stat.get("diskio", {})
            io_bytes = diskio.get("io_service_bytes", [])
            read_bytes = sum(d.get("stats", {}).get("Read", 0) for d in io_bytes)
            write_bytes = sum(d.get("stats", {}).get("Write", 0) for d in io_bytes)

            # Filesystem
            filesystems = stat.get("filesystem", [])
            fs_usage = sum(fs.get("usage", 0) for fs in filesystems)

            stats_list.append(ContainerStats(
                name=name,
                path=path,
                cpu_total_ns=cpu.get("total", 0),
                cpu_user_ns=cpu.get("user", 0),
                cpu_system_ns=cpu.get("system", 0),
                memory_usage=memory.get("usage", 0),
                memory_working_set=memory.get("working_set", 0),
                memory_cache=memory.get("cache", 0),
                net_rx_bytes=rx_bytes,
                net_tx_bytes=tx_bytes,
                disk_read_bytes=read_bytes,
                disk_write_bytes=write_bytes,
                fs_usage_bytes=fs_usage,
            ))

        return stats_list

    def get_container_stats(self, name: str) -> Optional[ContainerStats]:
        """Fetch full stats for a specific container by name.

        More efficient than get_stats() when you only need one container.
        ~6KB per container vs ~375KB for all.

        Args:
            name: Container name.

        Returns:
            ContainerStats or None if not found.
        """
        path = self.get_container_path(name)
        if not path:
            return None

        data = self._get(f"/api/v2.0/stats{path}?count=1")
        stat_data = data.get(path)
        if not stat_data:
            return None

        stat = stat_data[0]

        # CPU
        cpu = stat.get("cpu", {}).get("usage", {})

        # Memory
        memory = stat.get("memory", {})

        # Network
        network = stat.get("network", {})
        interfaces = network.get("interfaces", [])
        rx_bytes = sum(iface.get("rx_bytes", 0) for iface in interfaces)
        tx_bytes = sum(iface.get("tx_bytes", 0) for iface in interfaces)

        # Disk IO
        diskio = stat.get("diskio", {})
        io_bytes = diskio.get("io_service_bytes", [])
        read_bytes = sum(d.get("stats", {}).get("Read", 0) for d in io_bytes)
        write_bytes = sum(d.get("stats", {}).get("Write", 0) for d in io_bytes)

        # Filesystem
        filesystems = stat.get("filesystem", [])
        fs_usage = sum(fs.get("usage", 0) for fs in filesystems)

        return ContainerStats(
            name=name,
            path=path,
            cpu_total_ns=cpu.get("total", 0),
            cpu_user_ns=cpu.get("user", 0),
            cpu_system_ns=cpu.get("system", 0),
            memory_usage=memory.get("usage", 0),
            memory_working_set=memory.get("working_set", 0),
            memory_cache=memory.get("cache", 0),
            net_rx_bytes=rx_bytes,
            net_tx_bytes=tx_bytes,
            disk_read_bytes=read_bytes,
            disk_write_bytes=write_bytes,
            fs_usage_bytes=fs_usage,
        )
