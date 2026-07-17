"""Integration test: this node's diagnostics must aggregate cleanly.

Launches container_stats_publisher alongside diagnostic_aggregator, loaded
with this package's own shipped config/analyzers.yaml, and asserts that once
things have warmed up nothing on /diagnostics_agg is STALE and nothing fell
through to the aggregator's "Other" catch-all. A STALE or Other entry means a
diagnostic this node publishes isn't claimed by the analyzer config shipped
alongside it, which defeats the point of shipping them together.
"""

import atexit
import os
import tempfile
import time
import unittest

from ament_index_python.packages import get_package_share_directory
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
import launch
import launch_ros.actions
import launch_testing.actions
from launch_testing_ros import WaitForTopics
import pytest
import yaml

AGGREGATOR_BASE_PATH = 'Aggregation'


def _write_aggregator_params_file() -> str:
    """Wrap this package's analyzer fragment into a full aggregator_node params file."""
    fragment_path = os.path.join(
        get_package_share_directory('cadvisor_monitor'), 'config', 'analyzers.yaml'
    )
    with open(fragment_path) as f:
        fragment = yaml.safe_load(f)

    params = {'analyzers': {'ros__parameters': {'path': AGGREGATOR_BASE_PATH, **fragment}}}

    fd, path = tempfile.mkstemp(suffix='.yaml', prefix='aggregator_params_')
    with os.fdopen(fd, 'w') as f:
        yaml.safe_dump(params, f)
    atexit.register(os.remove, path)
    return path


@pytest.mark.launch_test
def generate_test_description():
    container_stats_publisher = launch_ros.actions.Node(
        package='cadvisor_monitor',
        executable='container_stats_publisher',
        # Unreachable on purpose: connectivity OK/ERROR doesn't matter for this
        # test, only that diagnostics keep flowing and land in the right bucket.
        parameters=[{'cadvisor_url': 'http://127.0.0.1:9'}],
    )
    aggregator = launch_ros.actions.Node(
        package='diagnostic_aggregator',
        executable='aggregator_node',
        parameters=[_write_aggregator_params_file()],
    )

    return launch.LaunchDescription([
        container_stats_publisher,
        aggregator,
        launch_testing.actions.ReadyToTest(),
    ])


class TestDiagnosticsAggregation(unittest.TestCase):

    def test_no_stale_or_unclaimed_diagnostics(self):
        with WaitForTopics(
            [('/diagnostics_agg', DiagnosticArray)], timeout=15.0, messages_received_buffer_length=10
        ) as waiter:
            # Let a few aggregation cycles pass so any startup-time STALE clears.
            time.sleep(8.0)
            messages = waiter.received_messages('/diagnostics_agg')

        self.assertTrue(messages, 'never received a /diagnostics_agg message')

        latest = messages[-1]
        other_prefix = f'/{AGGREGATOR_BASE_PATH}/Other'
        stale = [s.name for s in latest.status if s.level == DiagnosticStatus.STALE]
        unclaimed = [s.name for s in latest.status if s.name.startswith(other_prefix)]

        self.assertEqual(stale, [], f'diagnostics reported STALE: {stale}')
        self.assertEqual(
            unclaimed, [],
            f'diagnostics fell through to Other (add an analyzer for them in config/analyzers.yaml): {unclaimed}'
        )
