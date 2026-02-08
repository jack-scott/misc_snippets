#!/bin/bash
# Test: No residual host network state after teardown
#
# Verifies that tearing down the simulator leaves no veth pairs or
# manet-related interfaces on the host.
#
# Prerequisites: Simulator must be RUNNING before this test.
# This test will tear it down and check for residual state.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "=== Test: Full Cleanup ==="

echo "Tearing down simulator..."
"${SCRIPT_DIR}/launch.py" down 2>&1

sleep 5

# Check for residual veth interfaces from our setup
echo "Checking for residual veth-d* interfaces..."
residual=$(ip link show 2>/dev/null | grep -c "veth-d" || true)
if [ "$residual" -gt 0 ]; then
  echo "FAIL: found ${residual} residual veth-d* interfaces"
  ip link show | grep "veth-d"
  exit 1
fi

# Check manet_mesh network is gone
echo "Checking manet_mesh network removed..."
if docker network inspect manet_mesh > /dev/null 2>&1; then
  echo "FAIL: manet_mesh network still exists"
  exit 1
fi

# Check no drone containers remain
echo "Checking no drone containers remain..."
drone_containers=$(docker ps -q --filter "name=drone" 2>/dev/null | wc -l)
if [ "$drone_containers" -gt 0 ]; then
  echo "FAIL: ${drone_containers} drone container(s) still running"
  docker ps --filter "name=drone"
  exit 1
fi

echo "PASS: no residual interfaces, networks, or containers"
