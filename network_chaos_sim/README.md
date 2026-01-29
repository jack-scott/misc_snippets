# MANET Chaos Simulator

Network chaos testing for drone MANET (Mobile Ad-hoc Network) simulation.

**Features:**
- Affects ALL traffic types: ICMP (ping), UDP, and TCP
- Uses Linux `tc netem` for kernel-level chaos injection
- Real-time metrics: ping latency, TCP connectivity, UDP connectivity
- Web UI for visualization and control
- Drone software is separated from infrastructure for easy customization

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
├── launch.py                 # Launcher script
├── docker-compose.yml        # Control plane (UI)
├── drone/
│   ├── compose.radio.yml     # Infrastructure (DO NOT MODIFY)
│   └── compose.app.yml       # Your drone software (CUSTOMIZE THIS)
├── radio/
│   └── radio.py              # Chaos injection + probes
└── ui/
    └── app.py                # Web UI
```

## Customizing Your Drone

Edit `drone/compose.app.yml` to add your services:

```yaml
services:
  # Replace the example app with your drone software
  my_drone_app:
    image: your-image:latest
    container_name: drone${DRONE_ID}_myapp
    environment:
      - DRONE_ID=${DRONE_ID}
      - DRONE_COUNT=${DRONE_COUNT}
    networks:
      - internal
    depends_on:
      - radio

  # Add more services as needed
  ros_node:
    image: ros:humble
    container_name: drone${DRONE_ID}_ros
    environment:
      - ROS_DOMAIN_ID=${DRONE_ID}
    networks:
      - internal

networks:
  internal:
    name: drone${DRONE_ID}_internal
```

**Key points:**
- Use `${DRONE_ID}` and `${DRONE_COUNT}` environment variables
- Connect services to the `internal` network
- Add `depends_on: radio` to wait for network setup
- To reach other drones: `172.31.0.1X` where X is the drone ID

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Per Drone                           │
│  ┌─────────────────┐    ┌─────────────────┐         │
│  │  compose.app.yml │    │ compose.radio.yml│        │
│  │  (your software) │    │  (infrastructure)│        │
│  │                  │    │                  │        │
│  │  ┌───────────┐  │    │  ┌───────────┐  │        │
│  │  │  your app │  │    │  │   radio   │  │        │
│  │  └─────┬─────┘  │    │  │ (tc netem)│  │        │
│  │        │        │    │  └─────┬─────┘  │        │
│  └────────┼────────┘    └────────┼────────┘        │
│           │     internal         │                  │
│           └──────────────────────┘                  │
│                                  │ manet_mesh       │
└──────────────────────────────────┼──────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │        manet_mesh           │
                    │       172.31.0.0/24         │
                    └──────────────┬──────────────┘
                                   │
                         ┌─────────┴─────────┐
                         │      Web UI       │
                         │ localhost:8080    │
                         └───────────────────┘
```

## Web UI

Access http://localhost:8080 to:
- View network topology with live link status
- See ping latency, TCP, and UDP connectivity per link
- Click any link to add chaos
- Use presets: Good, Degraded, Bad, Lossy, Partition

## Chaos Types

| Type | Effect | Example |
|------|--------|---------|
| Latency | Delays packets | 200ms delay |
| Jitter | Latency variation | ±50ms |
| Packet Loss | Drops randomly | 10% loss |
| Bandwidth | Limits throughput | 100kbit/s |

All chaos affects ICMP, UDP, and TCP equally.

## API

```bash
# Get all link metrics
curl http://localhost:8080/api/links

# Add chaos (drone 1 -> drone 2)
curl -X POST http://localhost:8080/api/chaos/1/2 \
  -H "Content-Type: application/json" \
  -d '{"latency_ms": 200, "loss_percent": 10}'

# Clear chaos
curl -X DELETE http://localhost:8080/api/chaos/1/2
```

## Scaling

```bash
./launch.py 5   # 5 drones
./launch.py 10  # 10 drones (may be slow)
```
