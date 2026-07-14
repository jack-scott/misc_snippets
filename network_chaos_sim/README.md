# MANET Chaos Simulator

Network chaos testing for drone MANET (Mobile Ad-hoc Network) simulation.
Each drone node runs a radio sidecar that applies kernel-level `tc netem` shaping
on inter-drone traffic. App containers share the radio's network namespace.

## Quick Start

```bash
# Radio only (no app)
./launch.py up 3

# With the flight controller experiment
./launch.py up 3 experiments/drone_fc/compose.yml

# Star topology (adds base station at 172.31.0.10)
./launch.py up 3 experiments/drone_fc/compose.yml --star

# No UI (headless)
./launch.py up 3 --no-ui

# Stop everything
./launch.py down
```

UI:       http://localhost:8080  
Foxglove: ws://localhost:8765  

## File Structure

```
network_chaos_sim/
├── launch.py                 # Generic multi-node orchestrator
├── config.yaml               # Radio, distance, environment, topology config
├── radio/
│   ├── radio.py              # Radio sidecar: tc shaping, probes, HTTP API
│   ├── Dockerfile
│   └── compose.yml           # Radio node (drones + base station via DRONE_ID)
├── control_plane/
│   ├── compose.yml           # Foxglove logger + creates manet_control network
│   └── foxglove_logger/
│       └── server.py
├── ui/
│   ├── app.py                # Web UI + controller API proxy
│   ├── Dockerfile
│   └── compose.yml           # Optional UI (separate from control plane)
└── experiments/
    └── drone_fc/             # Example: flight controller
        ├── compose.yml       # App overlay — copy this for new experiments
        └── fc/               # App source files
```

## Creating an Experiment

Copy `experiments/drone_fc/compose.yml` and point it at your service.
The only required line is `network_mode: "service:radio"` — that joins your
container into the radio's network namespace and gives it:

- `172.31.0.1N` — MANET IP reachable from other drones (goes through tc/netem)
- `127.0.0.1` — intra-drone localhost (bypasses shaping entirely)
- `foxglove_logger:9090` — clean backhaul on the control network
- `localhost:8080` — radio HTTP API (read link quality, set overrides)

```yaml
# experiments/my_algo/compose.yml
services:
  my_algo:
    build: ./src
    container_name: drone${DRONE_ID}_my_algo
    network_mode: "service:radio"
    environment:
      - DRONE_ID=${DRONE_ID}
      - DRONE_COUNT=${DRONE_COUNT}
    depends_on:
      - radio
```

```bash
./launch.py up 3 experiments/my_algo/compose.yml
```

## Radio HTTP API

Each radio exposes an API on port 8080 accessible via the control network
(or from within the same drone via localhost):

| Endpoint | Method | Description |
|---|---|---|
| `/status` | GET | Full state: position, link quality, probe results |
| `/position` | POST | Update drone position `{x, y, z}` |
| `/environment` | POST | Set weather profile `{profile: "heavy_rain"}` |
| `/topology` | POST | Switch mode `{mode: "mesh"\|"star"}` |
| `/link_override` | POST | Per-link tweak `{target, extra_latency_ms, extra_loss_percent}` |
| `/link_down` | POST | Simulate out-of-range (100% loss) |
| `/link_up` | POST | Restore distance-based quality |
| `/bandwidth` | POST | Override aggregate bandwidth `{rate_kbit}` |

The UI proxies these at `http://localhost:8080/drones/{id}/...`.

## Foxglove

Connect Foxglove Studio to `ws://localhost:8765`.

```bash
# Record MCAP session
RECORD_MCAP=true ./launch.py up 3
```

## Testing

```bash
# Unit tests
pixi run pytest tests/test_radio.py -v

# Integration tests (requires a running simulator)
./launch.py up 3
pixi run pytest tests/integration/ -v
./launch.py down
```
