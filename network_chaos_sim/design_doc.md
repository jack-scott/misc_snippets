**Drone Network Simulator**

Technical Design Document

*Star Topology with Gateway-Per-Drone, Central Radio Hub, and Per-Link Network Emulation*

# **1\. Problem Statement**

We need to simulate a multi-drone radio network where each drone is represented by a Docker Compose stack of approximately 20 services (database, control, telemetry, etc.) running on a shared internal Docker bridge network. The simulation must satisfy the following requirements:

* Any container within a drone’s stack may send traffic to containers on other drones using radio IP addresses

* Internal communication between a drone’s own services (e.g., database ↔ control stack) must be **completely unaffected** by network simulation — no added latency, loss, or bandwidth limits

* A central radio hub models the shared radio hardware, with an aggregate bandwidth cap representing the radio’s total throughput

* Per-drone link quality (latency, loss, bandwidth) is independently controllable

* Link quality is adjustable at runtime via an API, driven by simulated drone distance

The previous approach of routing through a NAT gateway on a Docker bridge failed because Docker’s bridge netfilter (br\_netfilter) dropped packets with destination IPs outside the bridge subnet before they reached the gateway container. This document describes a replacement architecture that uses veth pairs to bypass Docker bridge networking entirely for inter-drone traffic.

# **2\. Architecture Overview**

## **2.1 Gateway-Per-Drone Design**

Each drone’s Docker Compose stack gets one additional lightweight container: a gateway. This gateway container sits on the drone’s internal Docker bridge network (alongside all 20 existing services) and also has a veth pair connecting it to the central radio hub. It runs with IP forwarding enabled and acts as the next hop for any traffic destined for other drones.

The key principle: all traffic between a drone’s own services stays on the internal Docker bridge and is never shaped. Only traffic destined for another drone’s IP range is routed through the gateway, across the veth to the radio hub, and out to the destination drone’s gateway. Shaping is applied exclusively on the veth links.

The full path for a packet from drone1’s database to drone2’s control service:

drone1 database (10.1.0.5)

  → drone1 internal bridge (unmodified Docker network, no shaping)

  → drone1 gateway (10.1.0.100) \[ip\_forward\]

  → veth to radio hub \[tc netem: drone1 spoke shaping\]

  → radio hub \[tc htb: aggregate bandwidth cap\]

  → veth to drone2 gateway \[tc netem: drone2 spoke shaping\]

  → drone2 gateway (10.2.0.100) \[ip\_forward\]

  → drone2 internal bridge (unmodified Docker network, no shaping)

  → drone2 control service (10.2.0.8)

Internal traffic (e.g., drone1’s database talking to drone1’s control stack) never leaves the internal bridge and is completely unaffected.

## **2.2 Why the Gateway Avoids the br\_netfilter Problem**

The original design failed because packets with destination IPs outside the Docker bridge’s subnet were dropped by host-level iptables rules applied via br\_netfilter. In this design, the gateway container’s external interface is a veth pair — a point-to-point kernel link between two network namespaces. Veth pairs do not traverse any Docker bridge and are not subject to br\_netfilter. The gateway’s internal interface is on the Docker bridge, but traffic flowing through it to other services on the same bridge has matching subnet IPs, so br\_netfilter does not interfere.

## **2.3 Component Summary**

| Component | Quantity | Role |
| :---- | :---- | :---- |
| Drone service containers | \~20 per drone | Run unmodified drone software on internal bridge |
| Gateway container | 1 per drone | Routes inter-drone traffic; on internal bridge \+ veth to radio hub |
| Radio hub container | 1 total | Central star hub; forwards between all gateway veths; aggregate bandwidth cap |
| Controller API | 1 total | REST API for runtime tc netem updates; runs privileged on host PID namespace |
| Setup script | 1 total | Creates veth pairs, assigns IPs, configures routes and tc after docker compose up |

# **3\. Component Details**

## **3.1 Gateway Container**

Each drone adds a gateway service to its existing docker-compose.yml. The gateway is a minimal Alpine container with iproute2 and IP forwarding enabled. It has two interfaces:

* **Internal (eth0):** Connected to the drone’s existing Docker bridge network. Given a static IP (e.g., 10.1.0.100 for drone1). All other services on the drone use this as their gateway for inter-drone traffic.

* **External (veth):** A veth endpoint attached by the setup script after container creation. Connected to the radio hub. Carries only inter-drone traffic, shaped by tc netem.

The gateway performs NAT (MASQUERADE) on outbound traffic so that return packets from the radio hub are correctly routed back. This is necessary because the radio hub and destination drone only see the gateway’s veth address, not the internal service IPs.

Gateway container configuration:

\# Inside the gateway container (done by entrypoint or setup script)

sysctl \-w net.ipv4.ip\_forward=1

\# NAT outbound traffic on the veth interface

iptables \-t nat \-A POSTROUTING \-o veth-gw1-radio \-j MASQUERADE

\# Accept forwarding in both directions

iptables \-A FORWARD \-i eth0 \-o veth-gw1-radio \-j ACCEPT

iptables \-A FORWARD \-i veth-gw1-radio \-o eth0 \\

    \-m state \--state RELATED,ESTABLISHED \-j ACCEPT

Unlike the previous failed design, the MASQUERADE and FORWARD rules here work correctly because they’re applied inside the gateway’s own network namespace on a veth interface — not on a Docker bridge port. The host’s br\_netfilter never sees this traffic.

## **3.2 Routing Inside Drone Services**

Every service container in a drone’s stack needs one additional route to direct inter-drone traffic to the gateway. This is the only change to existing drone services.

\# Added to each service container (via entrypoint, or by the setup script)

\# For drone1, where gateway is at 10.1.0.100:

ip route add 10.100.0.0/16 via 10.1.0.100

The 10.100.0.0/16 range covers all radio hub and gateway veth addresses. Traffic to internal services (10.1.0.0/16 for drone1) is unaffected because the more-specific Docker bridge route takes precedence. Only traffic to other drones matches this route and gets sent to the gateway.

There are several ways to inject this route:

* **Option A — Entrypoint wrapper:** Add the ip route command to each service’s entrypoint script. Requires NET\_ADMIN capability on each service container.

* **Option B — Setup script with nsenter:** The host-side setup script uses nsenter to add the route inside each container’s netns after startup. No changes to service images required, but the setup script needs to enumerate all containers.

* **Option C — Docker Compose extra\_hosts \+ custom DNS:** Less clean; routes are more reliable than DNS for this purpose. Options A or B are recommended.

## **3.3 Radio Hub Container**

The radio hub is a single container that acts as the central star hub. After the setup script attaches all gateway veth endpoints, it has N interfaces (one per drone). It forwards packets between them and applies an aggregate bandwidth cap using tc htb on an IFB device.

Radio hub configuration:

\# Enable forwarding

sysctl \-w net.ipv4.ip\_forward=1

\# Aggregate bandwidth cap via IFB (applied to all forwarded traffic)

ip link add ifb0 type ifb

ip link set ifb0 up

tc qdisc add dev ifb0 root handle 1: htb default 10

tc class add dev ifb0 parent 1: classid 1:10 htb \\

    rate 10mbit ceil 10mbit

\# Redirect ingress from each gateway veth to ifb0

for iface in veth-radio-gw1 veth-radio-gw2 veth-radio-gw3; do

  tc qdisc add dev $iface ingress

  tc filter add dev $iface parent ffff: protocol ip \\

    u32 match u32 0 0 \\

    action mirred egress redirect dev ifb0

done

The IFB (Intermediate Functional Block) device is needed because tc can only shape *egress* traffic. Since forwarded packets arrive on one veth and leave on another, we redirect all ingress through ifb0 where the aggregate htb rate limit is applied. This ensures total throughput across all drones is capped at the radio’s hardware limit.

## **3.4 Setup Script**

A host-side bash script that runs after all Docker Compose stacks are up. It creates veth pairs between each drone’s gateway and the radio hub, configures addresses, injects routes into all service containers, and applies initial tc netem shaping.

\#\!/bin/bash

set \-e

RADIO\_PID=$(docker inspect \-f '{{.State.Pid}}' radio-hub)

\# Define drones: name, gateway container, internal bridge subnet,

\#                  gateway internal IP

DRONES=(

  "drone1 drone1-gateway 10.1.0.0/16 10.1.0.100"

  "drone2 drone2-gateway 10.2.0.0/16 10.2.0.100"

  "drone3 drone3-gateway 10.3.0.0/16 10.3.0.100"

)

for i in "${\!DRONES\[@\]}"; do

  read \-r NAME GW\_CONTAINER INTERNAL\_SUBNET GW\_INTERNAL\_IP \\

      \<\<\< "${DRONES\[$i\]}"

  N=$((i \+ 1))

  GW\_PID=$(docker inspect \-f '{{.State.Pid}}' $GW\_CONTAINER)

  \# \--- Create veth pair \---

  ip link add veth-gw${N}-radio type veth \\

      peer name veth-radio-gw${N}

  \# Move endpoints into containers

  ip link set veth-gw${N}-radio netns $GW\_PID

  ip link set veth-radio-gw${N} netns $RADIO\_PID

  \# \--- Configure gateway side \---

  nsenter \-t $GW\_PID \-n bash \-c "

    ip addr add 10.100.${N}.1/30 dev veth-gw${N}-radio

    ip link set veth-gw${N}-radio up

    sysctl \-w net.ipv4.ip\_forward=1

    \# NAT outbound on veth

    iptables \-t nat \-A POSTROUTING \\

        \-o veth-gw${N}-radio \-j MASQUERADE

    iptables \-A FORWARD \-i eth0 \\

        \-o veth-gw${N}-radio \-j ACCEPT

    iptables \-A FORWARD \-i veth-gw${N}-radio \-o eth0 \\

        \-m state \--state RELATED,ESTABLISHED \-j ACCEPT

  "

  \# \--- Configure radio hub side \---

  nsenter \-t $RADIO\_PID \-n bash \-c "

    ip addr add 10.100.${N}.2/30 dev veth-radio-gw${N}

    ip link set veth-radio-gw${N} up

  "

  \# \--- Add routes on radio hub to reach internal subnets \---

  \# (Radio needs to know: to reach drone1's internal net,

  \#  send via gateway1's veth address)

  nsenter \-t $RADIO\_PID \-n ip route add \\

      $INTERNAL\_SUBNET via 10.100.${N}.1

  \# \--- Routes on gateway to reach other drones via radio \---

  for j in "${\!DRONES\[@\]}"; do

    if \[ $j \-ne $i \]; then

      M=$((j \+ 1))

      read \-r \_ \_ OTHER\_SUBNET \_ \<\<\< "${DRONES\[$j\]}"

      nsenter \-t $GW\_PID \-n ip route add \\

          10.100.${M}.0/30 via 10.100.${N}.2

    fi

  done

  \# \--- Apply initial tc netem on both veth ends \---

  nsenter \-t $GW\_PID \-n tc qdisc add \\

      dev veth-gw${N}-radio root netem rate 1mbit

  nsenter \-t $RADIO\_PID \-n tc qdisc add \\

      dev veth-radio-gw${N} root netem rate 1mbit

done

\# \--- Inject routes into ALL service containers per drone \---

for i in "${\!DRONES\[@\]}"; do

  read \-r NAME GW\_CONTAINER \_ GW\_INTERNAL\_IP \\

      \<\<\< "${DRONES\[$i\]}"

  \# Get all containers on this drone's compose project

  CONTAINERS=$(docker ps \--filter \\

      "label=com.docker.compose.project=${NAME}" \\

      \--format '{{.Names}}')

  for CONT in $CONTAINERS; do

    if \[ "$CONT" \!= "$GW\_CONTAINER" \]; then

      CPID=$(docker inspect \-f '{{.State.Pid}}' $CONT)

      nsenter \-t $CPID \-n ip route add \\

          10.100.0.0/16 via $GW\_INTERNAL\_IP 2\>/dev/null \\

          || true

    fi

  done

done

\# \--- Configure radio hub aggregate bandwidth cap \---

nsenter \-t $RADIO\_PID \-n bash \-c "

  ip link add ifb0 type ifb

  ip link set ifb0 up

  tc qdisc add dev ifb0 root handle 1: htb default 10

  tc class add dev ifb0 parent 1: classid 1:10 \\

      htb rate 10mbit ceil 10mbit

"

for i in "${\!DRONES\[@\]}"; do

  N=$((i \+ 1))

  nsenter \-t $RADIO\_PID \-n bash \-c "

    tc qdisc add dev veth-radio-gw${N} ingress

    tc filter add dev veth-radio-gw${N} parent ffff: \\

        protocol ip u32 match u32 0 0 \\

        action mirred egress redirect dev ifb0

  "

done

echo 'Network setup complete'

## **3.5 Addressing Scheme**

Two address spaces are used: each drone’s internal Docker bridge subnet (unchanged from current setup) and the simulation /30 subnets on the veth links.

| Network | Subnet | Purpose |
| :---- | :---- | :---- |
| drone1 internal bridge | 10.1.0.0/16 | Internal comms between drone1’s \~20 services (unchanged) |
| drone2 internal bridge | 10.2.0.0/16 | Internal comms between drone2’s \~20 services (unchanged) |
| drone3 internal bridge | 10.3.0.0/16 | Internal comms between drone3’s \~20 services (unchanged) |
| drone1 gw ↔ radio hub | 10.100.1.0/30 | Simulation spoke (gateway=.1, radio=.2) |
| drone2 gw ↔ radio hub | 10.100.2.0/30 | Simulation spoke (gateway=.1, radio=.2) |
| drone3 gw ↔ radio hub | 10.100.3.0/30 | Simulation spoke (gateway=.1, radio=.2) |

The 10.100.0.0/16 range is reserved for simulation links. When any service container adds the route 10.100.0.0/16 via its gateway, only inter-drone traffic matches. All internal traffic to 10.X.0.0/16 is handled by the more-specific Docker bridge route and never reaches the gateway.

## **3.6 Controller API**

A lightweight FastAPI service exposing REST endpoints for runtime network control. It runs in a privileged container with host PID namespace access.

| Endpoint | Method | Parameters | Action |
| :---- | :---- | :---- | :---- |
| POST /drones/{id}/link | POST | delay\_ms, loss\_pct, rate\_kbit | Update tc netem on both ends of drone’s spoke veth |
| POST /drones/{id}/down | POST | — | Set 100% loss (simulates drone out of range) |
| POST /drones/{id}/up | POST | — | Restore spoke to previous parameters |
| POST /radio/bandwidth | POST | rate\_kbit | Update the radio hub’s aggregate htb bandwidth cap |
| GET /status | GET | — | Current tc parameters for all spokes and radio |

The link update executes tc qdisc change on both veth endpoints:

nsenter \-t $GW\_PID \-n tc qdisc change \\

    dev veth-gwN-radio root netem \\

    delay ${delay\_ms}ms loss ${loss\_pct}% rate ${rate\_kbit}kbit

nsenter \-t $RADIO\_PID \-n tc qdisc change \\

    dev veth-radio-gwN root netem \\

    delay ${delay\_ms}ms loss ${loss\_pct}% rate ${rate\_kbit}kbit

For distance-based simulation, a separate process computes pairwise distances from drone positions and calls the API. A simple linear model: loss\_pct \= max(0, (distance − min\_range) / (max\_range − min\_range) × 100), clamped to 0–100.

# **4\. Docker Compose Configuration**

Each drone’s existing docker-compose.yml gets one new service: the gateway. The radio hub and controller are defined in a separate compose file. All compose projects share a common external management network for the controller API.

## **4.1 Per-Drone Compose (e.g., drone1/docker-compose.yml)**

Add the gateway service. All existing services remain unchanged.

services:

  \# ... existing \~20 services unchanged ...

  database:

    image: drone-db:latest

    networks:

      \- drone1\_internal

  control:

    image: drone-control:latest

    networks:

      \- drone1\_internal

  \# NEW: gateway for inter-drone routing

  gateway:

    image: alpine:latest

    container\_name: drone1-gateway

    cap\_add:

      \- NET\_ADMIN

    command: \>

      sh \-c 'apk add \--no-cache iproute2 iptables &&

             sysctl \-w net.ipv4.ip\_forward=1 &&

             sleep infinity'

    networks:

      drone1\_internal:

        ipv4\_address: 10.1.0.100

networks:

  drone1\_internal:

    driver: bridge

    ipam:

      config:

        \- subnet: 10.1.0.0/16

## **4.2 Infrastructure Compose (infra/docker-compose.yml)**

services:

  radio-hub:

    image: alpine:latest

    container\_name: radio-hub

    cap\_add:

      \- NET\_ADMIN

    command: \>

      sh \-c 'apk add \--no-cache iproute2 iptables &&

             sysctl \-w net.ipv4.ip\_forward=1 &&

             sleep infinity'

  controller:

    image: sim-controller:latest

    container\_name: sim-controller

    volumes:

      \- /var/run/docker.sock:/var/run/docker.sock

    ports:

      \- '8080:8080'

    privileged: true

    pid: host

# **5\. Traffic Flow: Internal vs External**

This section clarifies exactly which traffic is shaped and which is not.

| Scenario | Path | Shaped? |
| :---- | :---- | :---- |
| drone1 database → drone1 control | Internal bridge only | No — stays on Docker bridge |
| drone1 database → drone2 control | Bridge → gw1 → veth → radio → veth → gw2 → bridge | Yes — both spoke netem \+ radio htb |
| drone1 service → drone1 gateway | Internal bridge only | No — stays on Docker bridge |
| drone1 gateway → radio hub | veth pair | Yes — tc netem on both ends |

The routing decision happens at the IP layer inside each service container. Traffic to addresses in the container’s own bridge subnet (e.g., 10.1.0.0/16) is delivered directly on the bridge. Traffic to the simulation range (10.100.0.0/16) matches the injected route and is sent to the gateway. There is no risk of internal traffic being accidentally shaped.

# **6\. Host Safety and Cleanup**

All network resources created by this system are ephemeral kernel objects. Nothing is written to persistent host configuration.

| Resource | Lifetime | Cleanup |
| :---- | :---- | :---- |
| veth pairs | Destroyed when either container is removed | Automatic |
| tc qdisc/filter rules | Live in kernel memory; removed with interface or netns | Automatic |
| IFB devices (inside radio hub) | Created inside container netns; removed with container | Automatic |
| IP routes (inside containers) | Removed with container | Automatic |
| ip\_forward sysctl | Set inside container netns; does not affect host | Automatic |
| iptables NAT/FORWARD rules | Inside gateway container netns; does not affect host | Automatic |

**Full cleanup:** docker compose down on all stacks removes all containers and their namespaces, destroying all veth pairs, tc rules, iptables rules, and routes. A host reboot also clears everything. The setup script never modifies the host’s own routing table, iptables, or persistent network config.

**Partial cleanup:** To reset the simulation without restarting containers, run the teardown script (deletes veth pairs from inside each gateway’s and radio hub’s netns) then re-run the setup script.

# **7\. Verification and Testing**

## **7.1 Test 1: Internal Traffic Unaffected**

Verify that communication between a drone’s own services has no added latency or loss, even with aggressive shaping on the spoke.

1. Start all stacks and run the setup script

2. Apply heavy shaping to drone1’s spoke (200ms delay, 50% loss):

curl \-X POST http://localhost:8080/drones/1/link \\

  \-d '{"delay\_ms": 200, "loss\_pct": 50, "rate\_kbit": 100}'

3. Ping drone1’s database from drone1’s control service (internal traffic):

docker exec drone1-control ping \-c 20 10.1.0.5

4. Expected: \~0.1ms RTT, 0% loss. The spoke shaping has zero effect on internal traffic.

## **7.2 Test 2: Inter-Drone Connectivity via Radio Hub**

Verify that traffic between drones routes through the gateway and radio hub.

1. Remove all shaping (set 0ms delay, 0% loss, high rate)

2. From any container in drone1, ping a container in drone2:

docker exec drone1-control ping \-c 5 10.100.2.1

3. Run traceroute to verify the path:

docker exec drone1-control traceroute \-n 10.100.2.1

4. Expected: traceroute shows hops through drone1-gateway (10.1.0.100) then radio hub (10.100.1.2) then drone2-gateway (10.100.2.1). Ping shows 0% loss.

## **7.3 Test 3: Per-Spoke Latency and Loss**

Verify that shaping on one drone’s spoke does not affect other drones.

1. Apply 50ms delay, 20% loss to drone1’s spoke; leave drone2 and drone3 at 0ms/0%

2. From drone1, ping drone2 (100 pings):

docker exec drone1-control ping \-c 100 10.100.2.1

3. From drone2, ping drone3 (100 pings):

docker exec drone2-control ping \-c 100 10.100.3.1

4. Expected: drone1→drone2 shows \~100ms RTT and \~20% loss. drone2→drone3 shows \~0ms RTT and \~0% loss.

## **7.4 Test 4: Spoke Bandwidth Limiting**

Verify per-drone bandwidth constraints using iperf3.

1. Set drone1 spoke to 500kbit, drone2 spoke to 2mbit

2. Run iperf3 from drone1 to drone2:

docker exec drone2-gateway iperf3 \-s \-D

docker exec drone1-control iperf3 \-c 10.100.2.1 \-t 10

3. Expected: throughput capped at \~500 kbps (bottleneck is drone1’s spoke)

## **7.5 Test 5: Radio Hub Aggregate Cap**

Verify that the radio hub’s aggregate bandwidth limit constrains total throughput across all drones.

1. Set all spokes to 10mbit (uncapped at spoke level)

2. Set radio hub aggregate cap to 2mbit:

curl \-X POST http://localhost:8080/radio/bandwidth \\

  \-d '{"rate\_kbit": 2000}'

3. Run two simultaneous iperf3 flows through the radio hub:

docker exec drone2-gateway iperf3 \-s \-D

docker exec drone1-control iperf3 \-c 10.100.2.1 \-t 10 &

docker exec drone3-control iperf3 \-c 10.100.2.1 \-t 10 \-p 5202 &

wait

4. Expected: combined throughput \~2 Mbps total. Each flow gets roughly 1 Mbps.

## **7.6 Test 6: Dynamic Distance Simulation**

Verify real-time API updates to link quality.

1. Start continuous ping from drone1 to drone2

2. Progressively increase loss:

for loss in 0 10 25 50 75 100; do

  curl \-s \-X POST http://localhost:8080/drones/1/link \\

    \-d "{\\"delay\_ms\\": 10, \\"loss\_pct\\": $loss, \\"rate\_kbit\\": 1000}"

  sleep 5

done

3. Expected: ping output shows loss increasing in steps. At 100% loss, no replies (drone out of range).

## **7.7 Test 7: Any Container Can Reach Other Drones**

Verify that the route injection works for all service containers, not just the gateway.

1. Pick several different service containers from drone1 (database, telemetry, control, etc.)

2. From each, ping drone2’s gateway:

docker exec drone1-database ping \-c 3 10.100.2.1

docker exec drone1-telemetry ping \-c 3 10.100.2.1

docker exec drone1-control ping \-c 3 10.100.2.1

3. Expected: all succeed, confirming the 10.100.0.0/16 route is present in every service container.

## **7.8 Test 8: Full Cleanup**

Verify no residual host network configuration after teardown.

1. Record host state: ip link show; ip route show; iptables \-L \-n

2. Tear down all stacks: docker compose down on each drone \+ infra

3. Record host state again and diff

4. Expected: identical output. No veth pairs, routes, or iptables rules from the simulation remain on the host.

# **8\. File Structure**

drone-sim/

├── infra/

│   └── docker-compose.yml    \# radio-hub \+ controller

├── drone1/

│   └── docker-compose.yml    \# \~20 services \+ gateway

├── drone2/

│   └── docker-compose.yml

├── drone3/

│   └── docker-compose.yml

├── setup\_network.sh

├── teardown\_network.sh

├── controller/

│   ├── Dockerfile

│   ├── app.py                \# FastAPI controller

│   └── netem.py              \# tc command wrappers

└── tests/

    ├── test\_internal\_unaffected.sh

    ├── test\_connectivity.sh

    ├── test\_bandwidth.sh

    └── test\_cleanup.sh

# **9\. Known Limitations and Considerations**

* **Route injection into \~20 containers:** The setup script must enumerate all containers per drone and nsenter into each to add the route. If a service container restarts, it loses the route. Consider a sidecar or init container pattern, or add the route to each service’s entrypoint for resilience.

* **NET\_ADMIN on service containers:** If using the entrypoint approach for route injection (Option A), each service container needs NET\_ADMIN capability. If using the nsenter approach (Option B), only the setup script (running on the host) needs privileges — service containers can remain unprivileged.

* **NAT on the gateway:** Gateway MASQUERADE means the destination drone sees traffic as coming from the gateway’s veth IP, not the original service IP. This is fine for most applications but means per-source-service visibility is lost at the receiving end. If this matters, replace MASQUERADE with proper routing (add return routes for each drone’s internal subnet through the radio hub).

* **Container restart recovery:** If the radio hub or a gateway restarts, its veth pairs and tc rules are lost. The controller should detect this (e.g., periodic health checks) and re-run setup for the affected components.

* **tc netem precision:** netem loss and delay are statistical. Use test runs of 100+ packets for meaningful validation. Short runs will show high variance.

* **IFB kernel module:** The ifb module must be available on the host. Verify with: modprobe ifb. Most Linux distributions include it by default.

* **Asymmetric links:** tc netem is applied independently on each veth end. Different parameters on the gateway-side and radio-side endpoints model asymmetric uplink/downlink characteristics.