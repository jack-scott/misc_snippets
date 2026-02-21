# Drone Network Chaos Simulator

Technical Design Document

# 1. Problem Statement

We need to simulate a multi-drone MANET (Mobile Ad-hoc Network) where each drone runs a stack of services inside Docker containers. The simulation must satisfy:

- Any container within a drone's stack can send TCP/UDP/ICMP traffic to containers on other drones using a stable radio IP address (172.31.0.1X)
- Internal communication between a drone's own services is completely unaffected by network simulation
- Each radio has a shared aggregate bandwidth cap (HTB qdisc) representing the physical radio's total throughput
- Per-link quality (latency, loss) is independently calculated based on 3D position, environment profile, and optional manual overrides
- Link quality is adjustable at runtime via an HTTP API on each radio
- Both mesh (all-to-all) and star (via base station) topologies are supported

# 2. Architecture Overview

## 2.1 Shared Network Namespace Design

All containers within a drone share the radio's network namespace via Docker's `network_mode: "service:radio"`. This mirrors a real drone where all software shares the same network interfaces provided by the radio hardware.

- **Radio sidecar** (`droneX_radio`): A Python-based network emulator on the MANET mesh network. It handles traffic shaping (tc/netem), link quality calculation, probing, and exposes an HTTP API for control.
- **App container(s)** (`droneX_app1`, `droneX_app2`, etc.): The drone's actual software. They share the radio's network namespace and can bind directly to the MANET IP.

Because all containers share the same netns:
- Apps bind to `0.0.0.0:<port>` and are reachable at `172.31.0.1X:<port>` from other drones
- Inter-service comms within a drone go over localhost (the kernel routes local-destined traffic through loopback, bypassing the MANET interface entirely)
- Traffic to other drones exits through the MANET interface where tc rules apply shaping
- No NAT, no route injection, no veth pairs needed

## 2.2 Network Layout

Each drone's radio has two network attachments:

| Interface | Network | Address | Purpose |
|-----------|---------|---------|---------|
| ethX (manet) | `manet_mesh` (172.31.0.0/24) | 172.31.0.1N | Inter-drone radio traffic, tc rules applied here |
| ethY (control) | `manet_control` | DHCP | Control plane (UI communicates with radios) |

All app containers see these same interfaces via the shared network namespace. There is no internal bridge network.

## 2.3 Traffic Path

**Inter-drone: drone2_app1 sends to drone3_app2 (e.g., iperf to 172.31.0.13:5001)**

```
drone2_app1 (shares drone2_radio netns)
  -> binds to / sends from 172.31.0.12
  -> tc netem on manet interface (latency/loss/bandwidth shaping applied on egress)
  -> manet_mesh network
  -> drone3_radio (172.31.0.13)
  -> tc netem on drone3's manet interface (shaping applied on drone3's egress for return traffic)
  -> drone3_app2 receives on 172.31.0.13:5001 (same netns)
```

No NAT, no DNAT, no conntrack. Source IPs are preserved end-to-end.

**Intra-drone: drone2_app1 talks to drone2_app2**

```
drone2_app1 -> localhost / 172.31.0.12 -> kernel loopback -> drone2_app2
```

Traffic to a local IP is routed through loopback by the kernel. It never touches the MANET interface and is completely unaffected by tc shaping.

## 2.4 Component Summary

| Component | Quantity | Role |
|-----------|----------|------|
| Radio sidecar | 1 per drone | Shapes traffic, probes peers, exposes API |
| App container(s) | 1+ per drone | User's drone software (shared netns with radio) |
| Base station radio | 0 or 1 | Star topology hub (DRONE_ID=0) |
| Control plane UI | 1 | Web UI for visualization and runtime control |
| launch.py | 1 | Orchestrates startup: networks, compose stacks |

# 3. Traffic Shaping

## 3.1 HTB + Netem Per-Link Shaping

Each radio applies traffic control on its MANET interface (egress only):

```
HTB root (1:) - aggregate bandwidth cap
  |
  +-- HTB class (1:11) for peer drone 1 -> netem (delay, loss)
  +-- HTB class (1:12) for peer drone 2 -> netem (delay, loss)
  +-- HTB class (1:13) for peer drone 3 -> netem (delay, loss)
  +-- HTB class (1:99) default (unclassified traffic)
```

- **HTB root** caps total radio throughput (configurable via `config.yaml` or API)
- **Per-peer HTB classes** share the parent bandwidth with `ceil` equal to the parent rate
- **Netem qdiscs** on each class add latency (with jitter = delay/10) and packet loss
- **u32 filters** match `ip dst` to direct traffic to the correct class

## 3.2 Link Quality Calculation

Link quality between two drones is derived from:

1. **3D Euclidean distance** between their positions
2. **Threshold interpolation** - configurable distance/latency/loss breakpoints in `config.yaml`
3. **Environment multiplier** - weather profiles (clear, rain, fog, etc.) scale latency and loss
4. **Manual overrides** - per-link extra latency, extra loss, or full partition via API

In star topology, drone-to-drone quality reflects the two-hop path (drone -> base station -> drone): latencies add, losses compound.

## 3.3 Shaping Symmetry

Each radio independently shapes its outbound traffic per destination. For a link between drone A and drone B:
- Drone A's radio shapes A->B traffic (its outbound)
- Drone B's radio shapes B->A traffic (its outbound)

Since both calculate distance symmetrically, degradation is equal in both directions (unless manual overrides differ).

# 4. Topology Modes

## 4.1 Mesh

All drones can communicate directly with each other. Each radio creates tc classes for every other drone. Link quality is based on direct distance.

## 4.2 Star

All traffic routes through a base station (DRONE_ID=0, IP 172.31.0.10). Each drone's radio adds `/32` routes to send peer-destined traffic via the base station IP. The base station runs the same radio code with `DRONE_ID=0`, forwarding between drones without NAT (preserving source IPs).

Link quality for drone-to-drone traffic is the compound of two hops:
- Latency: `leg1_latency + leg2_latency`
- Loss: `1 - (1 - leg1_loss) * (1 - leg2_loss)`

Each drone only shapes its own leg (drone -> base station). The base station shapes the second leg (base station -> target drone).

# 5. Radio HTTP API

Each radio runs an HTTP server on port 8080 (accessible via the control network).

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Full state: position, probes, link quality, overrides, traffic |
| `/config` | GET | Loaded configuration |
| `/position` | POST | Update this drone's position `{x, y, z}` |
| `/positions/{id}` | POST | Update another drone's position (for coordinator broadcast) |
| `/environment` | POST | Set environment profile `{profile: "heavy_rain"}` |
| `/topology` | POST | Set topology mode `{mode: "mesh"\|"star"}` |
| `/link` | POST | Set absolute tc params `{delay_ms, loss_pct, rate_kbit}` |
| `/link_down` | POST | Simulate out-of-range (100% loss on all links) |
| `/link_up` | POST | Restore to distance-based calculation |
| `/bandwidth` | POST | Override aggregate bandwidth `{rate_kbit}` |
| `/link_override` | POST | Per-link override `{target, extra_latency_ms, extra_loss_percent, partition}` |
| `/link_override/{id}` | DELETE | Clear per-link override |

Each radio also runs probe servers:
- **TCP server** on port 9000 (echo)
- **UDP server** on port 9001 (echo)

Probes run on a 1-second cycle to each peer: ICMP ping, TCP connect, UDP echo. Traffic stats are updated and written to the shared metrics volume every 500ms on a separate timer, independent of probe completion.

# 6. Launch Process

`launch.py` orchestrates the full startup sequence:

1. Create shared Docker network `manet_mesh` (172.31.0.0/24) and volume `manet_metrics`
2. Start the control plane UI (`docker-compose.yml` - also creates the `manet_control` network)
3. Start base station if star topology (`base_station/compose.yml`)
4. For each drone: start radio + app stack (`drone/compose.radio.yml` + `drone/compose.app.yml`)

No post-startup network configuration is needed. App containers join the radio's network namespace via `network_mode: "service:radio"` and have immediate access to the MANET interface.

Teardown (`launch.py down`) stops all compose projects and removes the shared network.

# 7. File Structure

```
network_chaos_sim/
├── launch.py                  # Orchestrator: up/down
├── config.yaml                # Radio, distance, environment, topology config
├── docker-compose.yml         # Control plane UI
├── design_doc.md              # This document
├── radio/
│   ├── Dockerfile             # Python 3.11 Alpine + iproute2/iptables
│   └── radio.py               # Radio sidecar: shaping, API, probes
├── drone/
│   ├── compose.radio.yml      # Radio infrastructure (networks, radio service)
│   └── compose.app.yml        # User's drone software (customize this)
├── base_station/
│   └── compose.yml            # Base station for star topology
├── ui/
│   ├── Dockerfile
│   └── app.py                 # Web UI for visualization and control
├── tests/
│   └── ...
└── pixi.toml                  # Python dependency management
```

# 8. Addressing Scheme

| Network | Subnet | Purpose |
|---------|--------|---------|
| MANET mesh | 172.31.0.0/24 | Inter-drone radio traffic. Drone N = 172.31.0.1N, base station = 172.31.0.10 |
| Control network | DHCP | UI <-> radio API communication |

All containers within a drone share the radio's MANET IP. There are no per-service IPs. Apps reach other drones by sending to `172.31.0.1X`.

# 9. Host Safety

All resources are ephemeral and scoped to container network namespaces:

| Resource | Scope | Cleanup |
|----------|-------|---------|
| tc qdisc/filter/class | Inside radio container netns | Destroyed with container |
| ip_forward sysctl | Inside container netns; does not affect host | Destroyed with container |
| Docker networks | Docker-managed | Removed by `launch.py down` |

`launch.py` never modifies the host's routing table, iptables, or persistent network config. There are no privileged helper containers, no host namespace manipulation, and no veth pairs to clean up.

# 10. Limitations

### MANET IP scheme limits drone count to 9
The addressing `172.31.0.1{DRONE_ID}` means drone 10 would be `172.31.0.110`, which overflows the /24 subnet semantics. Max usable drones: 9 (IDs 1-9). Fixing this requires a different IP scheme (e.g., `172.31.0.{10 + DRONE_ID}`).

### Port conflicts in shared namespace
All containers in a drone share the same network namespace, so they cannot bind to the same port. The radio reserves ports 8080 (API), 9000 (TCP probe), and 9001 (UDP probe). App services must use different ports from each other and from the radio.

### tc netem is statistical
Loss and delay are probabilistic. Short test runs show high variance. Use 100+ packets for meaningful measurements.

### Shaping is egress-only
tc rules are applied on the MANET interface's egress path. Ingress traffic is not shaped at the receiving radio - it was already shaped by the sending radio's egress rules. This means each direction of a link is shaped independently.

# 11. Future Improvements

### Better MANET addressing
Switch to `172.31.0.{10 + DRONE_ID}` to support more drones, or use a larger subnet.

### Asymmetric link profiles
Currently link quality is symmetric (same distance = same degradation in both directions). Add support for asymmetric uplink/downlink characteristics per drone.

### Ingress shaping
Add IFB (Intermediate Functional Block) devices to shape incoming traffic, allowing the receiving radio to also enforce bandwidth limits on ingress.
