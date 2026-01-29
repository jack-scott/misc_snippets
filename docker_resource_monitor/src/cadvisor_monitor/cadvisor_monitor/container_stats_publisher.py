#!/usr/bin/env python3
"""ROS 2 node that publishes container statistics from cAdvisor."""

import rclpy
from rclpy.node import Node
from rclpy.time import Time
from builtin_interfaces.msg import Time as TimeMsg
from statistics_msgs.msg import MetricsMessage, StatisticDataPoint

from .cadvisor import CAdvisorClient, ContainerSummary


# StatisticDataType constants (from statistics_msgs)
STATISTICS_DATA_TYPE_AVERAGE = 1
STATISTICS_DATA_TYPE_MINIMUM = 2
STATISTICS_DATA_TYPE_MAXIMUM = 3
STATISTICS_DATA_TYPE_STDDEV = 4
STATISTICS_DATA_TYPE_SAMPLE_COUNT = 5


class ContainerStatsPublisher(Node):
    """Node that publishes container statistics from cAdvisor."""

    def __init__(self):
        super().__init__('container_stats_publisher')

        # Declare parameters
        self.declare_parameter('cadvisor_url', 'http://localhost:8080')
        self.declare_parameter('publish_rate', 1.0)  # Hz
        self.declare_parameter('name_refresh_interval', 30)  # seconds

        # Get parameters
        cadvisor_url = self.get_parameter('cadvisor_url').get_parameter_value().string_value
        publish_rate = self.get_parameter('publish_rate').get_parameter_value().double_value
        name_refresh = self.get_parameter('name_refresh_interval').get_parameter_value().integer_value

        self.get_logger().info(f'Connecting to cAdvisor at {cadvisor_url}')

        # Initialize cAdvisor client
        self.client = CAdvisorClient(
            base_url=cadvisor_url,
            timeout=10,
            name_cache_ttl=name_refresh
        )

        # Create publishers for different metric types
        # Using separate topics for easier filtering
        self.cpu_pub = self.create_publisher(MetricsMessage, 'container_stats/cpu', 10)
        self.memory_pub = self.create_publisher(MetricsMessage, 'container_stats/memory', 10)

        # Timer for publishing
        timer_period = 1.0 / publish_rate
        self.timer = self.create_timer(timer_period, self.publish_stats)

        # Track window timing
        self.last_publish_time = self.get_clock().now()

        self.get_logger().info(f'Publishing container stats at {publish_rate} Hz')

    def _make_time_msg(self, ros_time: Time) -> TimeMsg:
        """Convert ROS Time to TimeMsg."""
        msg = TimeMsg()
        msg.sec = int(ros_time.nanoseconds // 1_000_000_000)
        msg.nanosec = int(ros_time.nanoseconds % 1_000_000_000)
        return msg

    def _create_cpu_message(self, summary: ContainerSummary, window_start: Time, window_stop: Time) -> MetricsMessage:
        """Create a MetricsMessage for CPU stats."""
        msg = MetricsMessage()
        msg.measurement_source_name = 'cadvisor'
        msg.metrics_source = f'{summary.name}/cpu'
        msg.unit = 'millicores'
        msg.window_start = self._make_time_msg(window_start)
        msg.window_stop = self._make_time_msg(window_stop)

        # Current value as average (it's instantaneous)
        current = StatisticDataPoint()
        current.data_type = STATISTICS_DATA_TYPE_AVERAGE
        current.data = float(summary.cpu_millicores)
        msg.statistics.append(current)

        # 1-minute average
        avg_1m = StatisticDataPoint()
        avg_1m.data_type = STATISTICS_DATA_TYPE_AVERAGE
        avg_1m.data = float(summary.cpu_1m_mean)
        msg.statistics.append(avg_1m)

        # 1-minute max
        max_1m = StatisticDataPoint()
        max_1m.data_type = STATISTICS_DATA_TYPE_MAXIMUM
        max_1m.data = float(summary.cpu_1m_max)
        msg.statistics.append(max_1m)

        # 1-hour average
        avg_1h = StatisticDataPoint()
        avg_1h.data_type = STATISTICS_DATA_TYPE_AVERAGE
        avg_1h.data = float(summary.cpu_1h_mean)
        msg.statistics.append(avg_1h)

        # 1-hour max
        max_1h = StatisticDataPoint()
        max_1h.data_type = STATISTICS_DATA_TYPE_MAXIMUM
        max_1h.data = float(summary.cpu_1h_max)
        msg.statistics.append(max_1h)

        return msg

    def _create_memory_message(self, summary: ContainerSummary, window_start: Time, window_stop: Time) -> MetricsMessage:
        """Create a MetricsMessage for memory stats."""
        msg = MetricsMessage()
        msg.measurement_source_name = 'cadvisor'
        msg.metrics_source = f'{summary.name}/memory'
        msg.unit = 'bytes'
        msg.window_start = self._make_time_msg(window_start)
        msg.window_stop = self._make_time_msg(window_stop)

        # Current value
        current = StatisticDataPoint()
        current.data_type = STATISTICS_DATA_TYPE_AVERAGE
        current.data = float(summary.memory_bytes)
        msg.statistics.append(current)

        # 1-minute average
        avg_1m = StatisticDataPoint()
        avg_1m.data_type = STATISTICS_DATA_TYPE_AVERAGE
        avg_1m.data = float(summary.memory_1m_mean)
        msg.statistics.append(avg_1m)

        # 1-minute max
        max_1m = StatisticDataPoint()
        max_1m.data_type = STATISTICS_DATA_TYPE_MAXIMUM
        max_1m.data = float(summary.memory_1m_max)
        msg.statistics.append(max_1m)

        # 1-hour average
        avg_1h = StatisticDataPoint()
        avg_1h.data_type = STATISTICS_DATA_TYPE_AVERAGE
        avg_1h.data = float(summary.memory_1h_mean)
        msg.statistics.append(avg_1h)

        # 1-hour max
        max_1h = StatisticDataPoint()
        max_1h.data_type = STATISTICS_DATA_TYPE_MAXIMUM
        max_1h.data = float(summary.memory_1h_max)
        msg.statistics.append(max_1h)

        return msg

    def publish_stats(self):
        """Fetch and publish container statistics."""
        window_start = self.last_publish_time
        window_stop = self.get_clock().now()

        try:
            summaries = self.client.get_summaries()

            for summary in summaries:
                # Publish CPU stats
                cpu_msg = self._create_cpu_message(summary, window_start, window_stop)
                self.cpu_pub.publish(cpu_msg)

                # Publish memory stats
                mem_msg = self._create_memory_message(summary, window_start, window_stop)
                self.memory_pub.publish(mem_msg)

            self.get_logger().debug(f'Published stats for {len(summaries)} containers')

        except Exception as e:
            self.get_logger().error(f'Failed to fetch/publish stats: {e}')

        self.last_publish_time = window_stop


def main(args=None):
    rclpy.init(args=args)

    node = ContainerStatsPublisher()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
