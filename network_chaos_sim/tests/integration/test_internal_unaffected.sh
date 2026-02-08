#!/bin/bash
# Test: Internal traffic unaffected by spoke shaping
#
# Verifies that communication between a drone's own containers has no added
# latency or loss, even with aggressive shaping on the radio link.
#
# Prerequisites: ./launch.py 3

set -euo pipefail

API="http://localhost:8080"
DRONE=1
MAX_RTT_MS=5
MAX_LOSS_PCT=0

echo "=== Test: Internal Traffic Unaffected ==="

# Apply heavy shaping to drone1
echo "Applying heavy shaping to drone ${DRONE} (200ms delay, 50% loss, 100kbit)..."
curl -sf -X POST "${API}/drones/${DRONE}/link" \
  -H "Content-Type: application/json" \
  -d '{"delay_ms": 200, "loss_pct": 50, "rate_kbit": 100}' > /dev/null

sleep 2

# Ping from app container to radio container on the internal network
echo "Pinging radio from app on internal network..."
output=$(docker exec drone${DRONE}_app ping -c 20 -q 10.${DRONE}.0.2)
echo "$output"

# Parse loss percentage
loss=$(echo "$output" | grep -oP '\d+(?=% packet loss)')
if [ "$loss" -gt "$MAX_LOSS_PCT" ]; then
  echo "FAIL: packet loss ${loss}% exceeds threshold ${MAX_LOSS_PCT}%"
  curl -sf -X POST "${API}/drones/${DRONE}/up" > /dev/null
  exit 1
fi

# Parse average RTT
avg_rtt=$(echo "$output" | grep -oP 'rtt min/avg/max/mdev = [\d.]+/([\d.]+)' | grep -oP '[\d.]+$')
# Compare as integers (truncate to ms)
avg_rtt_int=$(printf "%.0f" "$avg_rtt")
if [ "$avg_rtt_int" -gt "$MAX_RTT_MS" ]; then
  echo "FAIL: average RTT ${avg_rtt}ms exceeds threshold ${MAX_RTT_MS}ms"
  curl -sf -X POST "${API}/drones/${DRONE}/up" > /dev/null
  exit 1
fi

echo "Restoring link..."
curl -sf -X POST "${API}/drones/${DRONE}/up" > /dev/null

echo "PASS: internal traffic unaffected (loss=${loss}%, avg_rtt=${avg_rtt}ms)"
