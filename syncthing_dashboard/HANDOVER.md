# Fleet Sync — Claude Code Handover

## What This Is

A web dashboard for managing Syncthing-based log synchronisation across a drone fleet. The central server operator selects which date-organised log folders to pull from each drone, and the dashboard manages the plumbing — SSH tunnels, Syncthing ignore patterns, and per-drone API access — without exposing anything insecurely.

The UI is an engineering tool, not a product. Assume the operator knows what they're doing. Instructions can be terse.

---

## System Architecture

```
[Browser]
    |
    | (served over Tailscale or local network)
    v
[Central / Field Server]
  - Flask (or similar) backend
  - Serves the React dashboard
  - Proxies Syncthing REST API calls (never exposed directly)
  - Manages SSH tunnel subprocesses
    |
    | localhost:8384
    v
[Syncthing daemon on server]
    |
    | Syncthing sync (port 22000, any network, encrypted)
    |
    +——— direct (office LAN) ———> [Drone Syncthing]
    +——— relay (field/remote) ——> [relay server] ——> [Drone Syncthing]
    +——— Tailscale WireGuard ——> [Field Server Syncthing]
                                        |
                                        | same local switch
                                        v
                                 [Drone Syncthing]
```

**Key principle:** The Syncthing API (port 8384) is never exposed to any network. It only listens on localhost on every device. All API access goes through either:
- The backend proxy (for local/server Syncthing)
- An SSH tunnel (for drone Syncthing when on the same LAN)
- A proxied SSH tunnel via a field server (for drones reachable through a field server)

---

## Drone Connectivity Tiers

The dashboard detects which tier a drone is in and adjusts available actions accordingly.

| Status | How detected | API access | Browse folders | Notes |
|---|---|---|---|---|
| `local` | Syncthing connected + IP in configured subnet | Via SSH tunnel | Yes, after CONNECT | Tunnel opened on demand |
| `relay` | Syncthing connected via relay:// address | None | No | Status/progress only |
| `wan` | Syncthing connected, IP not in local subnet | None | No | Status/progress only |
| `offline` | Not connected | None | Last known state | |

### Local subnet detection
The server checks the IP address that Syncthing actually connected to a device on, retrieved from `GET /rest/system/connections`. This IP is compared against a configured subnet (e.g. `192.168.1.0/24`) set in dashboard settings.

**Important:** We deliberately do NOT auto-detect the server's own subnet. It must be manually configured in settings. Reason: auto-detection (e.g. via netifaces) can't distinguish "our office network" from "some other office network the drone happened to end up on." The configured subnet is the operator's explicit assertion of trust.

### Why not just use Tailscale on drones?
Drones may have constrained OS environments and may not support Tailscale. Field servers do have Tailscale, so they act as the trust boundary for drones without it.

---

## SSH Tunnel Design

When a drone is detected as `local`, a CONNECT button appears. Clicking it triggers the backend to open an SSH tunnel:

```bash
ssh -N -i <keysDir>/<drone-name>/id_ed25519 \
    -L <local_port>:127.0.0.1:8384 \
    <sshUser>@<drone_ip>
```

The drone IP comes from parsing the Syncthing connections response — Syncthing already found it, we just harvest the address it used. No pre-configured IP list needed.

**Per-drone SSH keys:** Each drone gets its own keypair generated at provisioning time, stored at `<sshKeysDir>/<drone-name>/id_ed25519`. Rationale: shared fleet keys mean a single compromised drone exposes all of them. Scoped keys limit blast radius.

**Tunnel port allocation:** Sequential from a pool (e.g. 9384, 9385, ...) managed by the backend. The backend tracks active tunnels as a dict of `{ device_id: { process, local_port, drone_ip } }`.

**Tunnel lifecycle:** Tunnels are opened on demand (CONNECT button) and closed explicitly (DISCONNECT button) or when the backend shuts down. They are NOT auto-opened on page load — intentional, operator should consciously initiate.

---

## Per-Drone API Keys

Syncthing API keys are NOT shared across the fleet. Each drone has its own key set in its `config.xml`. The provisioning flow retrieves it via SSH:

```bash
ssh -i <keyPath> <user>@<drone_ip> \
  "grep -oP '(?<=<apikey>)[^<]+' ~/.config/syncthing/config.xml"
```

The key is stored in the dashboard's persistent storage against the drone's device ID and used for all subsequent API calls to that drone (via its SSH tunnel).

---

## Date Folder Sync Selection

The drone's `organised` folder is structured as:
```
organised/
  2025-06-10/   ← one folder per flight date
  2025-06-08/
  2025-05-30/
  ...
```

This organisation happens on-device before sync. The dashboard does NOT trigger or manage organisation — it only manages what gets synced.

**Mechanism:** Syncthing's ignore patterns (`.stignore` / `ignorePatterns` in folder config). Default is ignore everything, then selectively un-ignore chosen dates:

```
!/2025-06-10
!/2025-06-08
*
```

Applied via `PATCH /rest/config/folders/organised` with updated `ignorePatterns`. No restart required — Syncthing picks up ignore changes live.

**Browse API:** When a tunnel is open to a drone, the dashboard calls `GET /rest/db/browse?folder=organised&levels=1` on the drone's Syncthing (via tunnel) to get actual folder sizes and file counts before committing to a sync. This is only available when tunnelled — relay/offline drones show `—` for size.

---

## Persistent Storage

Dashboard config and drone history persist across reloads using `window.storage` (artifact storage API, key-value).

Two keys:
- `fleet-sync-config` — operator settings (subnet, SSH user, keys dir, local Syncthing API key, field servers)
- `fleet-sync-drones` — per-drone history (name, device ID, per-drone API key, SSH key path, selected dates)

**What persists per drone:**
```json
{
  "DEVICE-ID-XXX": {
    "id": "DEVICE-ID-XXX",
    "name": "Drone Alpha-1",
    "apiKey": "drone-specific-api-key",
    "keyPath": "/etc/fleet/keys/drone-alpha-1/id_ed25519",
    "sshUser": "drone",
    "selectedDates": ["2025-06-10", "2025-06-08"],
    "addedAt": 1234567890
  }
}
```

When building a real backend, this storage should migrate to a server-side database or config file. The frontend storage is a stand-in for the prototype phase.

---

## Field Servers

Field servers are Raspberry Pi / mini-PC class machines deployed with drone teams. They have Tailscale, so the central server can reach them at their Tailscale IP (100.x.x.x).

Field servers run their own Syncthing daemon and may have drones connected locally (same switch). The central server can:
1. Hit the field server's Syncthing API directly via Tailscale: `http://100.x.x.x:8384`
2. Use the field server as a jump host to SSH-tunnel into a drone connected to that field server

Field servers are registered in settings with name + Tailscale IP + their own Syncthing API key.

**Future work:** The dashboard currently only handles drones reachable by the central server directly. Routing API calls through a field server as a jump host (for drones connected to a remote field server) is designed but not yet implemented. The connection tier data model supports it — `wan` status on the central server may mean `local` on a field server.

---

## Provisioning Flow (New Drone)

The "+ NEW DRONE" modal walks through provisioning with live-parameterised commands. Steps unlock sequentially as verification passes. Values captured in one step (pub key, API key, device IDs) are injected into commands in later steps.

Steps:
1. Generate SSH keypair for this drone (`<keysDir>/<drone-name>/id_ed25519`)
2. Install public key on drone — `ssh-copy-id` or manual append
3. Retrieve drone's Syncthing API key via SSH grep on config.xml *(verify button: tries SSH, auto-fills key)*
4. Open test tunnel, retrieve drone's Syncthing device ID *(verify button: opens tunnel to port 19384, hits /rest/system/status)*
5. Retrieve field server's own device ID from local Syncthing
6. Pair devices — add each to the other's Syncthing config via API
7. Share `organised` folder — PATCH folder config on server, POST new folder on drone via tunnel

On completion, "REGISTER DRONE" button stores the drone in persistent history and triggers a device list refresh.

**Verify buttons** hit backend endpoints (not yet implemented) that perform the actual check:
- `POST /api/provision/verify/ssh` — tries `ssh -i <key> <user>@<ip> echo ok`
- `POST /api/provision/verify/apikey` — SSHes, greps config.xml, returns key
- `POST /api/provision/verify/deviceid` — opens tunnel, hits /rest/system/status, returns myID
- `POST /api/provision/verify/folder` — checks /rest/config/devices on both ends

---

## Backend (Not Yet Built)

The Flask (or FastAPI) backend needs these responsibilities:

### Syncthing proxy
Route API calls to the right Syncthing instance:
- Local server: `http://127.0.0.1:8384`
- Field server: `http://<tailscale_ip>:8384`
- Drone (tunnelled): `http://127.0.0.1:<tunnel_port>`

### Tunnel management
```
POST /api/tunnel/open   { device_id, drone_ip, key_path, ssh_user }  → opens SSH tunnel, returns local_port
POST /api/tunnel/close  { device_id }                                 → kills SSH process
GET  /api/tunnel/status                                               → dict of active tunnels
```

### Provisioning verify endpoints
```
POST /api/provision/verify/ssh       { ip, key_path, ssh_user }
POST /api/provision/verify/apikey    { ip, key_path, ssh_user }       → returns api_key
POST /api/provision/verify/deviceid  { ip, key_path, ssh_user, api_key } → returns device_id
POST /api/provision/verify/folder    { device_id, api_key, tunnel_port }
```

### Device list
```
GET /api/devices   → merges Syncthing connections + stored drone history, returns enriched device list
```

---

## What's In The JSX (Current State)

- `MOCK_MODE = true` at the top — all data is hardcoded mock data. Flip to false and wire up real fetch calls.
- All API calls have comments showing the real endpoint they'd hit
- `tunnelState` is an in-memory JS object (resets on reload) — in production this is managed by the backend
- `window.storage` calls are real and functional for config/history persistence
- The provisioning verify buttons mock a delay and return hardcoded results

---

## Key Decisions Summary

| Decision | Rationale |
|---|---|
| Syncthing API bound to localhost only | Never expose management API to any network |
| SSH tunnel for drone API access | Drone doesn't need Tailscale; tunnel uses existing SSH provisioning |
| Subnet configured manually, not auto-detected | Can't distinguish "our" LAN from "a" LAN by IP range alone |
| Per-drone SSH keypairs | Limit blast radius of a compromised drone |
| Per-drone Syncthing API keys | Same reasoning; keys are retrieved at provisioning not pre-shared |
| IP harvested from Syncthing connections | Syncthing already did NAT traversal discovery; no need to pre-configure drone IPs |
| Ignore patterns for date selection | Native Syncthing feature, no restart, live update, simple to reason about |
| Field server as trust boundary | Drones without Tailscale get API access proxied through field server which does have Tailscale |
| Tunnels opened on demand, not auto | Operator should consciously decide when to open API access to a drone |
