import pytest
import rclpy
from diagnostic_msgs.msg import DiagnosticStatus
from diagnostic_updater import DiagnosticStatusWrapper
from rclpy.time import Time

from cadvisor_monitor.cadvisor import ContainerSummary
from cadvisor_monitor.container_stats_publisher import (
    STATISTICS_DATA_TYPE_AVERAGE,
    STATISTICS_DATA_TYPE_MAXIMUM,
    ContainerStatsPublisher,
)


@pytest.fixture(scope="session")
def ros_session():
    rclpy.init()
    yield
    rclpy.shutdown()


@pytest.fixture
def node(ros_session):
    n = ContainerStatsPublisher()
    yield n
    n.destroy_node()


@pytest.fixture
def window():
    return Time(seconds=100, nanoseconds=0), Time(seconds=101, nanoseconds=0)


def make_summary(**overrides):
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


# ── _make_time_msg ────────────────────────────────────────────────────────────

def test_time_msg_sec(node):
    msg = node._make_time_msg(Time(seconds=1234567890, nanoseconds=0))
    assert msg.sec == 1234567890


def test_time_msg_nanosec(node):
    msg = node._make_time_msg(Time(seconds=1, nanoseconds=123456789))
    assert msg.nanosec == 123456789


def test_time_msg_nanosec_overflow_splits_into_sec(node):
    msg = node._make_time_msg(Time(seconds=1, nanoseconds=500_000_000))
    assert msg.sec == 1
    assert msg.nanosec == 500_000_000


# ── _create_cpu_message ───────────────────────────────────────────────────────

def test_cpu_message_has_five_statistics(node, window):
    msg = node._create_cpu_message(make_summary(), *window)
    assert len(msg.statistics) == 5


def test_cpu_message_source_and_unit(node, window):
    msg = node._create_cpu_message(make_summary(name="jellyfin"), *window)
    assert msg.measurement_source_name == "cadvisor"
    assert msg.metrics_source == "jellyfin/cpu"
    assert msg.unit == "millicores"


def test_cpu_current_value_at_index_0(node, window):
    msg = node._create_cpu_message(make_summary(cpu_millicores=175), *window)
    assert msg.statistics[0].data_type == STATISTICS_DATA_TYPE_AVERAGE
    assert msg.statistics[0].data == 175.0


def test_cpu_1m_mean_at_index_1(node, window):
    msg = node._create_cpu_message(make_summary(cpu_1m_mean=120), *window)
    assert msg.statistics[1].data_type == STATISTICS_DATA_TYPE_AVERAGE
    assert msg.statistics[1].data == 120.0


def test_cpu_1m_max_at_index_2(node, window):
    msg = node._create_cpu_message(make_summary(cpu_1m_max=200), *window)
    assert msg.statistics[2].data_type == STATISTICS_DATA_TYPE_MAXIMUM
    assert msg.statistics[2].data == 200.0


def test_cpu_1h_mean_at_index_3(node, window):
    msg = node._create_cpu_message(make_summary(cpu_1h_mean=100), *window)
    assert msg.statistics[3].data_type == STATISTICS_DATA_TYPE_AVERAGE
    assert msg.statistics[3].data == 100.0


def test_cpu_1h_max_at_index_4(node, window):
    msg = node._create_cpu_message(make_summary(cpu_1h_max=250), *window)
    assert msg.statistics[4].data_type == STATISTICS_DATA_TYPE_MAXIMUM
    assert msg.statistics[4].data == 250.0


# ── _create_memory_message ────────────────────────────────────────────────────

def test_memory_message_has_five_statistics(node, window):
    msg = node._create_memory_message(make_summary(), *window)
    assert len(msg.statistics) == 5


def test_memory_message_source_and_unit(node, window):
    msg = node._create_memory_message(make_summary(name="jellyfin"), *window)
    assert msg.measurement_source_name == "cadvisor"
    assert msg.metrics_source == "jellyfin/memory"
    assert msg.unit == "bytes"


def test_memory_current_value_at_index_0(node, window):
    msg = node._create_memory_message(make_summary(memory_bytes=524288000), *window)
    assert msg.statistics[0].data_type == STATISTICS_DATA_TYPE_AVERAGE
    assert msg.statistics[0].data == 524288000.0


def test_memory_1m_mean_at_index_1(node, window):
    msg = node._create_memory_message(make_summary(memory_1m_mean=500000000), *window)
    assert msg.statistics[1].data_type == STATISTICS_DATA_TYPE_AVERAGE
    assert msg.statistics[1].data == 500000000.0


def test_memory_1m_max_at_index_2(node, window):
    msg = node._create_memory_message(make_summary(memory_1m_max=600000000), *window)
    assert msg.statistics[2].data_type == STATISTICS_DATA_TYPE_MAXIMUM
    assert msg.statistics[2].data == 600000000.0


def test_memory_1h_mean_at_index_3(node, window):
    msg = node._create_memory_message(make_summary(memory_1h_mean=480000000), *window)
    assert msg.statistics[3].data_type == STATISTICS_DATA_TYPE_AVERAGE
    assert msg.statistics[3].data == 480000000.0


def test_memory_1h_max_at_index_4(node, window):
    msg = node._create_memory_message(make_summary(memory_1h_max=650000000), *window)
    assert msg.statistics[4].data_type == STATISTICS_DATA_TYPE_MAXIMUM
    assert msg.statistics[4].data == 650000000.0


# ── _check_cadvisor_connectivity ──────────────────────────────────────────────

def test_diagnostics_error_before_first_success(node):
    stat = node._check_cadvisor_connectivity(DiagnosticStatusWrapper())
    assert stat.level == DiagnosticStatus.ERROR


def test_diagnostics_ok_after_success(node):
    node.last_success_time = node.get_clock().now()
    node.consecutive_failures = 0

    stat = node._check_cadvisor_connectivity(DiagnosticStatusWrapper())

    assert stat.level == DiagnosticStatus.OK


def test_diagnostics_warn_after_failure_following_a_success(node):
    node.last_success_time = node.get_clock().now()
    node.consecutive_failures = 3
    node.last_error = "connection refused"

    stat = node._check_cadvisor_connectivity(DiagnosticStatusWrapper())

    assert stat.level == DiagnosticStatus.WARN
    assert "connection refused" in stat.message


def test_diagnostics_reports_consecutive_failures(node):
    node.last_success_time = node.get_clock().now()
    node.consecutive_failures = 5

    stat = node._check_cadvisor_connectivity(DiagnosticStatusWrapper())

    values = {kv.key: kv.value for kv in stat.values}
    assert values["consecutive_failures"] == "5"


def test_diagnostics_omits_last_success_before_any_success(node):
    stat = node._check_cadvisor_connectivity(DiagnosticStatusWrapper())

    keys = {kv.key for kv in stat.values}
    assert "seconds_since_last_success" not in keys
