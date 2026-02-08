#!/bin/bash
# Test: Inter-drone connectivity via radio
#
# Verifies that app containers can reach other drones through the veth pair
# and radio sidecar.
#
# Prerequisites: ./launch.py 3

set -euo pipefail

echo "=== Test: Inter-Drone Connectivity ==="

# Restore all links to clean state
for i in 1 2 3; do
  curl -sf -X POST "http://localhost:8080/drones/${i}/up" > /dev/null
done
sleep 2

# Verify veth route exists in drone1_app
echo "Checking route in drone1_app..."
route_output=$(docker exec drone1_app ip route show 172.31.0.0/24)
echo "  $route_output"
if ! echo "$route_output" | grep -q "10.100.1.2"; then
  echo "FAIL: route to 172.31.0.0/24 via 10.100.1.2 not found"
  exit 1
fi

# Verify veth interface exists
echo "Checking veth interface in drone1_app..."
if ! docker exec drone1_app ip link show veth-d1-app > /dev/null 2>&1; then
  echo "FAIL: veth-d1-app interface not found in drone1_app"
  exit 1
fi

# Ping drone2 from drone1 app container
echo "Pinging drone2 (172.31.0.12) from drone1_app..."
output=$(docker exec drone1_app ping -c 5 -q 172.31.0.12)
echo "$output"

loss=$(echo "$output" | grep -oP '\d+(?=% packet loss)')
if [ "$loss" -ne 0 ]; then
  echo "FAIL: expected 0% loss, got ${loss}%"
  exit 1
fi

# Ping drone1 from drone2 app container
echo "Pinging drone1 (172.31.0.11) from drone2_app..."
output=$(docker exec drone2_app ping -c 5 -q 172.31.0.11)
echo "$output"

loss=$(echo "$output" | grep -oP '\d+(?=% packet loss)')
if [ "$loss" -ne 0 ]; then
  echo "FAIL: expected 0% loss, got ${loss}%"
  exit 1
fi

echo "PASS: inter-drone connectivity works via veth pairs"
