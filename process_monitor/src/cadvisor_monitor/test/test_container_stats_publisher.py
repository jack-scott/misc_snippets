import unittest

import rclpy
from rclpy.time import Time

from cadvisor_monitor.cadvisor import ContainerSummary
from cadvisor_monitor.container_stats_publisher import (
    STATISTICS_DATA_TYPE_AVERAGE,
    STATISTICS_DATA_TYPE_MAXIMUM,
    ContainerStatsPublisher,
)


def _make_summary(**overrides):
    defaults = dict(
        name="testcontainer",
        path="/system.slice/docker-abc123.scope",
        cpu_millicores=150,
        memory_bytes=524288000,
        cpu_1m_mean=120,
        cpu_1m_max=200,
        memory_1m_mean=500000000,
        memory_1m_max=600000000,
        cpu_1h_mean=100,
        cpu_1h_max=250,
        cpu_1h_p95=220,
        memory_1h_mean=480000000,
        memory_1h_max=650000000,
    )
    defaults.update(overrides)
    return ContainerSummary(**defaults)


class TestMakeTimeMsg(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def setUp(self):
        self.node = ContainerStatsPublisher()

    def tearDown(self):
        self.node.destroy_node()

    def test_sec_extracted_correctly(self):
        expected_sec = 1234567890
        msg = self.node._make_time_msg(Time(seconds=expected_sec, nanoseconds=0))
        self.assertEqual(msg.sec, expected_sec)

    def test_nanosec_extracted_correctly(self):
        expected_nanosec = 123456789
        msg = self.node._make_time_msg(Time(seconds=1, nanoseconds=expected_nanosec))
        self.assertEqual(msg.nanosec, expected_nanosec)

    def test_nanosec_overflow_splits_into_sec(self):
        # 1s + 500ms passed as 1_500_000_000 total nanoseconds
        msg = self.node._make_time_msg(Time(seconds=1, nanoseconds=500_000_000))
        self.assertEqual(msg.sec, 1)
        self.assertEqual(msg.nanosec, 500_000_000)


class TestCreateCpuMessage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def setUp(self):
        self.node = ContainerStatsPublisher()
        self.window_start = Time(seconds=100, nanoseconds=0)
        self.window_stop = Time(seconds=101, nanoseconds=0)

    def tearDown(self):
        self.node.destroy_node()

    def _make_msg(self, **summary_overrides):
        return self.node._create_cpu_message(
            _make_summary(**summary_overrides), self.window_start, self.window_stop
        )

    def test_has_five_statistics(self):
        self.assertEqual(len(self._make_msg().statistics), 5)

    def test_source_name_and_unit(self):
        msg = self._make_msg(name="jellyfin")
        self.assertEqual(msg.measurement_source_name, "cadvisor")
        self.assertEqual(msg.metrics_source, "jellyfin/cpu")
        self.assertEqual(msg.unit, "millicores")

    def test_current_value_at_index_0(self):
        expected = 175
        stat = self._make_msg(cpu_millicores=expected).statistics[0]
        self.assertEqual(stat.data_type, STATISTICS_DATA_TYPE_AVERAGE)
        self.assertEqual(stat.data, float(expected))

    def test_1m_mean_at_index_1(self):
        expected = 120
        stat = self._make_msg(cpu_1m_mean=expected).statistics[1]
        self.assertEqual(stat.data_type, STATISTICS_DATA_TYPE_AVERAGE)
        self.assertEqual(stat.data, float(expected))

    def test_1m_max_at_index_2(self):
        expected = 200
        stat = self._make_msg(cpu_1m_max=expected).statistics[2]
        self.assertEqual(stat.data_type, STATISTICS_DATA_TYPE_MAXIMUM)
        self.assertEqual(stat.data, float(expected))

    def test_1h_mean_at_index_3(self):
        expected = 100
        stat = self._make_msg(cpu_1h_mean=expected).statistics[3]
        self.assertEqual(stat.data_type, STATISTICS_DATA_TYPE_AVERAGE)
        self.assertEqual(stat.data, float(expected))

    def test_1h_max_at_index_4(self):
        expected = 250
        stat = self._make_msg(cpu_1h_max=expected).statistics[4]
        self.assertEqual(stat.data_type, STATISTICS_DATA_TYPE_MAXIMUM)
        self.assertEqual(stat.data, float(expected))


class TestCreateMemoryMessage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def setUp(self):
        self.node = ContainerStatsPublisher()
        self.window_start = Time(seconds=100, nanoseconds=0)
        self.window_stop = Time(seconds=101, nanoseconds=0)

    def tearDown(self):
        self.node.destroy_node()

    def _make_msg(self, **summary_overrides):
        return self.node._create_memory_message(
            _make_summary(**summary_overrides), self.window_start, self.window_stop
        )

    def test_has_five_statistics(self):
        self.assertEqual(len(self._make_msg().statistics), 5)

    def test_source_name_and_unit(self):
        msg = self._make_msg(name="jellyfin")
        self.assertEqual(msg.measurement_source_name, "cadvisor")
        self.assertEqual(msg.metrics_source, "jellyfin/memory")
        self.assertEqual(msg.unit, "bytes")

    def test_current_value_at_index_0(self):
        expected = 524288000
        stat = self._make_msg(memory_bytes=expected).statistics[0]
        self.assertEqual(stat.data_type, STATISTICS_DATA_TYPE_AVERAGE)
        self.assertEqual(stat.data, float(expected))

    def test_1m_mean_at_index_1(self):
        expected = 500000000
        stat = self._make_msg(memory_1m_mean=expected).statistics[1]
        self.assertEqual(stat.data_type, STATISTICS_DATA_TYPE_AVERAGE)
        self.assertEqual(stat.data, float(expected))

    def test_1m_max_at_index_2(self):
        expected = 600000000
        stat = self._make_msg(memory_1m_max=expected).statistics[2]
        self.assertEqual(stat.data_type, STATISTICS_DATA_TYPE_MAXIMUM)
        self.assertEqual(stat.data, float(expected))

    def test_1h_mean_at_index_3(self):
        expected = 480000000
        stat = self._make_msg(memory_1h_mean=expected).statistics[3]
        self.assertEqual(stat.data_type, STATISTICS_DATA_TYPE_AVERAGE)
        self.assertEqual(stat.data, float(expected))

    def test_1h_max_at_index_4(self):
        expected = 650000000
        stat = self._make_msg(memory_1h_max=expected).statistics[4]
        self.assertEqual(stat.data_type, STATISTICS_DATA_TYPE_MAXIMUM)
        self.assertEqual(stat.data, float(expected))


if __name__ == "__main__":
    unittest.main()
