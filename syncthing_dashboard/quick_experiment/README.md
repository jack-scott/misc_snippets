# Syncthing Fleet Dashboard

Browser-based dashboard for managing a fleet of drones running Syncthing. No backend — all state lives in `localStorage`, all data is fetched live from each drone's Syncthing REST API.

## Setup

### 1. Configure CORS on each drone

Syncthing must accept cross-origin requests. Edit `config.xml` on each drone:

```xml
<gui>
  <address>0.0.0.0:8384</address>
  <insecureSkipHostcheck>true</insecureSkipHostcheck>
</gui>
```

Or patch it via API while the drone is reachable:

```bash
curl -X PATCH http://{drone-ip}:8384/rest/config/gui \
  -H "X-API-Key: {key}" \
  -H "Content-Type: application/json" \
  -d '{"insecureSkipHostcheck": true}'
```

### 2. Serve the dashboard

The dashboard must be served over HTTP (not opened as `file://`) so that `fetch` works.

```bash
cd syncthing_control
pixi run serve
```

Then open `http://localhost:8080/dashboard.html` in your browser.

### 3. Add drones

Click **Settings**, fill in the label, host (`192.168.1.x:8384`), and API key for each drone, then hit **Test connection** before saving.

The API key is visible in each drone's Syncthing web UI under **Actions → Settings → API Key**.

## Usage

- **Fleet overview** — cards for every configured drone, polling every 30s
- **Drone detail** — per-folder sync state, peers, and filesystem browser; polls every 8s
- **Browse & add** — navigate the drone filesystem and add directories as send-only Syncthing folders
