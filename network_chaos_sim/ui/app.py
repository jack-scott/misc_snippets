"""MANET Chaos Simulator UI - Enhanced with position, environment, and topology controls."""

import json
import os
import time
from pathlib import Path

import requests
import yaml
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)
DRONE_COUNT = int(os.environ.get("DRONE_COUNT", 3))
METRICS_DIR = Path("/metrics")
CONFIG_DIR = Path("/config")

def load_config():
    config_file = CONFIG_DIR / "config.yaml"
    if config_file.exists():
        with open(config_file) as f:
            return yaml.safe_load(f)
    return {}

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
            grid-template-columns: 1fr 320px;
            gap: 20px;
        }

        .panel {
            background: #16213e;
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 15px;
        }
        .panel h2 {
            font-size: 12px;
            color: #666;
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }

        /* Topology visualization */
        .topology { min-height: 400px; position: relative; }
        .topology svg { width: 100%; height: 380px; cursor: grab; }
        .topology svg.dragging { cursor: grabbing; }
        .zoom-controls {
            position: absolute;
            top: 35px;
            right: 10px;
            display: flex;
            flex-direction: column;
            gap: 5px;
        }
        .zoom-btn {
            width: 28px;
            height: 28px;
            background: #0f3460;
            border: 1px solid #2a4a6a;
            border-radius: 4px;
            color: #fff;
            font-size: 16px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .zoom-btn:hover { background: #1a4a7a; border-color: #00d9ff; }
        .zoom-level { font-size: 10px; color: #666; text-align: center; }

        .drone circle {
            fill: #0f3460;
            stroke: #00d9ff;
            stroke-width: 2;
            cursor: pointer;
        }
        .drone:hover circle { fill: #1a4a7a; }
        .drone.base circle { fill: #2d1b4e; stroke: #9b59b6; }
        .drone text { fill: #fff; font-size: 12px; font-weight: 600; text-anchor: middle; dominant-baseline: middle; pointer-events: none; }
        .drone .pos-label { fill: #666; font-size: 9px; font-weight: normal; }

        .link { cursor: pointer; }
        .link:hover { stroke-width: 5 !important; }
        .link.good { stroke: #00ff88; }
        .link.degraded { stroke: #ffaa00; }
        .link.bad { stroke: #ff4444; }
        .link.down { stroke: #333; stroke-dasharray: 5,5; }
        .link.override { stroke-dasharray: 8,4; }
        .link.partition { stroke: #ff00ff; stroke-dasharray: 3,6; }

        .link-label { font-size: 9px; fill: #888; pointer-events: none; }
        .link-traffic { font-size: 8px; fill: #666; pointer-events: none; }

        /* Node stats panel */
        .node-stats {
            max-height: 200px;
            overflow-y: auto;
        }
        .node-stat-item {
            background: #0f3460;
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 8px;
            font-size: 12px;
        }
        .node-stat-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }
        .node-stat-name { font-weight: 600; }
        .node-stat-load {
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 10px;
            font-weight: 600;
        }
        .node-stat-load.low { background: #00ff8833; color: #00ff88; }
        .node-stat-load.medium { background: #ffaa0033; color: #ffaa00; }
        .node-stat-load.high { background: #ff444433; color: #ff4444; }
        .node-stat-details {
            display: flex;
            gap: 12px;
            font-size: 10px;
            color: #888;
        }
        .node-stat-details span { display: flex; align-items: center; gap: 4px; }

        /* Controls */
        .control-row {
            display: flex;
            gap: 10px;
            margin-bottom: 12px;
        }
        .control-group { flex: 1; }
        .control-group label { display: block; font-size: 11px; color: #666; margin-bottom: 4px; }
        .control-group select, .control-group input {
            width: 100%;
            padding: 8px;
            background: #0f3460;
            border: 1px solid #2a4a6a;
            border-radius: 6px;
            color: #fff;
            font-size: 13px;
        }
        .control-group select:focus, .control-group input:focus {
            outline: none;
            border-color: #00d9ff;
        }

        /* Status indicators */
        .status-row {
            display: flex;
            gap: 15px;
            padding: 10px;
            background: #0f3460;
            border-radius: 8px;
            margin-bottom: 12px;
            font-size: 12px;
        }
        .status-item { display: flex; align-items: center; gap: 6px; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; }
        .status-dot.green { background: #00ff88; }
        .status-dot.yellow { background: #ffaa00; }
        .status-dot.red { background: #ff4444; }

        /* Link list */
        .link-item {
            background: #0f3460;
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 8px;
            font-size: 12px;
        }
        .link-header { display: flex; justify-content: space-between; margin-bottom: 4px; }
        .link-name { font-weight: 600; }
        .link-stats { display: flex; gap: 10px; color: #888; font-size: 11px; }
        .link-stats span { display: flex; align-items: center; gap: 4px; }

        /* Position editor modal */
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
            min-width: 350px;
        }
        .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .modal-close { background: none; border: none; color: #666; font-size: 24px; cursor: pointer; }

        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
        }
        .btn-primary { background: #00d9ff; color: #000; }
        .btn-primary:hover { background: #00b8d9; }
        .btn-sm { padding: 4px 10px; font-size: 11px; }

        /* Legend */
        .legend { display: flex; gap: 15px; margin-top: 10px; font-size: 11px; color: #666; }
        .legend-item { display: flex; align-items: center; gap: 5px; }
        .legend-line { width: 20px; height: 3px; border-radius: 2px; }
        .legend-line.good { background: #00ff88; }
        .legend-line.degraded { background: #ffaa00; }
        .legend-line.bad { background: #ff4444; }
    </style>
</head>
<body>
    <div class="container">
        <h1>MANET Chaos Simulator</h1>
        <p class="subtitle">Position-based degradation | Shared radio bandwidth | Environment profiles</p>

        <div class="main-layout">
            <div>
                <div class="panel topology">
                    <h2>Network Topology</h2>
                    <svg id="topology-svg" viewBox="0 0 600 380"></svg>
                    <div class="zoom-controls">
                        <button class="zoom-btn" onclick="zoomIn()" title="Zoom in">+</button>
                        <button class="zoom-btn" onclick="zoomOut()" title="Zoom out">−</button>
                        <button class="zoom-btn" onclick="resetZoom()" title="Reset">⌂</button>
                        <div class="zoom-level" id="zoom-level">100%</div>
                    </div>
                    <div class="legend">
                        <div class="legend-item"><div class="legend-line good"></div> Good</div>
                        <div class="legend-item"><div class="legend-line degraded"></div> Degraded</div>
                        <div class="legend-item"><div class="legend-line bad"></div> Bad</div>
                        <div class="legend-item"><div class="legend-line" style="background:#ff00ff"></div> Partitioned</div>
                        <div class="legend-item"><div class="legend-line good" style="background:repeating-linear-gradient(90deg,#00ff88 0,#00ff88 8px,transparent 8px,transparent 12px)"></div> Override</div>
                    </div>
                </div>
            </div>

            <div class="side-panel">
                <div class="panel">
                    <h2>Network Settings</h2>
                    <div class="control-row">
                        <div class="control-group">
                            <label>Topology</label>
                            <select id="topology-select" onchange="setTopology(this.value)">
                                <option value="mesh">Mesh (all-to-all)</option>
                                <option value="star">Star (via base station)</option>
                            </select>
                        </div>
                    </div>
                    <div class="control-row">
                        <div class="control-group">
                            <label>Environment</label>
                            <select id="environment-select" onchange="setEnvironment(this.value)">
                                <option value="clear">Clear</option>
                                <option value="humid">Humid</option>
                                <option value="light_rain">Light Rain</option>
                                <option value="heavy_rain">Heavy Rain</option>
                                <option value="storm">Storm</option>
                                <option value="fog">Fog</option>
                                <option value="urban">Urban</option>
                            </select>
                        </div>
                    </div>
                    <div class="status-row">
                        <div class="status-item">
                            <span class="status-dot green"></span>
                            <span id="status-bw">1000 kbps</span>
                        </div>
                        <div class="status-item">
                            <span id="status-drones">3 drones</span>
                        </div>
                    </div>
                </div>

                <div class="panel">
                    <h2>Node Traffic</h2>
                    <div id="node-stats" class="node-stats"></div>
                </div>

                <div class="panel">
                    <h2>Links</h2>
                    <div id="links-list"></div>
                </div>
            </div>
        </div>
    </div>

    <!-- Position Editor Modal -->
    <div class="modal" id="position-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 id="modal-title">Set Position</h2>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="control-row">
                <div class="control-group">
                    <label>X (meters)</label>
                    <input type="number" id="pos-x" value="0">
                </div>
                <div class="control-group">
                    <label>Y (meters)</label>
                    <input type="number" id="pos-y" value="0">
                </div>
            </div>
            <div class="control-row">
                <div class="control-group">
                    <label>Z / Altitude (meters)</label>
                    <input type="number" id="pos-z" value="50">
                </div>
            </div>
            <div style="margin-top: 15px;">
                <button class="btn btn-primary" onclick="savePosition()">Save Position</button>
            </div>
        </div>
    </div>

    <!-- Link Editor Modal -->
    <div class="modal" id="link-modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2 id="link-modal-title">Edit Link</h2>
                <button class="modal-close" onclick="closeLinkModal()">&times;</button>
            </div>
            <div class="status-row" style="margin-bottom: 15px;">
                <div class="status-item">
                    <span>Base latency: <strong id="link-base-latency">-</strong></span>
                </div>
                <div class="status-item">
                    <span>Base loss: <strong id="link-base-loss">-</strong></span>
                </div>
            </div>
            <div class="control-row">
                <div class="control-group">
                    <label>Extra Latency (ms)</label>
                    <input type="number" id="link-latency" value="0" min="0" max="5000">
                </div>
                <div class="control-group">
                    <label>Extra Loss (%)</label>
                    <input type="number" id="link-loss" value="0" min="0" max="100">
                </div>
            </div>
            <div class="control-row">
                <div class="control-group">
                    <label>
                        <input type="checkbox" id="link-partition"> Partition (100% loss)
                    </label>
                </div>
            </div>
            <div style="margin-top: 15px; display: flex; gap: 10px;">
                <button class="btn btn-primary" onclick="saveLinkOverride()">Apply</button>
                <button class="btn" style="background:#444;" onclick="clearLinkOverride()">Clear Override</button>
            </div>
        </div>
    </div>

    <script>
        const DRONE_COUNT = {{ drone_count }};
        const CONFIG = {{ config | tojson }};

        let metrics = {};
        let links = [];
        let selectedDrone = null;
        let selectedLink = null;  // {source, target}
        let currentTopology = 'mesh';
        let currentEnvironment = 'clear';

        // Zoom and pan state
        let zoom = 1;
        let panX = 0;
        let panY = 0;
        let isDragging = false;
        let dragStartX = 0;
        let dragStartY = 0;
        let dragStartPanX = 0;
        let dragStartPanY = 0;

        const MIN_ZOOM = 0.25;
        const MAX_ZOOM = 4;
        const ZOOM_STEP = 0.2;

        // Base positions (before zoom/pan transforms)
        const BASE_CENTER_X = 300, BASE_CENTER_Y = 190;
        const BASE_RADIUS = 120;  // Default circular layout radius
        const BASE_SCALE = 0.5;   // Real-world to pixel scale

        // Calculate base position for a drone (before zoom/pan)
        function getBasePosition(pos, droneId) {
            if (!pos || (pos.x === 0 && pos.y === 0)) {
                // Default circular layout if no position set
                const angle = (2 * Math.PI * (droneId - 1) / DRONE_COUNT) - Math.PI / 2;
                return {
                    x: BASE_CENTER_X + BASE_RADIUS * Math.cos(angle),
                    y: BASE_CENTER_Y + BASE_RADIUS * Math.sin(angle)
                };
            }

            return {
                x: BASE_CENTER_X + pos.x * BASE_SCALE,
                y: BASE_CENTER_Y - pos.y * BASE_SCALE  // Flip Y for screen coords
            };
        }

        // Apply semantic zoom transform to a position
        // Positions scale with zoom, but sizes stay constant
        function applyZoomTransform(basePos) {
            // Zoom around center of SVG
            const zoomCenterX = 300 + panX;
            const zoomCenterY = 190 + panY;

            return {
                x: zoomCenterX + (basePos.x - 300) * zoom,
                y: zoomCenterY + (basePos.y - 190) * zoom
            };
        }

        // Format bytes to human readable
        function formatBytes(bytes) {
            if (bytes < 1024) return bytes + ' B/s';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB/s';
            return (bytes / 1024 / 1024).toFixed(1) + ' MB/s';
        }

        async function fetchMetrics() {
            try {
                const resp = await fetch('/api/metrics');
                metrics = await resp.json();
                updateUI();
            } catch (e) {
                console.error('Failed to fetch metrics:', e);
            }
        }

        function updateUI() {
            // Update status from first drone's metrics
            const firstDrone = metrics[1] || {};
            currentTopology = firstDrone.topology || 'mesh';
            currentEnvironment = firstDrone.environment || 'clear';

            document.getElementById('topology-select').value = currentTopology;
            document.getElementById('environment-select').value = currentEnvironment;
            document.getElementById('status-bw').textContent = (firstDrone.bandwidth_kbps || 1000) + ' kbps';
            document.getElementById('status-drones').textContent = DRONE_COUNT + ' drones';

            // Build links array from metrics
            links = [];
            for (const [droneId, data] of Object.entries(metrics)) {
                const probes = data.probes || {};
                const overrides = data.link_overrides || {};
                for (const [targetId, probe] of Object.entries(probes)) {
                    const override = overrides[targetId] || {};
                    links.push({
                        source: parseInt(droneId),
                        target: parseInt(targetId),
                        ping_ms: probe.ping_ms,
                        tcp_ok: probe.tcp_ok,
                        udp_ok: probe.udp_ok,
                        distance_m: probe.distance_m || 0,
                        reachable: probe.reachable !== false,
                        position: data.position || {},
                        tx_bytes_sec: probe.tx_bytes_sec || 0,
                        tx_packets_sec: probe.tx_packets_sec || 0,
                        dropped_sec: probe.dropped_sec || 0,
                        expected_latency_ms: probe.expected_latency_ms || 0,
                        expected_loss_percent: probe.expected_loss_percent || 0,
                        has_override: !!(override.extra_latency_ms || override.extra_loss_percent || override.partition),
                        partition: override.partition || false,
                    });
                }
            }

            renderTopology();
            renderLinksList();
            renderNodeStats();
        }

        function getLinkStatus(link) {
            if (!link.reachable || link.ping_ms < 0) return 'down';
            if (link.ping_ms > 100) return 'bad';
            if (link.ping_ms > 30) return 'degraded';
            return 'good';
        }

        function renderTopology() {
            const svg = document.getElementById('topology-svg');
            let content = '';

            // Get base positions (before zoom)
            const basePositions = {};
            for (let i = 1; i <= DRONE_COUNT; i++) {
                const droneMetrics = metrics[i] || {};
                basePositions[i] = getBasePosition(droneMetrics.position, i);
            }

            // Base station at center (if star topology)
            if (currentTopology === 'star') {
                basePositions[0] = { x: BASE_CENTER_X, y: BASE_CENTER_Y };
            }

            // Apply zoom transform to get display positions
            const positions = {};
            for (const [id, basePos] of Object.entries(basePositions)) {
                positions[id] = applyZoomTransform(basePos);
            }

            // Draw links (sizes stay constant, positions change with zoom)
            const drawnLinks = new Set();
            for (const link of links) {
                const key = [link.source, link.target].sort().join('-');
                if (drawnLinks.has(key)) continue;

                const from = positions[link.source];
                const to = positions[link.target];
                if (!from || !to) continue;

                const status = getLinkStatus(link);
                const overrideClass = link.partition ? 'partition' : (link.has_override ? 'override' : '');

                // Offset for bidirectional (constant offset regardless of zoom)
                const dx = to.x - from.x;
                const dy = to.y - from.y;
                const len = Math.sqrt(dx*dx + dy*dy) || 1;
                const ox = -dy/len * 6;
                const oy = dx/len * 6;

                content += `<line class="link ${status} ${overrideClass}"
                    x1="${from.x + ox}" y1="${from.y + oy}"
                    x2="${to.x + ox}" y2="${to.y + oy}"
                    stroke-width="3"
                    onclick="editLink(${link.source}, ${link.target})"/>`;

                // Distance and traffic label
                const midX = (from.x + to.x) / 2 + ox;
                const midY = (from.y + to.y) / 2 + oy;
                const dist = link.distance_m > 0 ? Math.round(link.distance_m) + 'm' : '';
                const traffic = link.tx_bytes_sec > 0 ? formatBytes(link.tx_bytes_sec) : '';

                content += `<text class="link-label" x="${midX}" y="${midY - 8}" text-anchor="middle">${dist}</text>`;
                if (traffic) {
                    content += `<text class="link-traffic" x="${midX}" y="${midY + 4}" text-anchor="middle">${traffic}</text>`;
                }

                drawnLinks.add(key);
            }

            // Draw base station (star topology) - size stays constant
            if (currentTopology === 'star') {
                const bsPos = positions[0];
                content += `<g class="drone base" transform="translate(${bsPos.x},${bsPos.y})" onclick="editPosition(0)">
                    <circle r="25"/>
                    <text y="2">BS</text>
                </g>`;
            }

            // Draw drones - sizes stay constant, positions change with zoom
            for (let i = 1; i <= DRONE_COUNT; i++) {
                const pos = positions[i];
                const realPos = metrics[i]?.position || {};
                const posLabel = realPos.x !== undefined ? `(${realPos.x}, ${realPos.y})` : '';

                content += `<g class="drone" transform="translate(${pos.x},${pos.y})" onclick="editPosition(${i})">
                    <circle r="28"/>
                    <text y="0">D${i}</text>
                    <text class="pos-label" y="40">${posLabel}</text>
                </g>`;
            }

            svg.innerHTML = content;
        }

        function updateTransform() {
            // Re-render topology with new zoom/pan values
            renderTopology();
            document.getElementById('zoom-level').textContent = Math.round(zoom * 100) + '%';
        }

        function zoomIn() {
            zoom = Math.min(MAX_ZOOM, zoom + ZOOM_STEP);
            updateTransform();
        }

        function zoomOut() {
            zoom = Math.max(MIN_ZOOM, zoom - ZOOM_STEP);
            updateTransform();
        }

        function resetZoom() {
            zoom = 1;
            panX = 0;
            panY = 0;
            updateTransform();
        }

        // Mouse wheel zoom
        document.addEventListener('DOMContentLoaded', () => {
            const svg = document.getElementById('topology-svg');

            svg.addEventListener('wheel', (e) => {
                e.preventDefault();
                const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP;
                const newZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom + delta));

                // Zoom toward mouse position
                const rect = svg.getBoundingClientRect();
                const mouseX = e.clientX - rect.left;
                const mouseY = e.clientY - rect.top;

                // Convert to SVG coordinates
                const svgX = (mouseX / rect.width) * 600;
                const svgY = (mouseY / rect.height) * 380;

                // Adjust pan to zoom toward mouse
                const zoomRatio = newZoom / zoom;
                panX = svgX - (svgX - panX) * zoomRatio;
                panY = svgY - (svgY - panY) * zoomRatio;

                zoom = newZoom;
                updateTransform();
            }, { passive: false });

            // Mouse drag pan
            svg.addEventListener('mousedown', (e) => {
                if (e.button !== 0) return;
                // Don't start drag if clicking on a drone
                if (e.target.closest('.drone')) return;

                isDragging = true;
                dragStartX = e.clientX;
                dragStartY = e.clientY;
                dragStartPanX = panX;
                dragStartPanY = panY;
                svg.classList.add('dragging');
            });

            document.addEventListener('mousemove', (e) => {
                if (!isDragging) return;

                const svg = document.getElementById('topology-svg');
                const rect = svg.getBoundingClientRect();

                // Convert pixel movement to SVG units
                const dx = (e.clientX - dragStartX) * (600 / rect.width);
                const dy = (e.clientY - dragStartY) * (380 / rect.height);

                panX = dragStartPanX + dx;
                panY = dragStartPanY + dy;
                updateTransform();
            });

            document.addEventListener('mouseup', () => {
                if (isDragging) {
                    isDragging = false;
                    document.getElementById('topology-svg').classList.remove('dragging');
                }
            });
        });

        function renderLinksList() {
            const list = document.getElementById('links-list');
            let html = '';

            for (const link of links) {
                const status = getLinkStatus(link);
                const pingStr = link.ping_ms >= 0 ? link.ping_ms.toFixed(1) + 'ms' : 'DOWN';
                const distStr = link.distance_m > 0 ? Math.round(link.distance_m) + 'm' : '-';
                const trafficStr = link.tx_bytes_sec > 0 ? formatBytes(link.tx_bytes_sec) : '-';
                const pktStr = link.tx_packets_sec > 0 ? link.tx_packets_sec + ' pkt/s' : '-';
                const droppedStr = link.dropped_sec > 0 ? `<span style="color:#ff4444">${link.dropped_sec} drop/s</span>` : '';

                html += `<div class="link-item">
                    <div class="link-header">
                        <span class="link-name">D${link.source} → ${link.target === 0 ? 'BS' : 'D' + link.target}</span>
                        <span style="color:#666;font-size:10px">${trafficStr}</span>
                    </div>
                    <div class="link-stats">
                        <span><span class="status-dot ${status === 'good' ? 'green' : status === 'degraded' ? 'yellow' : 'red'}"></span>${pingStr}</span>
                        <span>TCP: ${link.tcp_ok ? '✓' : '✗'}</span>
                        <span>UDP: ${link.udp_ok ? '✓' : '✗'}</span>
                        <span>${distStr}</span>
                        <span>${pktStr}</span>
                        ${droppedStr}
                    </div>
                </div>`;
            }

            list.innerHTML = html || '<div style="color:#666">Waiting for data...</div>';
        }

        function renderNodeStats() {
            const container = document.getElementById('node-stats');
            let html = '';

            for (let i = 1; i <= DRONE_COUNT; i++) {
                const data = metrics[i] || {};
                const traffic = data.traffic || {};
                const load = traffic.load_percent || 0;
                const txRate = traffic.tx_bytes_sec || 0;
                const rxRate = traffic.rx_bytes_sec || 0;
                const txPkt = traffic.tx_packets_sec || 0;
                const rxPkt = traffic.rx_packets_sec || 0;

                let loadClass = 'low';
                if (load > 70) loadClass = 'high';
                else if (load > 30) loadClass = 'medium';

                html += `<div class="node-stat-item">
                    <div class="node-stat-header">
                        <span class="node-stat-name">Drone ${i}</span>
                        <span class="node-stat-load ${loadClass}">${load.toFixed(1)}% load</span>
                    </div>
                    <div class="node-stat-details">
                        <span>↑ ${formatBytes(txRate)}</span>
                        <span>↓ ${formatBytes(rxRate)}</span>
                        <span>${txPkt + rxPkt} pkt/s</span>
                    </div>
                </div>`;
            }

            container.innerHTML = html || '<div style="color:#666">Waiting for data...</div>';
        }

        function editPosition(droneId) {
            selectedDrone = droneId;
            const pos = metrics[droneId]?.position || { x: 0, y: 0, z: 50 };

            document.getElementById('modal-title').textContent =
                droneId === 0 ? 'Base Station Position' : `Drone ${droneId} Position`;
            document.getElementById('pos-x').value = pos.x || 0;
            document.getElementById('pos-y').value = pos.y || 0;
            document.getElementById('pos-z').value = pos.z || 50;

            document.getElementById('position-modal').classList.add('active');
        }

        function closeModal() {
            document.getElementById('position-modal').classList.remove('active');
            selectedDrone = null;
        }

        function editLink(source, target) {
            selectedLink = { source, target };

            // Find link data
            const link = links.find(l => l.source === source && l.target === target);
            const baseLatency = link?.expected_latency_ms || 0;
            const baseLoss = link?.expected_loss_percent || 0;

            document.getElementById('link-modal-title').textContent =
                `Link: D${source} → ${target === 0 ? 'BS' : 'D' + target}`;
            document.getElementById('link-base-latency').textContent = baseLatency.toFixed(1) + 'ms';
            document.getElementById('link-base-loss').textContent = baseLoss.toFixed(1) + '%';

            // Check for existing override
            const droneData = metrics[source] || {};
            const override = droneData.link_overrides?.[target] || {};

            document.getElementById('link-latency').value = override.extra_latency_ms || 0;
            document.getElementById('link-loss').value = override.extra_loss_percent || 0;
            document.getElementById('link-partition').checked = override.partition || false;

            document.getElementById('link-modal').classList.add('active');
        }

        function closeLinkModal() {
            document.getElementById('link-modal').classList.remove('active');
            selectedLink = null;
        }

        async function saveLinkOverride() {
            if (!selectedLink) return;

            const partition = document.getElementById('link-partition').checked;
            const override = {
                extra_latency_ms: partition ? 0 : parseInt(document.getElementById('link-latency').value) || 0,
                extra_loss_percent: partition ? 100 : parseInt(document.getElementById('link-loss').value) || 0,
                partition: partition,
            };

            try {
                await fetch(`/api/link/${selectedLink.source}/${selectedLink.target}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(override)
                });
                closeLinkModal();
                setTimeout(fetchMetrics, 500);
            } catch (e) {
                console.error('Failed to set link override:', e);
            }
        }

        async function clearLinkOverride() {
            if (!selectedLink) return;

            try {
                await fetch(`/api/link/${selectedLink.source}/${selectedLink.target}`, {
                    method: 'DELETE',
                });
                closeLinkModal();
                setTimeout(fetchMetrics, 500);
            } catch (e) {
                console.error('Failed to clear link override:', e);
            }
        }

        async function savePosition() {
            if (selectedDrone === null) return;

            const pos = {
                x: parseFloat(document.getElementById('pos-x').value) || 0,
                y: parseFloat(document.getElementById('pos-y').value) || 0,
                z: parseFloat(document.getElementById('pos-z').value) || 50,
            };

            try {
                await fetch(`/api/position/${selectedDrone}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(pos)
                });
                closeModal();
                setTimeout(fetchMetrics, 500);
            } catch (e) {
                console.error('Failed to set position:', e);
            }
        }

        async function setTopology(mode) {
            try {
                await fetch('/api/topology', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode })
                });
                setTimeout(fetchMetrics, 500);
            } catch (e) {
                console.error('Failed to set topology:', e);
            }
        }

        async function setEnvironment(profile) {
            try {
                await fetch('/api/environment', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ profile })
                });
                setTimeout(fetchMetrics, 500);
            } catch (e) {
                console.error('Failed to set environment:', e);
            }
        }

        // Initial load and refresh
        fetchMetrics();
        setInterval(fetchMetrics, 2000);
    </script>
</body>
</html>
"""


def get_all_metrics():
    """Read metrics from all drones."""
    metrics = {}
    for i in range(0, DRONE_COUNT + 1):  # Include base station (0)
        metrics_file = METRICS_DIR / f"drone{i}.json"
        if metrics_file.exists():
            try:
                with open(metrics_file) as f:
                    data = json.load(f)
                    if time.time() - data.get("timestamp", 0) < 15:
                        metrics[i] = data
            except (json.JSONDecodeError, IOError):
                pass
    return metrics


@app.route("/")
def index():
    config = load_config()
    return render_template_string(HTML_TEMPLATE, drone_count=DRONE_COUNT, config=config)


@app.route("/api/metrics")
def api_metrics():
    return jsonify(get_all_metrics())


@app.route("/api/config")
def api_config():
    return jsonify(load_config())


@app.route("/api/position/<int:drone_id>", methods=["POST"])
def api_set_position(drone_id):
    """Set a drone's position (broadcasts to all drones)."""
    data = request.json
    results = []

    # Send to the target drone
    if drone_id == 0:
        url = "http://base_station_radio:8080/position"
    else:
        url = f"http://drone{drone_id}_radio:8080/position"

    try:
        resp = requests.post(url, json=data, timeout=5)
        results.append({"drone": drone_id, "ok": resp.ok})
    except requests.RequestException as e:
        results.append({"drone": drone_id, "error": str(e)})

    # Also update other drones about this position change
    for i in range(1, DRONE_COUNT + 1):
        if i == drone_id:
            continue
        try:
            resp = requests.post(
                f"http://drone{i}_radio:8080/positions/{drone_id}",
                json=data, timeout=2
            )
        except requests.RequestException:
            pass

    return jsonify({"results": results})


@app.route("/api/topology", methods=["POST"])
def api_set_topology():
    """Set topology mode for all drones."""
    data = request.json
    results = []

    # Set on all drones
    for i in range(1, DRONE_COUNT + 1):
        try:
            resp = requests.post(
                f"http://drone{i}_radio:8080/topology",
                json=data, timeout=5
            )
            results.append({"drone": i, "ok": resp.ok})
        except requests.RequestException as e:
            results.append({"drone": i, "error": str(e)})

    return jsonify({"results": results})


@app.route("/api/environment", methods=["POST"])
def api_set_environment():
    """Set environment profile for all drones."""
    data = request.json
    results = []

    for i in range(1, DRONE_COUNT + 1):
        try:
            resp = requests.post(
                f"http://drone{i}_radio:8080/environment",
                json=data, timeout=5
            )
            results.append({"drone": i, "ok": resp.ok})
        except requests.RequestException as e:
            results.append({"drone": i, "error": str(e)})

    return jsonify({"results": results})


@app.route("/api/link/<int:source>/<int:target>", methods=["POST"])
def api_set_link_override(source, target):
    """Set link quality override (extra latency/loss or partition)."""
    data = request.json

    # Send to the source drone
    if source == 0:
        url = "http://base_station_radio:8080/link_override"
    else:
        url = f"http://drone{source}_radio:8080/link_override"

    try:
        resp = requests.post(
            url,
            json={"target": target, **data},
            timeout=5
        )
        return jsonify({"ok": resp.ok})
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/link/<int:source>/<int:target>", methods=["DELETE"])
def api_clear_link_override(source, target):
    """Clear link quality override."""
    if source == 0:
        url = "http://base_station_radio:8080/link_override"
    else:
        url = f"http://drone{source}_radio:8080/link_override"

    try:
        resp = requests.delete(
            f"{url}/{target}",
            timeout=5
        )
        return jsonify({"ok": resp.ok})
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
