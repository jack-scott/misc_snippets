#!/bin/bash
# Test: Route injection — all app containers can reach all other drones
#
# Verifies that veth pair setup by launch.py correctly routes traffic from
# every app container to every other drone's radio.
#
# Prerequisites: ./launch.py 3

set -euo pipefail

echo "=== Test: Route Injection ==="

# Restore all links
for i in 1 2 3; do
  curl -sf -X POST "http://localhost:8080/drones/${i}/up" > /dev/null
done
sleep 2

failures=0

for src in 1 2 3; do
  for dst in 1 2 3; do
    if [ "$src" -ne "$dst" ]; then
      echo -n "drone${src}_app -> 172.31.0.1${dst}: "
      if docker exec drone${src}_app ping -c 3 -W 2 -q 172.31.0.1${dst} > /dev/null 2>&1; then
        echo "OK"
      else
        echo "FAIL"
        failures=$((failures + 1))
      fi
    fi
  done
done

if [ "$failures" -gt 0 ]; then
  echo "FAIL: ${failures} route(s) failed"
  exit 1
fi

echo "PASS: all app containers can reach all other drones"
