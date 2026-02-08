#!/bin/bash
# Test: Per-spoke shaping isolation
#
# Verifies that shaping on one drone's link does not affect other drones.
#
# Prerequisites: ./launch.py 3

set -euo pipefail

API="http://localhost:8080"
# drone1 is shaped: expect elevated loss
SHAPED_MIN_LOSS=5
# drone2->drone3 is unaffected: expect zero loss
UNSHAPED_MAX_LOSS=0

echo "=== Test: Per-Spoke Shaping Isolation ==="

# Restore all links
for i in 1 2 3; do
  curl -sf -X POST "${API}/drones/${i}/up" > /dev/null
done
sleep 2

# Apply 50ms delay, 20% loss to drone1 only
echo "Applying shaping to drone1 (50ms delay, 20% loss)..."
curl -sf -X POST "${API}/drones/1/link" \
  -H "Content-Type: application/json" \
  -d '{"delay_ms": 50, "loss_pct": 20, "rate_kbit": 1000}' > /dev/null

sleep 2

# drone1 -> drone2 (should be shaped)
echo "Pinging drone2 from drone1 (shaped)..."
output1=$(docker exec drone1_app ping -c 30 -q 172.31.0.12 || true)
echo "$output1"

loss1=$(echo "$output1" | grep -oP '\d+(?=% packet loss)')
if [ "$loss1" -lt "$SHAPED_MIN_LOSS" ]; then
  echo "FAIL: shaped link loss ${loss1}% below expected minimum ${SHAPED_MIN_LOSS}%"
  curl -sf -X POST "${API}/drones/1/up" > /dev/null
  exit 1
fi
echo "  shaped link loss: ${loss1}% (>= ${SHAPED_MIN_LOSS}% threshold)"

# drone2 -> drone3 (should be clean)
echo "Pinging drone3 from drone2 (unaffected)..."
output2=$(docker exec drone2_app ping -c 20 -q 172.31.0.13)
echo "$output2"

loss2=$(echo "$output2" | grep -oP '\d+(?=% packet loss)')
if [ "$loss2" -gt "$UNSHAPED_MAX_LOSS" ]; then
  echo "FAIL: unshaped link loss ${loss2}% exceeds threshold ${UNSHAPED_MAX_LOSS}%"
  curl -sf -X POST "${API}/drones/1/up" > /dev/null
  exit 1
fi
echo "  unshaped link loss: ${loss2}% (<= ${UNSHAPED_MAX_LOSS}% threshold)"

# Cleanup
curl -sf -X POST "${API}/drones/1/up" > /dev/null

echo "PASS: shaping isolated to drone1 (loss=${loss1}%), drone2->drone3 unaffected (loss=${loss2}%)"
