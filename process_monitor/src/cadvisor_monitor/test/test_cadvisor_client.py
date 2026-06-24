import time
import unittest
from unittest.mock import MagicMock, patch

from cadvisor_monitor.cadvisor import CAdvisorClient
import scipy

SPEC_RESPONSE = {
    "/system.slice/docker-abc123.scope": {
        "labels": {"com.docker.compose.service": "jellyfin"}
    }
}

SUMMARY_RESPONSE = {
    "/system.slice/docker-abc123.scope": {
        "latest_usage": {"cpu": 150, "memory": 524288000},
        "minute_usage": {
            "cpu": {"present": True, "mean": 120, "max": 200},
            "memory": {"present": True, "mean": 500000000.0, "max": 600000000.0},
        },
        "hour_usage": {
            "cpu": {"present": True, "mean": 100, "max": 250, "ninetyfive": 220},
            "memory": {"present": True, "mean": 480000000.0, "max": 650000000.0},
        },
    },
    "/system.slice/not-docker.scope": {
        "latest_usage": {"cpu": 50, "memory": 100000},
        "minute_usage": {"cpu": {}, "memory": {}},
        "hour_usage": {"cpu": {}, "memory": {}},
    },
}

STATS_RESPONSE = {
    "/system.slice/docker-abc123.scope": [
        {
            "cpu": {"usage": {"total": 1000000000, "user": 600000000, "system": 400000000}},
            "memory": {"usage": 524288000, "working_set": 400000000, "cache": 100000000},
            "network": {
                "interfaces": [
                    {"rx_bytes": 1000, "tx_bytes": 500},
                    {"rx_bytes": 2000, "tx_bytes": 800},
                ]
            },
            "diskio": {
                "io_service_bytes": [
                    {"stats": {"Read": 4096, "Write": 8192}},
                    {"stats": {"Read": 1024, "Write": 2048}},
                ]
            },
            "filesystem": [
                {"usage": 1073741824},
                {"usage": 536870912},
            ],
        }
    ]
}


def _make_client():
    return CAdvisorClient("http://localhost:8080")


def _mock_get_for_summaries(client, summary_data=None):
    def mock_get(endpoint):
        if "spec" in endpoint:
            return SPEC_RESPONSE
        return summary_data if summary_data is not None else SUMMARY_RESPONSE

    client._get = mock_get


def _mock_get_for_stats(client, stats_data=None):
    def mock_get(endpoint):
        if "spec" in endpoint:
            return SPEC_RESPONSE
        return stats_data if stats_data is not None else STATS_RESPONSE

    client._get = mock_get


class TestRefreshContainerNames(unittest.TestCase):

    def test_compose_service_label_used_as_name(self):
        client = _make_client()
        client._get = MagicMock(return_value={
            "/system.slice/docker-abc123.scope": {
                "labels": {"com.docker.compose.service": "jellyfin"}
            }
        })
        names = client.refresh_container_names()
        self.assertEqual(names["/system.slice/docker-abc123.scope"], "jellyfin")

    def test_name_label_used_as_fallback(self):
        client = _make_client()
        client._get = MagicMock(return_value={
            "/system.slice/docker-abc123.scope": {"labels": {"name": "mycontainer"}}
        })
        names = client.refresh_container_names()
        self.assertEqual(names["/system.slice/docker-abc123.scope"], "mycontainer")

    def test_path_used_as_last_fallback(self):
        client = _make_client()
        client._get = MagicMock(return_value={
            "/system.slice/docker-abc1234567890abcdef.scope": {"labels": {}}
        })
        names = client.refresh_container_names()
        name = names["/system.slice/docker-abc1234567890abcdef.scope"]
        self.assertEqual(len(name), 12)
        self.assertTrue(name.startswith("abc"))

    def test_compose_label_takes_priority_over_name_label(self):
        client = _make_client()
        client._get = MagicMock(return_value={
            "/system.slice/docker-abc123.scope": {
                "labels": {
                    "com.docker.compose.service": "compose-name",
                    "name": "name-label",
                }
            }
        })
        names = client.refresh_container_names()
        self.assertEqual(names["/system.slice/docker-abc123.scope"], "compose-name")

    def test_non_docker_paths_skipped(self):
        client = _make_client()
        client._get = MagicMock(return_value={
            "/system.slice/other-service.scope": {
                "labels": {"com.docker.compose.service": "nginx"}
            }
        })
        names = client.refresh_container_names()
        self.assertEqual(len(names), 0)

    def test_reverse_lookup_populated(self):
        client = _make_client()
        client._get = MagicMock(return_value={
            "/system.slice/docker-abc123.scope": {
                "labels": {"com.docker.compose.service": "jellyfin"}
            }
        })
        client.refresh_container_names()
        self.assertEqual(
            client._container_paths["jellyfin"], "/system.slice/docker-abc123.scope"
        )


class TestContainerNameCache(unittest.TestCase):

    def test_cache_not_refreshed_within_ttl(self):
        client = CAdvisorClient("http://localhost:8080", name_cache_ttl=60)
        client._last_name_refresh = time.time()
        client._container_names = {"existing": "data"}

        with patch.object(client, "refresh_container_names") as mock_refresh:
            client.get_container_names()
            mock_refresh.assert_not_called()

    def test_cache_refreshed_after_ttl(self):
        client = CAdvisorClient("http://localhost:8080", name_cache_ttl=60)
        client._last_name_refresh = time.time() - 120

        with patch.object(client, "refresh_container_names", return_value={}) as mock_refresh:
            client.get_container_names()
            mock_refresh.assert_called_once()

    def test_force_refresh_ignores_cache(self):
        client = CAdvisorClient("http://localhost:8080", name_cache_ttl=60)
        client._last_name_refresh = time.time()

        with patch.object(client, "refresh_container_names", return_value={}) as mock_refresh:
            client.get_container_names(force_refresh=True)
            mock_refresh.assert_called_once()


class TestGetSummaries(unittest.TestCase):

    def test_parses_all_summary_fields(self):
        client = _make_client()
        _mock_get_for_summaries(client)
        summaries = client.get_summaries()

        self.assertEqual(len(summaries), 1)
        s = summaries[0]
        self.assertEqual(s.name, "jellyfin")
        self.assertEqual(s.cpu_millicores, 150)
        self.assertEqual(s.memory_bytes, 524288000)
        self.assertEqual(s.cpu_1m_mean, 120)
        self.assertEqual(s.cpu_1m_max, 200)
        self.assertEqual(s.memory_1m_mean, 500000000)
        self.assertEqual(s.memory_1m_max, 600000000)
        self.assertEqual(s.cpu_1h_mean, 100)
        self.assertEqual(s.cpu_1h_max, 250)
        self.assertEqual(s.cpu_1h_p95, 220)
        self.assertEqual(s.memory_1h_mean, 480000000)
        self.assertEqual(s.memory_1h_max, 650000000)

    def test_zeros_stats_when_not_present(self):
        not_present = {
            "/system.slice/docker-abc123.scope": {
                "latest_usage": {"cpu": 50, "memory": 100000},
                "minute_usage": {
                    "cpu": {"present": False, "mean": 999},
                    "memory": {"present": False, "mean": 999},
                },
                "hour_usage": {
                    "cpu": {"present": False, "mean": 999, "max": 999, "ninetyfive": 999},
                    "memory": {"present": False, "mean": 999, "max": 999},
                },
            }
        }
        client = _make_client()
        _mock_get_for_summaries(client, not_present)
        s = client.get_summaries()[0]

        self.assertEqual(s.cpu_1m_mean, 0)
        self.assertEqual(s.cpu_1m_max, 0)
        self.assertEqual(s.memory_1m_mean, 0)
        self.assertEqual(s.memory_1m_max, 0)
        self.assertEqual(s.cpu_1h_mean, 0)
        self.assertEqual(s.cpu_1h_max, 0)
        self.assertEqual(s.cpu_1h_p95, 0)
        self.assertEqual(s.memory_1h_mean, 0)
        self.assertEqual(s.memory_1h_max, 0)

    def test_filters_non_docker_by_default(self):
        client = _make_client()
        _mock_get_for_summaries(client)
        paths = [s.path for s in client.get_summaries()]
        self.assertNotIn("/system.slice/not-docker.scope", paths)

    def test_includes_non_docker_when_flag_off(self):
        client = _make_client()
        _mock_get_for_summaries(client)
        paths = [s.path for s in client.get_summaries(docker_only=False)]
        self.assertIn("/system.slice/not-docker.scope", paths)


class TestGetStats(unittest.TestCase):

    def test_parses_cpu_and_memory(self):
        client = _make_client()
        _mock_get_for_stats(client)
        stats = client.get_stats()

        self.assertEqual(len(stats), 1)
        s = stats[0]
        self.assertEqual(s.cpu_total_ns, 1000000000)
        self.assertEqual(s.cpu_user_ns, 600000000)
        self.assertEqual(s.cpu_system_ns, 400000000)
        self.assertEqual(s.memory_usage, 524288000)
        self.assertEqual(s.memory_working_set, 400000000)
        self.assertEqual(s.memory_cache, 100000000)

    def test_sums_network_across_interfaces(self):
        client = _make_client()
        _mock_get_for_stats(client)
        s = client.get_stats()[0]
        self.assertEqual(s.net_rx_bytes, 3000)   # 1000 + 2000
        self.assertEqual(s.net_tx_bytes, 1300)   # 500 + 800

    def test_sums_disk_io_across_devices(self):
        client = _make_client()
        _mock_get_for_stats(client)
        s = client.get_stats()[0]
        self.assertEqual(s.disk_read_bytes, 5120)    # 4096 + 1024
        self.assertEqual(s.disk_write_bytes, 10240)  # 8192 + 2048

    def test_sums_filesystem_usage(self):
        client = _make_client()
        _mock_get_for_stats(client)
        s = client.get_stats()[0]
        self.assertEqual(s.fs_usage_bytes, 1610612736)  # 1073741824 + 536870912

    def test_skips_containers_with_empty_stat_data(self):
        client = _make_client()
        _mock_get_for_stats(client, {"/system.slice/docker-abc123.scope": []})
        self.assertEqual(len(client.get_stats()), 0)


if __name__ == "__main__":
    unittest.main()
