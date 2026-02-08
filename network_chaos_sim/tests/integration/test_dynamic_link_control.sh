#!/bin/bash
# Test: Dynamic link control via API
#
# Sets specific loss values and verifies the ping results fall within expected
# bounds. Tests both a clean link and a lossy link.
#
# Prerequisites: ./launch.py 3

set -euo pipefail

API="http://localhost:8080"

echo "=== Test: Dynamic Link Control ==="

# Restore all links
for i in 1 2 3; do
  curl -sf -X POST "${API}/drones/${i}/up" > /dev/null
done
sleep 2

# Phase 1: clean link (0% loss) — expect 0% measured loss
echo "Setting drone1 link to 0% loss..."
curl -sf -X POST "${API}/drones/1/link" \
  -H "Content-Type: application/json" \
  -d '{"delay_ms": 10, "loss_pct": 0, "rate_kbit": 1000}' > /dev/null

sleep 2

echo "Pinging drone2 from drone1 (clean link)..."
output_clean=$(docker exec drone1_app ping -c 20 -q 172.31.0.12)
echo "$output_clean"

loss_clean=$(echo "$output_clean" | grep -oP '\d+(?=% packet loss)')
if [ "$loss_clean" -ne 0 ]; then
  echo "FAIL: clean link showed ${loss_clean}% loss (expected 0%)"
  curl -sf -X POST "${API}/drones/1/up" > /dev/null
  exit 1
fi

# Phase 2: 100% loss — expect all packets dropped
echo "Setting drone1 link to 100% loss..."
curl -sf -X POST "${API}/drones/1/link" \
  -H "Content-Type: application/json" \
  -d '{"delay_ms": 0, "loss_pct": 100, "rate_kbit": 1000}' > /dev/null

sleep 2

echo "Pinging drone2 from drone1 (100% loss)..."
output_full=$(docker exec drone1_app ping -c 10 -W 2 -q 172.31.0.12 || true)
echo "$output_full"

loss_full=$(echo "$output_full" | grep -oP '\d+(?=% packet loss)')
if [ "$loss_full" -ne 100 ]; then
  echo "FAIL: 100% loss link showed ${loss_full}% loss (expected 100%)"
  curl -sf -X POST "${API}/drones/1/up" > /dev/null
  exit 1
fi

# Phase 3: link_down / link_up API
echo "Testing link_down API..."
curl -sf -X POST "${API}/drones/1/up" > /dev/null
sleep 1
curl -sf -X POST "${API}/drones/1/down" > /dev/null
sleep 2

output_down=$(docker exec drone1_app ping -c 5 -W 2 -q 172.31.0.12 || true)
echo "$output_down"

loss_down=$(echo "$output_down" | grep -oP '\d+(?=% packet loss)')
if [ "$loss_down" -ne 100 ]; then
  echo "FAIL: link_down showed ${loss_down}% loss (expected 100%)"
  curl -sf -X POST "${API}/drones/1/up" > /dev/null
  exit 1
fi

# Cleanup
curl -sf -X POST "${API}/drones/1/up" > /dev/null

echo "PASS: dynamic link control works (clean=0%, full_loss=100%, down=100%)"
