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

## 2.1 Radio-Per-Drone Design

Each drone has two containers:

- **Radio sidecar** (`droneX_radio`): A Python-based network emulator that sits on both the MANET mesh network and the drone's internal network. It handles routing, NAT, traffic shaping (tc/netem), link quality calculation, probing, and exposes an HTTP API for control.
- **App container(s)** (`droneX_app`, plus any user-added services): The drone's actual software, running on the internal network only.

The radio sidecar acts as a router/gateway. App containers reach other drones by routing through the radio. The radio applies tc netem rules on the MANET interface to simulate link degradation per destination.

## 2.2 Network Layout

Each drone N has three network attachments on the radio:

| Interface | Network | Address | Purpose |
|-----------|---------|---------|---------|
| ethX (manet) | `manet_mesh` (172.31.0.0/24) | 172.31.0.1N | Inter-drone radio traffic, tc rules applied here |
| ethY (control) | `manet_control` | DHCP | Control plane (UI communicates with radios) |
| ethZ (internal) | `droneN_internal` (10.N.0.0/16) | 10.N.0.2 | Internal comms with app containers |

Additionally, a **veth pair** connects each app container directly to its radio:

| End | Address | Location |
|-----|---------|----------|
| `veth-dN-app` | 10.100.N.1/30 | Inside app container |
| `veth-dN-radio` | 10.100.N.2/30 | Inside radio container |

The veth pair bypasses Docker bridge networking for routed inter-drone traffic. This avoids issues with `br_netfilter`, which can drop or interfere with packets whose destination IP is outside the bridge subnet (see Section 2.3).

## 2.3 Why Veth Pairs Instead of Docker Bridge Routing

Docker's `br_netfilter` kernel module causes host-level iptables rules to be applied to bridged (layer-2) traffic. When a container on a Docker bridge sends a packet to an IP outside the bridge's subnet (e.g., 172.31.0.X from a 10.N.0.0/16 bridge), the host's iptables FORWARD chain can drop it before it ever reaches the gateway container.

Veth pairs are point-to-point kernel links between two network namespaces. They do not traverse any bridge and are invisible to `br_netfilter`. By routing inter-drone traffic over a veth directly from the app to the radio, we completely sidestep this issue.

## 2.4 Traffic Path

**Outbound: drone2_app sends to drone3_app (e.g., iperf to 172.31.0.13:5001)**

```
drone2_app (10.100.2.1)
  -> ip route 172.31.0.0/24 via 10.100.2.2
  -> veth pair to drone2_radio (10.100.2.2)
  -> MASQUERADE (src rewritten: 10.100.2.1 -> 172.31.0.12)
  -> tc netem on manet interface (latency/loss/bandwidth shaping applied)
  -> manet_mesh network
  -> drone3_radio (172.31.0.13)
  -> DNAT (dst rewritten: 172.31.0.13 -> 10.100.3.1)
  -> FORWARD via veth pair
  -> drone3_app (10.100.3.1)
```

**Return path is handled automatically by conntrack** - reply packets are de-DNATted and de-MASQUERADEd in reverse.

**Internal traffic (drone2_app to drone2_radio on 10.2.0.X)** stays on the Docker bridge and is never shaped.

## 2.5 NAT Rules on Each Radio

```
# Outbound: rewrite app's veth source to the radio's manet IP
iptables -t nat -A POSTROUTING -o <manet_iface> -s 10.100.N.0/30 -j MASQUERADE

# Inbound: forward manet traffic to the app via veth
# (exclude radio's own service ports)
iptables -t nat -A PREROUTING -i <manet_iface> -d 172.31.0.1N -p tcp --dport 8080 -j ACCEPT
iptables -t nat -A PREROUTING -i <manet_iface> -d 172.31.0.1N -p tcp --dport 9000 -j ACCEPT
iptables -t nat -A PREROUTING -i <manet_iface> -d 172.31.0.1N -p udp --dport 9001 -j ACCEPT
iptables -t nat -A PREROUTING -i <manet_iface> -d 172.31.0.1N -j DNAT --to-destination 10.100.N.1

# Allow forwarding between veth and manet
iptables -P FORWARD ACCEPT
```

## 2.6 Component Summary

| Component | Quantity | Role |
|-----------|----------|------|
| Radio sidecar | 1 per drone | Routes, NATs, shapes, probes, exposes API |
| App container(s) | 1+ per drone | User's drone software on internal network |
| Base station radio | 0 or 1 | Star topology hub (DRONE_ID=0) |
| Control plane UI | 1 | Web UI for visualization and runtime control |
| launch.py | 1 | Orchestrates startup: networks, compose stacks, veth pairs |

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

Probes run every 2 seconds to each peer: ICMP ping, TCP connect, UDP echo. Results are written to a shared metrics volume as JSON.

# 6. Launch Process

`launch.py` orchestrates the full startup sequence:

1. Create shared Docker network `manet_mesh` (172.31.0.0/24) and volume `manet_metrics`
2. Start the control plane UI (`docker-compose.yml`)
3. Start base station if star topology (`base_station/compose.yml`)
4. For each drone: start radio + app stack (`drone/compose.radio.yml` + `drone/compose.app.yml`)
5. Create veth pairs connecting each app container to its radio container:
   - Get PIDs of app and radio containers
   - Run a privileged Alpine container with host network/PID namespace to create veth pairs and move them into the correct namespaces
   - Configure IP addressing and routes inside each container via `docker exec`

Teardown (`launch.py down`) stops all compose projects, cleans up residual veth pairs from the host namespace, and removes the shared network.

# 7. File Structure

```
network_chaos_sim/
├── launch.py                  # Orchestrator: up/down, veth setup
├── config.yaml                # Radio, distance, environment, topology config
├── docker-compose.yml         # Control plane UI
├── design_doc.md              # This document
├── radio/
│   ├── Dockerfile             # Python 3.11 Alpine + iproute2/iptables
│   └── radio.py               # Radio sidecar: routing, shaping, API, probes
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
| Drone N internal bridge | 10.N.0.0/16 | Internal comms within drone N. Radio = 10.N.0.2, gateway = 10.N.0.1 |
| Drone N veth pair | 10.100.N.0/30 | Point-to-point app-to-radio link. App = 10.100.N.1, radio = 10.100.N.2 |
| Control network | DHCP | UI <-> radio API communication |

App containers reach other drones via: `ip route add 172.31.0.0/24 via 10.100.N.2`

# 9. Host Safety

All resources are ephemeral and scoped to container network namespaces:

| Resource | Scope | Cleanup |
|----------|-------|---------|
| veth pairs | Kernel; destroyed when either container is removed | Automatic (+ explicit cleanup in `launch.py down`) |
| tc qdisc/filter/class | Inside radio container netns | Destroyed with container |
| iptables NAT/FORWARD rules | Inside radio container netns | Destroyed with container |
| ip_forward sysctl | Inside container netns; does not affect host | Destroyed with container |
| Docker networks | Docker-managed | Removed by `launch.py down` |

`launch.py` never modifies the host's routing table, iptables, or persistent network config.

# 10. Limitations

### MANET IP scheme limits drone count to 9
The addressing `172.31.0.1{DRONE_ID}` means drone 10 would be `172.31.0.110`, which overflows the /24 subnet semantics. Max usable drones: 9 (IDs 1-9). Fixing this requires a different IP scheme (e.g., `172.31.0.{10 + DRONE_ID}`).

### Veth pair is per-app-container, not per-network
The veth pair connects a single app container to the radio. If multiple services are defined in `compose.app.yml`, only the `app` service gets the veth. Other services on the internal bridge can route through the radio's bridge IP (10.N.0.2) but may hit `br_netfilter` issues. See Section 11 for solutions.

### NAT hides source identity
MASQUERADE rewrites the source IP to the radio's MANET address. The receiving drone sees traffic as coming from `172.31.0.1X`, not the original internal service IP. Per-source-service visibility is lost at the receiving end.

### Container restarts break veth pairs
If a radio or app container restarts, its veth pair and routes are lost. The simulator must be relaunched (`launch.py down` then `launch.py N`).

### tc netem is statistical
Loss and delay are probabilistic. Short test runs show high variance. Use 100+ packets for meaningful measurements.

### No inbound port mapping granularity
The DNAT rule forwards all non-radio traffic to the single app container's veth IP. There is no way to direct specific ports to different internal services.

# 11. Future Improvements

### Bridge-level veth for multi-service support
Instead of connecting the veth to a single app container, attach one end to the Docker bridge (`droneN_internal`) itself. All containers on the bridge would then benefit from the veth routing without needing individual veth pairs. This would require modifying `launch.py` to create the veth with one end in the radio container and the other added as a port on the Docker bridge.

Alternatively, widen the MASQUERADE source match to include the full bridge subnet (`10.N.0.0/16`) and add a route on each service container (`172.31.0.0/24 via 10.N.0.2`) to go through the Docker bridge to the radio. This is simpler but reintroduces `br_netfilter` exposure for the internal leg - testing is needed to confirm whether this causes problems in practice.

### Better MANET addressing
Switch to `172.31.0.{10 + DRONE_ID}` to support more drones, or use a larger subnet.

### DNAT port mapping
Allow `compose.app.yml` to declare port mappings so that specific inbound ports on the MANET IP can be directed to different internal services.

### Asymmetric link profiles
Currently link quality is symmetric (same distance = same degradation in both directions). Add support for asymmetric uplink/downlink characteristics per drone.

### Container restart resilience
Detect container restarts and automatically re-establish veth pairs and routes without a full relaunch.
