# MANET Chaos Simulator

Network chaos testing for drone MANET (Mobile Ad-hoc Network) simulation.

**Features:**
- Affects ALL traffic types: ICMP (ping), UDP, and TCP
- Uses Linux `tc netem` for kernel-level chaos injection
- Veth-pair routing bypasses Docker bridge networking (no br_netfilter issues)
- Real-time metrics: ping latency, TCP connectivity, UDP connectivity
- Web UI for visualization and control
- Controller API for programmatic link control

## Quick Start

```bash
# Launch 3 drones
./launch.py 3

# Open UI
open http://localhost:8080

# Stop everything
./launch.py down
```

## File Structure

```
network_chaos_sim/
├── launch.py                 # Launcher (creates veth pairs + starts containers)
├── docker-compose.yml        # Control plane (UI)
├── drone/
│   ├── compose.radio.yml     # Infrastructure (DO NOT MODIFY)
│   └── compose.app.yml       # Your drone software (CUSTOMIZE THIS)
├── radio/
│   └── radio.py              # Chaos injection + probes
├── ui/
│   └── app.py                # Web UI + controller API
└── tests/
    ├── test_radio.py          # Unit tests
    ├── conftest.py            # Test fixtures
    └── integration/           # Integration test scripts
```

## Architecture

```
App Container                    Radio Container
┌─────────────────┐             ┌──────────────────────┐
│  eth0 (bridge)  │  internal   │  eth1 (internal)     │
│  10.1.0.3       │←── bridge →│  10.1.0.2            │
│                 │  (ARP/API) │                       │
│  veth-d1-app    │             │  veth-d1-radio       │
│  10.100.1.1/30  │←── veth ──→│  10.100.1.2/30       │
└─────────────────┘  (routed   │                       │
                     traffic)   │  eth0 (manet)        │
                                │  172.31.0.11         │──→ other drones
                                └──────────────────────┘
```

- **Internal bridge** (eth0↔eth1): Direct container-to-container API calls (e.g. `curl radio:8080`). Same subnet, no br_netfilter issues.
- **Veth pair**: Inter-drone routed traffic (172.31.0.0/24). Bypasses Docker bridge entirely — no br_netfilter drops.
- **Manet bridge** (eth0 on radio): Radio-to-radio communication. tc netem shaping applied here.

`launch.py` creates the veth pairs automatically after starting containers. It uses a temporary `--privileged` container to create the veth pair on the host and move each end into the correct container namespace, then configures addressing and routing via `docker exec`.

## Customizing Your Drone

Edit `drone/compose.app.yml` to add your services:

```yaml
services:
  my_drone_app:
    image: your-image:latest
    container_name: drone${DRONE_ID}_myapp
    cap_add:
      - NET_ADMIN
    environment:
      - DRONE_ID=${DRONE_ID}
      - DRONE_COUNT=${DRONE_COUNT}
    command:
      - sh
      - -c
      - |
        apk add --no-cache iproute2
        # Route to other drones is set up by launch.py via veth pair
        exec your-app
    networks:
      - internal
    depends_on:
      - radio

networks:
  internal:
    name: drone${DRONE_ID}_internal
```

**Key points:**
- Use `${DRONE_ID}` and `${DRONE_COUNT}` environment variables
- Connect services to the `internal` network only
- Keep `NET_ADMIN` capability (needed for veth configuration by launch.py)
- Other drones are reachable at `172.31.0.1X` where X is the drone ID

## Controller API

```bash
# Set absolute link parameters for a drone
curl -X POST http://localhost:8080/drones/1/link \
  -H "Content-Type: application/json" \
  -d '{"delay_ms": 50, "loss_pct": 10, "rate_kbit": 500}'

# Simulate drone out of range (100% loss)
curl -X POST http://localhost:8080/drones/1/down

# Restore drone to normal operation
curl -X POST http://localhost:8080/drones/1/up

# Set aggregate radio bandwidth for all drones
curl -X POST http://localhost:8080/radio/bandwidth \
  -H "Content-Type: application/json" \
  -d '{"rate_kbit": 2000}'

# Get aggregated status from all radios
curl http://localhost:8080/status
```

## UI API

```bash
# Get all link metrics
curl http://localhost:8080/api/metrics

# Set drone position
curl -X POST http://localhost:8080/api/position/1 \
  -H "Content-Type: application/json" \
  -d '{"x": 100, "y": 200, "z": 50}'

# Set link override (extra latency/loss)
curl -X POST http://localhost:8080/api/link/1/2 \
  -H "Content-Type: application/json" \
  -d '{"extra_latency_ms": 100, "extra_loss_percent": 10}'

# Clear link override
curl -X DELETE http://localhost:8080/api/link/1/2
```

## Testing

```bash
# Unit tests
pixi run pytest tests/test_radio.py -v

# Integration tests (requires running simulator: ./launch.py 3)
./tests/integration/test_connectivity.sh
./tests/integration/test_internal_unaffected.sh
./tests/integration/test_per_spoke_shaping.sh
./tests/integration/test_dynamic_link_control.sh
./tests/integration/test_route_injection.sh
./tests/integration/test_cleanup.sh          # tears down the simulator
```

## Scaling

```bash
./launch.py 5   # 5 drones
./launch.py 10  # 10 drones (may be slow)
```
