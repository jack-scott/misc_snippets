"""MANET Chaos Simulator UI - Network visualization and chaos control."""

import json
import os
import time
from pathlib import Path

import requests
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)
DRONE_COUNT = int(os.environ.get("DRONE_COUNT", 3))
METRICS_DIR = Path("/metrics")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>MANET Chaos Simulator</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        h1 { margin-bottom: 5px; color: #00d9ff; }
        .subtitle { color: #666; margin-bottom: 20px; font-size: 14px; }
        .container { max-width: 1400px; margin: 0 auto; }

        .main-layout {
            display: grid;
            grid-template-columns: 1fr 380px;
            gap: 20px;
        }

        /* Topology panel */
        .topology {
            background: #16213e;
            border-radius: 12px;
            padding: 20px;
            min-height: 500px;
        }
        .topology h2 { font-size: 13px; color: #666; margin-bottom: 15px; text-transform: uppercase; }
        .topology svg { width: 100%; height: 450px; }

        /* Drone nodes */
        .drone circle {
            fill: #0f3460;
            stroke: #00d9ff;
            stroke-width: 2;
            cursor: pointer;
            transition: all 0.2s;
        }
        .drone:hover circle { fill: #1a4a7a; stroke-width: 3; }
        .drone text {
            fill: #fff;
            font-size: 16px;
            font-weight: 600;
            text-anchor: middle;
            dominant-baseline: middle;
            pointer-events: none;
        }
        .drone-label {
            fill: #888;
            font-size: 11px;
            text-anchor: middle;
        }

        /* Link lines */
        .link { cursor: pointer; transition: all 0.2s; }
        .link:hover { stroke-width: 6 !important; }
        .link.good { stroke: #00ff88; }
        .link.degraded { stroke: #ffaa00; }
        .link.bad { stroke: #ff4444; }
        .link.down { stroke: #444; stroke-dasharray: 5,5; }

        /* Link metrics labels */
        .link-metrics {
            font-size: 10px;
            fill: #aaa;
            pointer-events: none;
        }
        .link-metrics.bad { fill: #ff6666; }

        /* Status indicators */
        .status-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 5px;
        }
        .status-dot.good { background: #00ff88; }
        .status-dot.bad { background: #ff4444; }

        /* Side panel */
        .side-panel {
            display: flex;
            flex-direction: column;
            gap: 15px;
        }

        .panel {
            background: #16213e;
            border-radius: 12px;
            padding: 15px;
        }
        .panel h2 {
            font-size: 13px;
            color: #666;
            margin-bottom: 12px;
            text-transform: uppercase;
        }

        /* Link list */
        .link-item {
            background: #0f3460;
            border-radius: 8px;
            padding: 10px 12px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 13px;
        }
        .link-item:hover { background: #1a4a7a; }
        .link-item.selected { border: 2px solid #00d9ff; }

        .link-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }
        .link-name { font-weight: 600; }

        .link-stats {
            display: flex;
            gap: 12px;
            font-size: 11px;
            color: #888;
        }
        .link-stats .metric { display: flex; align-items: center; gap: 4px; }
        .link-stats .value { color: #fff; }
        .link-stats .value.bad { color: #ff6666; }

        /* Chaos badge */
        .chaos-badge {
            background: #ff444433;
            color: #ff8888;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
        }

        /* Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.85);
            justify-content: center;
            align-items: center;
            z-index: 100;
        }
        .modal.active { display: flex; }
        .modal-content {
            background: #16213e;
            border-radius: 12px;
            padding: 24px;
            min-width: 420px;
        }
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        .modal-close {
            background: none;
            border: none;
            color: #666;
            font-size: 24px;
            cursor: pointer;
        }
        .modal-close:hover { color: #fff; }

        /* Form */
        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-bottom: 12px;
        }
        .form-group { margin-bottom: 12px; }
        .form-group label {
            display: block;
            margin-bottom: 6px;
            color: #888;
            font-size: 12px;
        }
        .form-group input {
            width: 100%;
            padding: 10px;
            background: #0f3460;
            border: 1px solid #2a4a6a;
            border-radius: 6px;
            color: #fff;
            font-size: 14px;
        }
        .form-group input:focus {
            outline: none;
            border-color: #00d9ff;
        }

        /* Presets */
        .presets {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 16px;
        }
        .preset {
            padding: 8px 14px;
            background: #0f3460;
            border: 1px solid #2a4a6a;
            border-radius: 6px;
            color: #aaa;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .preset:hover { background: #1a4a7a; color: #fff; border-color: #00d9ff; }

        /* Buttons */
        .btn-group { display: flex; gap: 10px; margin-top: 20px; }
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
        }
        .btn-primary { background: #00d9ff; color: #000; font-weight: 600; }
        .btn-primary:hover { background: #00b8d9; }
        .btn-danger { background: #ff4444; color: #fff; }
        .btn-danger:hover { background: #cc3333; }
        .btn-secondary { background: #333; color: #fff; }
        .btn-secondary:hover { background: #444; }

        /* Legend */
        .legend {
            display: flex;
            gap: 20px;
            margin-top: 15px;
            font-size: 12px;
            color: #666;
        }
        .legend-item { display: flex; align-items: center; gap: 6px; }
        .legend-line {
            width: 20px;
            height: 3px;
            border-radius: 2px;
        }
        .legend-line.good { background: #00ff88; }
        .legend-line.degraded { background: #ffaa00; }
        .legend-line.bad { background: #ff4444; }
        .legend-line.down { background: #444; }
    </style>
</head>
<body>
    <div class="container">
        <h1>MANET Chaos Simulator</h1>
        <p class="subtitle">Click on links to inject network chaos (latency, packet loss, bandwidth limits)</p>

        <div class="main-layout">
            <div class="topology">
                <h2>Network Topology</h2>
                <svg id="topology-svg"></svg>
                <div class="legend">
                    <div class="legend-item"><div class="legend-line good"></div> Good (&lt;50ms)</div>
                    <div class="legend-item"><div class="legend-line degraded"></div> Degraded (50-200ms)</div>
                    <div class="legend-item"><div class="legend-line bad"></div> Bad (&gt;200ms)</div>
                    <div class="legend-item"><div class="legend-line down"></div> Down</div>
                </div>
            </div>

            <div class="side-panel">
                <div class="panel">
                    <h2>Links</h2>
                    <div id="links-list"></div>
                </div>
            </div>
        </div>
    </div>

    <!-- Chaos Modal -->
    <div class="modal" id="chaos-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 id="modal-title">Configure Link</h2>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>

            <div class="presets">
                <button class="preset" onclick="applyPreset('clear')">Clear</button>
                <button class="preset" onclick="applyPreset('good')">Good Link</button>
                <button class="preset" onclick="applyPreset('degraded')">Degraded</button>
                <button class="preset" onclick="applyPreset('bad')">Bad Link</button>
                <button class="preset" onclick="applyPreset('lossy')">Lossy (30%)</button>
                <button class="preset" onclick="applyPreset('partition')">Partition</button>
            </div>

            <div class="form-row">
                <div class="form-group">
                    <label>Latency (ms)</label>
                    <input type="number" id="latency-input" value="0" min="0">
                </div>
                <div class="form-group">
                    <label>Jitter (ms)</label>
                    <input type="number" id="jitter-input" value="0" min="0">
                </div>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Packet Loss (%)</label>
                    <input type="number" id="loss-input" value="0" min="0" max="100">
                </div>
                <div class="form-group">
                    <label>Bandwidth (kbit/s, 0=unlimited)</label>
                    <input type="number" id="rate-input" value="0" min="0">
                </div>
            </div>

            <div class="btn-group">
                <button class="btn btn-primary" onclick="applyChaos()">Apply</button>
                <button class="btn btn-danger" onclick="clearChaos()">Clear Chaos</button>
                <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
            </div>
        </div>
    </div>

    <script>
        const DRONE_COUNT = {{ drone_count }};
        let links = [];
        let selectedLink = null;

        // Calculate drone positions in a circle
        function getDronePositions() {
            const positions = {};
            const centerX = 300, centerY = 225;
            const radius = 150;

            for (let i = 1; i <= DRONE_COUNT; i++) {
                const angle = (2 * Math.PI * (i - 1) / DRONE_COUNT) - Math.PI / 2;
                positions[i] = {
                    x: centerX + radius * Math.cos(angle),
                    y: centerY + radius * Math.sin(angle)
                };
            }
            return positions;
        }

        const dronePositions = getDronePositions();

        async function fetchLinks() {
            try {
                const resp = await fetch('/api/links');
                links = await resp.json();
                render();
            } catch (e) {
                console.error('Failed to fetch links:', e);
            }
        }

        function getLinkStatus(link) {
            if (link.ping_ms < 0) return 'down';
            if (link.ping_ms > 200) return 'bad';
            if (link.ping_ms > 50) return 'degraded';
            return 'good';
        }

        function hasActiveChaos(link) {
            const c = link.chaos || {};
            return c.latency_ms > 0 || c.loss_percent > 0 || c.rate_kbit > 0;
        }

        function render() {
            renderTopology();
            renderLinksList();
        }

        function renderTopology() {
            const svg = document.getElementById('topology-svg');
            let html = '';

            // Draw links
            const drawnLinks = new Set();
            for (const link of links) {
                const key = [link.source, link.target].sort().join('-');
                if (drawnLinks.has(key)) continue;

                const from = dronePositions[link.source];
                const to = dronePositions[link.target];
                if (!from || !to) continue;

                // Find reverse link
                const reverseLink = links.find(l => l.source === link.target && l.target === link.source);
                const status1 = getLinkStatus(link);
                const status2 = reverseLink ? getLinkStatus(reverseLink) : 'down';

                // Use worst status for line color
                const worstStatus = status1 === 'down' || status2 === 'down' ? 'down' :
                    status1 === 'bad' || status2 === 'bad' ? 'bad' :
                    status1 === 'degraded' || status2 === 'degraded' ? 'degraded' : 'good';

                // Draw main line
                const midX = (from.x + to.x) / 2;
                const midY = (from.y + to.y) / 2;

                html += `<line class="link ${worstStatus}"
                    x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}"
                    stroke-width="4"
                    onclick="selectLink(${link.source}, ${link.target})"
                    data-src="${link.source}" data-dst="${link.target}"/>`;

                // Draw metrics label
                const ping1 = link.ping_ms >= 0 ? link.ping_ms.toFixed(0) + 'ms' : '---';
                const ping2 = reverseLink && reverseLink.ping_ms >= 0 ? reverseLink.ping_ms.toFixed(0) + 'ms' : '---';

                // Offset label perpendicular to line
                const dx = to.x - from.x;
                const dy = to.y - from.y;
                const len = Math.sqrt(dx*dx + dy*dy);
                const ox = -dy/len * 15;
                const oy = dx/len * 15;

                html += `<text class="link-metrics ${worstStatus === 'bad' ? 'bad' : ''}"
                    x="${midX + ox}" y="${midY + oy}"
                    text-anchor="middle">${ping1} / ${ping2}</text>`;

                drawnLinks.add(key);
            }

            // Draw drone nodes
            for (let i = 1; i <= DRONE_COUNT; i++) {
                const pos = dronePositions[i];
                html += `<g class="drone" transform="translate(${pos.x},${pos.y})">
                    <circle r="35"/>
                    <text y="2">D${i}</text>
                </g>`;
            }

            svg.innerHTML = html;
        }

        function renderLinksList() {
            const list = document.getElementById('links-list');
            let html = '';

            // Group by source drone
            for (let src = 1; src <= DRONE_COUNT; src++) {
                const srcLinks = links.filter(l => l.source === src);
                for (const link of srcLinks) {
                    const status = getLinkStatus(link);
                    const hasChaos = hasActiveChaos(link);
                    const chaos = link.chaos || {};

                    html += `<div class="link-item" onclick="selectLink(${link.source}, ${link.target})">
                        <div class="link-header">
                            <span class="link-name">D${link.source} → D${link.target}</span>
                            ${hasChaos ? `<span class="chaos-badge">CHAOS</span>` : ''}
                        </div>
                        <div class="link-stats">
                            <div class="metric">
                                <span class="status-dot ${status === 'down' ? 'bad' : 'good'}"></span>
                                PING: <span class="value ${status === 'down' ? 'bad' : ''}">${link.ping_ms >= 0 ? link.ping_ms.toFixed(1) + 'ms' : 'DOWN'}</span>
                            </div>
                            <div class="metric">
                                <span class="status-dot ${link.tcp_ok ? 'good' : 'bad'}"></span>
                                TCP
                            </div>
                            <div class="metric">
                                <span class="status-dot ${link.udp_ok ? 'good' : 'bad'}"></span>
                                UDP
                            </div>
                        </div>
                    </div>`;
                }
            }

            list.innerHTML = html || '<div style="color:#666">Waiting for data...</div>';
        }

        function selectLink(src, dst) {
            selectedLink = { source: src, target: dst };
            const link = links.find(l => l.source === src && l.target === dst);
            const chaos = link?.chaos || {};

            document.getElementById('modal-title').textContent = `Configure D${src} → D${dst}`;
            document.getElementById('latency-input').value = chaos.latency_ms || 0;
            document.getElementById('jitter-input').value = chaos.jitter_ms || 0;
            document.getElementById('loss-input').value = chaos.loss_percent || 0;
            document.getElementById('rate-input').value = chaos.rate_kbit || 0;

            document.getElementById('chaos-modal').classList.add('active');
        }

        function closeModal() {
            document.getElementById('chaos-modal').classList.remove('active');
            selectedLink = null;
        }

        function applyPreset(preset) {
            const presets = {
                'clear': { latency: 0, jitter: 0, loss: 0, rate: 0 },
                'good': { latency: 10, jitter: 5, loss: 0, rate: 0 },
                'degraded': { latency: 100, jitter: 30, loss: 5, rate: 0 },
                'bad': { latency: 500, jitter: 100, loss: 10, rate: 100 },
                'lossy': { latency: 50, jitter: 20, loss: 30, rate: 0 },
                'partition': { latency: 0, jitter: 0, loss: 100, rate: 0 },
            };
            const p = presets[preset];
            document.getElementById('latency-input').value = p.latency;
            document.getElementById('jitter-input').value = p.jitter;
            document.getElementById('loss-input').value = p.loss;
            document.getElementById('rate-input').value = p.rate;
        }

        async function applyChaos() {
            if (!selectedLink) return;

            const params = {
                latency_ms: parseInt(document.getElementById('latency-input').value) || 0,
                jitter_ms: parseInt(document.getElementById('jitter-input').value) || 0,
                loss_percent: parseInt(document.getElementById('loss-input').value) || 0,
                rate_kbit: parseInt(document.getElementById('rate-input').value) || 0,
            };

            try {
                await fetch(`/api/chaos/${selectedLink.source}/${selectedLink.target}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(params)
                });
                closeModal();
                setTimeout(fetchLinks, 500);
            } catch (e) {
                console.error('Failed to apply chaos:', e);
            }
        }

        async function clearChaos() {
            if (!selectedLink) return;
            try {
                await fetch(`/api/chaos/${selectedLink.source}/${selectedLink.target}`, {
                    method: 'DELETE'
                });
                closeModal();
                setTimeout(fetchLinks, 500);
            } catch (e) {
                console.error('Failed to clear chaos:', e);
            }
        }

        // Initial load and refresh
        fetchLinks();
        setInterval(fetchLinks, 2000);
    </script>
</body>
</html>
"""


def get_all_metrics():
    """Read metrics from all drones."""
    metrics = {}
    for i in range(1, DRONE_COUNT + 1):
        metrics_file = METRICS_DIR / f"drone{i}.json"
        if metrics_file.exists():
            try:
                with open(metrics_file) as f:
                    data = json.load(f)
                    # Check if data is stale (>10 seconds old)
                    if time.time() - data.get("timestamp", 0) < 10:
                        metrics[i] = data
            except (json.JSONDecodeError, IOError):
                pass
    return metrics


def build_links():
    """Build link data from metrics."""
    metrics = get_all_metrics()
    links = []

    for src_id, src_data in metrics.items():
        probes = src_data.get("probes", {})
        chaos = src_data.get("chaos", {})

        for dst_id_str, probe_data in probes.items():
            dst_id = int(dst_id_str)
            link = {
                "source": src_id,
                "target": dst_id,
                "ping_ms": probe_data.get("ping_ms", -1),
                "tcp_ok": probe_data.get("tcp_ok", False),
                "udp_ok": probe_data.get("udp_ok", False),
                "chaos": chaos.get(str(dst_id), chaos.get(dst_id, {})),
            }
            links.append(link)

    return links


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE, drone_count=DRONE_COUNT)


@app.route("/api/links")
def api_links():
    return jsonify(build_links())


@app.route("/api/metrics")
def api_metrics():
    return jsonify(get_all_metrics())


@app.route("/api/chaos/<int:src>/<int:dst>", methods=["POST", "DELETE"])
def api_chaos(src, dst):
    """Proxy chaos control to the source drone's radio."""
    radio_url = f"http://drone{src}_radio:8080/chaos/{dst}"

    try:
        if request.method == "POST":
            resp = requests.post(radio_url, json=request.json, timeout=5)
        else:
            resp = requests.delete(radio_url, timeout=5)
        return jsonify(resp.json()), resp.status_code
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
