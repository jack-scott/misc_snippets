import { useState, useEffect, useRef } from "react";

// ─────────────────────────────────────────────────────────────────────────────
// CONSTANTS
// ─────────────────────────────────────────────────────────────────────────────
const STORAGE_CONFIG_KEY = "fleet-sync-config";
const STORAGE_DRONES_KEY = "fleet-sync-drones";

const DEFAULT_CONFIG = {
  localSubnet: "172.0.0.0/8",
  sshUser: "root",
  sshKeysDir: "keys",
};

const C = {
  bgPage:      "#0d1117",
  bgCard:      "#161b22",
  bgSubtle:    "#1c2128",
  border:      "#30363d",
  borderFaint: "#21262d",
  textHigh:    "#e6edf3",
  textMid:     "#8b949e",
  textDim:     "#484f58",
  blue:        "#388bfd",
  green:       "#3fb950",
  orange:      "#d29922",
  red:         "#f85149",
};

const FONT_UI   = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif";
const FONT_MONO = "'SF Mono', 'Fira Code', monospace";

// ─────────────────────────────────────────────────────────────────────────────
// API
// ─────────────────────────────────────────────────────────────────────────────
async function api(method, path, body) {
  const opts = {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  };
  const r = await fetch(path, opts);
  if (!r.ok) {
    const detail = await r.json().then(d => d.detail || r.statusText).catch(() => r.statusText);
    throw new Error(detail);
  }
  return r.json();
}
const GET  = path      => api("GET",  path);
const POST = (path, b) => api("POST", path, b);
const PUT  = (path, b) => api("PUT",  path, b);

// ─────────────────────────────────────────────────────────────────────────────
// UTILS
// ─────────────────────────────────────────────────────────────────────────────
function fmtBytes(b) {
  if (!b) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(b) / Math.log(1024));
  return `${(b / Math.pow(1024, i)).toFixed(1)} ${u[i]}`;
}
function loadLS(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
  catch { return fallback; }
}
function saveLS(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch {}
}

// ─────────────────────────────────────────────────────────────────────────────
// PRIMITIVES
// ─────────────────────────────────────────────────────────────────────────────
function Button({ children, onClick, disabled, variant = "default", size = "md", fullWidth }) {
  const styles = {
    default: { border: C.border,       color: C.textMid },
    primary: { border: C.blue,         color: C.blue    },
    danger:  { border: C.red,          color: C.red     },
    ghost:   { border: "transparent",  color: C.textDim },
  };
  const v = styles[variant] || styles.default;
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        background: "transparent",
        border: `1px solid ${disabled ? C.borderFaint : v.border}`,
        borderRadius: 6,
        color: disabled ? C.textDim : v.color,
        cursor: disabled ? "default" : "pointer",
        fontFamily: FONT_UI,
        fontSize: size === "sm" ? 12 : 13,
        fontWeight: 500,
        padding: size === "sm" ? "4px 10px" : "6px 14px",
        whiteSpace: "nowrap",
        width: fullWidth ? "100%" : "auto",
        transition: "border-color 0.12s, color 0.12s",
      }}
    >{children}</button>
  );
}

function Input({ value, onChange, placeholder, type = "text" }) {
  return (
    <input
      type={type}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      style={{
        width: "100%",
        background: C.bgPage,
        border: `1px solid ${C.border}`,
        borderRadius: 6,
        padding: "7px 10px",
        color: C.textHigh,
        fontFamily: FONT_UI,
        fontSize: 13,
      }}
    />
  );
}

function Toggle({ on, onChange }) {
  return (
    <div
      onClick={e => { e.stopPropagation(); onChange(!on); }}
      style={{
        width: 32, height: 18, borderRadius: 9, flexShrink: 0,
        background: on ? C.blue : C.bgSubtle,
        border: `1px solid ${on ? C.blue : C.border}`,
        position: "relative", cursor: "pointer",
        transition: "background 0.15s, border-color 0.15s",
      }}
    >
      <div style={{
        width: 12, height: 12, borderRadius: "50%",
        background: "#fff",
        position: "absolute", top: 2,
        left: on ? 16 : 2,
        transition: "left 0.15s",
        boxShadow: "0 1px 2px rgba(0,0,0,0.4)",
      }} />
    </div>
  );
}

const CONN_META = {
  local:   { label: "Local",   bg: "rgba(63,185,80,0.12)",  color: C.green  },
  relay:   { label: "Relay",   bg: "rgba(210,153,34,0.12)", color: C.orange },
  wan:     { label: "WAN",     bg: "rgba(56,139,253,0.12)", color: C.blue   },
  offline: { label: "Offline", bg: "rgba(248,81,73,0.10)",  color: C.red    },
};

function ConnBadge({ status }) {
  const m = CONN_META[status] || CONN_META.offline;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      background: m.bg, color: m.color,
      borderRadius: 20, padding: "2px 8px 2px 6px",
      fontSize: 11, fontWeight: 500, fontFamily: FONT_UI,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: m.color, display: "inline-block" }} />
      {m.label}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// DATE ROW
// Progress and sizes always come from server-side Syncthing API (no tunnel needed).
// droneBytes = global index size (what drone has), serverBytes = global - need.
// ─────────────────────────────────────────────────────────────────────────────
function DateRow({ row, onToggle }) {
  const { date, serverBytes, droneBytes, syncEnabled, progress } = row;
  const pct = progress || 0;
  const complete = pct >= 100;
  const barColor = complete ? C.green : (syncEnabled ? C.blue : C.borderFaint);

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10,
      padding: "7px 10px", borderRadius: 6, marginBottom: 2,
      background: syncEnabled ? "rgba(56,139,253,0.06)" : "transparent",
      border: `1px solid ${syncEnabled ? "rgba(56,139,253,0.18)" : "transparent"}`,
      transition: "background 0.15s, border-color 0.15s",
    }}>
      <Toggle on={syncEnabled} onChange={enabled => onToggle(date, enabled)} />

      <span style={{
        fontFamily: FONT_MONO, fontSize: 13,
        color: syncEnabled ? C.textHigh : C.textMid,
        flexShrink: 0, width: 96,
      }}>{date}</span>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          height: 4, borderRadius: 2, overflow: "hidden",
          background: C.bgSubtle, marginBottom: 4,
        }}>
          <div style={{
            height: "100%",
            width: `${Math.min(pct, 100)}%`,
            background: barColor,
            transition: "width 0.5s, background 0.2s",
          }} />
        </div>
        <div style={{ display: "flex", gap: 4, fontSize: 11, fontFamily: FONT_MONO, color: C.textDim }}>
          {syncEnabled ? (
            <>
              <span style={{ color: complete ? C.green : C.textMid }}>{fmtBytes(serverBytes)}</span>
              <span>/</span>
              <span>{fmtBytes(droneBytes)}</span>
            </>
          ) : (
            <span>{fmtBytes(droneBytes)}</span>
          )}
        </div>
      </div>

      <span style={{ fontSize: 11, fontFamily: FONT_MONO, color: C.textDim, flexShrink: 0, width: 32, textAlign: "right" }}>
        {row.droneFiles}f
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// ADD DRONE MODAL
// ─────────────────────────────────────────────────────────────────────────────
function ProvisionModal({ onClose, onDroneAdded }) {
  const [droneName, setDroneName] = useState("");
  const [droneHost, setDroneHost] = useState("127.0.0.1");
  const [sshPort,   setSshPort  ] = useState("22");
  const [pending,   setPending  ] = useState(false);
  const [err,       setErr      ] = useState("");

  async function handleAdd() {
    if (!droneHost.trim()) return;
    setPending(true);
    setErr("");
    try {
      const r = await POST("/api/provision/add", {
        name:     droneName.trim() || droneHost.trim(),
        host:     droneHost.trim(),
        ssh_port: parseInt(sshPort) || 22,
      });
      onDroneAdded({
        id:       r.device_id,
        name:     r.name,
        apiKey:   r.api_key,
        keyPath:  r.key_path,
        host:     r.host,
        sshPort:  r.ssh_port,
        folderId: r.folder_id,
        addedAt:  Date.now(),
      });
      onClose();
    } catch (e) {
      setErr(e.message);
    }
    setPending(false);
  }

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.8)",
      display: "flex", alignItems: "center", justifyContent: "center",
      zIndex: 100, padding: 24,
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: C.bgCard, border: `1px solid ${C.border}`,
        borderRadius: 10, width: "100%", maxWidth: 420, padding: 28,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 22 }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: C.textHigh, fontFamily: FONT_UI }}>Add Drone</h2>
          <Button onClick={onClose} size="sm">✕</Button>
        </div>

        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 12, color: C.textMid, marginBottom: 6, fontFamily: FONT_UI }}>Name (optional)</div>
          <Input value={droneName} onChange={setDroneName} placeholder="drone-delta-4" />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 10, marginBottom: 22 }}>
          <div>
            <div style={{ fontSize: 12, color: C.textMid, marginBottom: 6, fontFamily: FONT_UI }}>Drone IP</div>
            <Input value={droneHost} onChange={setDroneHost} placeholder="192.168.1.77" />
          </div>
          <div>
            <div style={{ fontSize: 12, color: C.textMid, marginBottom: 6, fontFamily: FONT_UI }}>SSH Port</div>
            <Input value={sshPort} onChange={setSshPort} placeholder="22" type="number" />
          </div>
        </div>

        <p style={{ fontSize: 12, color: C.textDim, marginBottom: 16, lineHeight: 1.6, fontFamily: FONT_UI }}>
          The backend will SSH in with the fleet key, read the Syncthing API key, and create a per-drone sync folder.
        </p>

        {err && (
          <div style={{
            padding: "9px 12px", marginBottom: 14, borderRadius: 6,
            background: "rgba(248,81,73,0.06)", border: "1px solid rgba(248,81,73,0.2)",
            fontSize: 12, color: C.red, fontFamily: FONT_UI,
          }}>{err}</div>
        )}

        <Button onClick={handleAdd} disabled={!droneHost.trim() || pending} variant="primary" fullWidth>
          {pending ? "Connecting…" : "Add Drone"}
        </Button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SETTINGS PANEL
// ─────────────────────────────────────────────────────────────────────────────
function SettingsPanel({ config, onSave, onClose }) {
  const [local, setLocal] = useState({ ...config });
  function upd(k, v) { setLocal(p => ({ ...p, [k]: v })); }
  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.8)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: 24,
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: C.bgCard, border: `1px solid ${C.border}`, borderRadius: 10,
        width: "100%", maxWidth: 480, maxHeight: "85vh", overflowY: "auto", padding: 28,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 22 }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: C.textHigh, fontFamily: FONT_UI }}>Settings</h2>
          <Button onClick={onClose} size="sm">✕</Button>
        </div>
        {[
          { key: "localSubnet", label: "Local subnet",       hint: "IPs in this range show Local status", ph: "172.0.0.0/8" },
          { key: "sshUser",     label: "SSH user",           hint: "Username on drone OS",                ph: "root"        },
          { key: "sshKeysDir",  label: "SSH keys directory", hint: "Per-drone keys stored here",          ph: "keys"        },
        ].map(f => (
          <div key={f.key} style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12, color: C.textMid, marginBottom: 4, fontFamily: FONT_UI, fontWeight: 500 }}>{f.label}</div>
            <p style={{ fontSize: 11, color: C.textDim, marginBottom: 6, fontFamily: FONT_UI }}>{f.hint}</p>
            <Input value={local[f.key] || ""} onChange={v => upd(f.key, v)} placeholder={f.ph} />
          </div>
        ))}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 8 }}>
          <Button onClick={onClose}>Cancel</Button>
          <Button onClick={() => { onSave(local); onClose(); }} variant="primary">Save</Button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// DRONE CARD
// Date list and progress come from server-side Syncthing — no tunnel required.
// Tunnel is optional (for future direct drone access).
// ─────────────────────────────────────────────────────────────────────────────
function DroneCard({ device, droneHistory, onUpdateHistory, onRemove }) {
  const [expanded,      setExpanded     ] = useState(false);
  const [tunnelOpen,    setTunnelOpen   ] = useState(false);
  const [tunnelPending, setTunnelPending] = useState(false);
  const [tunnelErr,     setTunnelErr    ] = useState("");
  const [dateRows,      setDateRows     ] = useState([]);
  const [datesLoading,  setDatesLoading ] = useState(false);
  const [rangeStart,    setRangeStart   ] = useState("");
  const [rangeEnd,      setRangeEnd     ] = useState("");
  const [applyingRange, setApplyingRange] = useState(false);
  const pollRef = useRef(null);

  const stored     = droneHistory[device.id] || {};
  const folderId   = stored.folderId;
  const canConnect = device.connectivity === "local" && !tunnelOpen && !!stored.host;
  const activeCount = dateRows.filter(r => r.syncEnabled).length;

  async function loadDates() {
    if (!folderId) return;
    try {
      const rows = await GET(`/api/sync/${folderId}/dates`);
      setDateRows(rows);
    } catch {}
  }

  // Load on expand — server Syncthing has the index, no tunnel needed
  useEffect(() => {
    if (!expanded || !folderId) return;
    setDatesLoading(true);
    loadDates().finally(() => setDatesLoading(false));
  }, [expanded, folderId]);

  // Poll while any date is actively syncing
  useEffect(() => {
    const hasActive = dateRows.some(r => r.syncEnabled && r.progress < 100);
    if (hasActive && expanded && !pollRef.current) {
      pollRef.current = setInterval(loadDates, 4000);
    } else if ((!hasActive || !expanded) && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, [dateRows.map(r => `${r.date}:${r.syncEnabled}:${r.progress}`).join(","), expanded, folderId]);

  async function openTunnel() {
    setTunnelPending(true);
    setTunnelErr("");
    try {
      await POST("/api/tunnel/open", {
        name:     device.id,
        host:     stored.host,
        ssh_port: stored.sshPort || 22,
        api_key:  stored.apiKey  || "",
        key_path: stored.keyPath || null,
      });
      setTunnelOpen(true);
    } catch (e) {
      setTunnelErr(e.message);
    }
    setTunnelPending(false);
  }

  async function closeTunnel() {
    try { await POST("/api/tunnel/close", { name: device.id }); } catch {}
    setTunnelOpen(false);
  }

  async function toggleDate(date, enabled) {
    if (!folderId) return;
    setDateRows(prev => prev.map(r => r.date === date ? { ...r, syncEnabled: enabled } : r));
    try {
      await PUT(`/api/sync/${folderId}/date/${date}`, { enabled });
      // Refresh after a short delay to get updated progress from db/need
      setTimeout(loadDates, 500);
    } catch {
      setDateRows(prev => prev.map(r => r.date === date ? { ...r, syncEnabled: !enabled } : r));
    }
  }

  function datesBetween(start, end) {
    const dates = [];
    const cur  = new Date(start + "T00:00:00");
    const last = new Date(end   + "T00:00:00");
    while (cur <= last) {
      dates.push(cur.toISOString().slice(0, 10));
      cur.setDate(cur.getDate() + 1);
    }
    return dates;
  }

  async function applyRange() {
    if (!rangeStart || !rangeEnd || !folderId) return;
    setApplyingRange(true);
    const start = rangeStart <= rangeEnd ? rangeStart : rangeEnd;
    const end   = rangeStart <= rangeEnd ? rangeEnd   : rangeStart;
    try {
      await PUT(`/api/sync/${folderId}/dates`, { dates: datesBetween(start, end), enabled: true });
      setRangeStart("");
      setRangeEnd("");
      await loadDates();
    } catch {}
    setApplyingRange(false);
  }

  return (
    <div style={{
      border: `1px solid ${C.border}`, borderRadius: 8,
      background: C.bgCard, marginBottom: 8, overflow: "hidden",
    }}>
      {/* Header */}
      <div
        onClick={() => setExpanded(v => !v)}
        style={{
          display: "flex", alignItems: "center", gap: 12,
          padding: "12px 16px", cursor: "pointer",
          borderBottom: expanded ? `1px solid ${C.borderFaint}` : "none",
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
            <span style={{ fontFamily: FONT_UI, fontSize: 14, fontWeight: 600, color: C.textHigh }}>
              {device.name}
            </span>
            <ConnBadge status={device.connectivity} />
            {tunnelOpen && <span style={{ fontSize: 11, color: C.blue, fontFamily: FONT_UI }}>tunnel</span>}
            {activeCount > 0 && (
              <span style={{ fontSize: 11, color: C.blue, fontFamily: FONT_UI }}>
                · {activeCount} syncing
              </span>
            )}
          </div>
          {device.address && (
            <span style={{ fontFamily: FONT_MONO, fontSize: 11, color: C.textDim }}>{device.address}</span>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
          <div style={{ textAlign: "right", marginRight: 4 }}>
            <div style={{ fontFamily: FONT_MONO, fontSize: 10, color: C.textDim }}>↓ {fmtBytes(device.inBytesTotal)}</div>
            <div style={{ fontFamily: FONT_MONO, fontSize: 10, color: C.textDim }}>↑ {fmtBytes(device.outBytesTotal)}</div>
          </div>

          <div onClick={e => e.stopPropagation()} style={{ display: "flex", gap: 6 }}>
            {canConnect && (
              <Button onClick={openTunnel} disabled={tunnelPending} variant="ghost" size="sm">
                {tunnelPending ? "…" : "Connect"}
              </Button>
            )}
            {tunnelOpen && (
              <Button onClick={closeTunnel} variant="ghost" size="sm">Disconnect</Button>
            )}
            <Button onClick={() => onRemove(device.id)} variant="danger" size="sm">✕</Button>
          </div>

          <span style={{
            color: C.textDim, fontSize: 12,
            transform: expanded ? "rotate(180deg)" : "none",
            transition: "transform 0.2s", display: "inline-block",
          }}>▾</span>
        </div>
      </div>

      {tunnelErr && (
        <div style={{
          padding: "6px 16px", fontSize: 12, color: C.red,
          background: "rgba(248,81,73,0.05)", borderBottom: "1px solid rgba(248,81,73,0.12)",
          fontFamily: FONT_UI,
        }}>{tunnelErr}</div>
      )}

      {/* Expanded panel */}
      {expanded && (
        <div style={{ padding: "14px 16px 16px" }}>
          {!stored.host && (
            <div style={{
              padding: "10px 14px", borderRadius: 6,
              background: C.bgSubtle, border: `1px solid ${C.border}`,
              fontSize: 13, color: C.textMid, fontFamily: FONT_UI,
            }}>
              Not provisioned — use <strong>Add Drone</strong> to set up SSH access.
            </div>
          )}

          {stored.host && !folderId && (
            <div style={{
              padding: "10px 14px", borderRadius: 6,
              background: C.bgSubtle, border: `1px solid ${C.border}`,
              fontSize: 13, color: C.textMid, fontFamily: FONT_UI,
            }}>
              No folder configured — re-provision this drone to set up per-drone sync.
            </div>
          )}

          {stored.host && folderId && (
            <>
              {/* Date range picker */}
              <div style={{
                marginBottom: 14, paddingBottom: 14,
                borderBottom: `1px solid ${C.borderFaint}`,
              }}>
                <div style={{ fontSize: 11, color: C.textDim, fontFamily: FONT_UI, marginBottom: 8 }}>
                  Enable date range
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <input
                    type="date"
                    value={rangeStart}
                    onChange={e => setRangeStart(e.target.value)}
                    style={{
                      flex: 1, minWidth: 130,
                      background: C.bgPage, border: `1px solid ${C.border}`,
                      borderRadius: 6, padding: "5px 10px",
                      color: C.textHigh, fontFamily: FONT_MONO, fontSize: 13,
                      colorScheme: "dark",
                    }}
                  />
                  <span style={{ color: C.textDim, fontSize: 12, flexShrink: 0 }}>to</span>
                  <input
                    type="date"
                    value={rangeEnd}
                    onChange={e => setRangeEnd(e.target.value)}
                    style={{
                      flex: 1, minWidth: 130,
                      background: C.bgPage, border: `1px solid ${C.border}`,
                      borderRadius: 6, padding: "5px 10px",
                      color: C.textHigh, fontFamily: FONT_MONO, fontSize: 13,
                      colorScheme: "dark",
                    }}
                  />
                  <Button
                    onClick={applyRange}
                    disabled={!rangeStart || !rangeEnd || applyingRange}
                    variant="primary" size="sm"
                  >
                    {applyingRange ? "…" : "Apply"}
                  </Button>
                </div>
              </div>

              {datesLoading ? (
                <span style={{ fontSize: 12, color: C.textDim, fontFamily: FONT_UI }}>Loading…</span>
              ) : dateRows.length === 0 ? (
                <div style={{ fontSize: 12, color: C.textDim, fontFamily: FONT_UI }}>
                  No log folders indexed yet — use the date picker above to pre-configure sync dates.
                </div>
              ) : (
                <>
                  <div style={{
                    display: "flex", alignItems: "center",
                    padding: "0 10px", marginBottom: 6, gap: 10,
                  }}>
                    <div style={{ width: 32 }} />
                    <div style={{ width: 96, fontSize: 10, color: C.textDim, fontFamily: FONT_UI, letterSpacing: 1, textTransform: "uppercase" }}>Date</div>
                    <div style={{ flex: 1, fontSize: 10, color: C.textDim, fontFamily: FONT_UI, letterSpacing: 1, textTransform: "uppercase" }}>Progress</div>
                    <div style={{ width: 32, fontSize: 10, color: C.textDim, fontFamily: FONT_UI, letterSpacing: 1, textAlign: "right" }}>Files</div>
                  </div>

                  {dateRows.map(row => (
                    <DateRow key={row.date} row={row} onToggle={toggleDate} />
                  ))}

                  {activeCount > 0 && (
                    <div style={{
                      marginTop: 10, paddingTop: 10, borderTop: `1px solid ${C.borderFaint}`,
                      fontSize: 12, color: C.textDim, fontFamily: FONT_UI,
                    }}>
                      {activeCount} date{activeCount !== 1 ? "s" : ""} enabled · syncing
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN APP
// ─────────────────────────────────────────────────────────────────────────────
export default function App() {
  const [config,        setConfig      ] = useState(DEFAULT_CONFIG);
  const [droneHistory,  setDroneHistory] = useState({});
  const [devices,       setDevices     ] = useState([]);
  const [loaded,        setLoaded      ] = useState(false);
  const [showSettings,  setShowSettings] = useState(false);
  const [showProvision, setShowProvision] = useState(false);
  const [refreshing,    setRefreshing  ] = useState(false);
  const [lastRefresh,   setLastRefresh ] = useState(null);
  const [backendErr,    setBackendErr  ] = useState(false);

  useEffect(() => {
    setConfig(loadLS(STORAGE_CONFIG_KEY, DEFAULT_CONFIG));
    setDroneHistory(loadLS(STORAGE_DRONES_KEY, {}));
    setLoaded(true);
  }, []);

  useEffect(() => { if (loaded) fetchDevices(); }, [loaded]);

  async function fetchDevices() {
    setRefreshing(true);
    try {
      const data = await GET("/api/devices");
      setDevices(data);
      setBackendErr(false);
    } catch {
      setBackendErr(true);
    }
    setLastRefresh(new Date());
    setRefreshing(false);
  }

  function saveConfig(cfg) {
    setConfig(cfg);
    saveLS(STORAGE_CONFIG_KEY, cfg);
  }

  async function updateDroneHistory(id, data) {
    const next = { ...droneHistory, [id]: data };
    setDroneHistory(next);
    saveLS(STORAGE_DRONES_KEY, next);
  }

  function registerDrone(drone) {
    const next = { ...droneHistory, [drone.id]: { ...droneHistory[drone.id], ...drone } };
    setDroneHistory(next);
    saveLS(STORAGE_DRONES_KEY, next);
    fetchDevices();
  }

  async function removeDrone(deviceId) {
    try { await api("DELETE", `/api/devices/${deviceId}`); } catch {}
    const next = { ...droneHistory };
    delete next[deviceId];
    setDroneHistory(next);
    saveLS(STORAGE_DRONES_KEY, next);
    setDevices(prev => prev.filter(d => (d.id || d.deviceID) !== deviceId));
  }

  if (!loaded) return (
    <div style={{ minHeight: "100vh", background: C.bgPage, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <span style={{ fontSize: 14, color: C.textDim, fontFamily: FONT_UI }}>Loading…</span>
    </div>
  );

  const online  = devices.filter(d => d.connectivity !== "offline").length;
  const offline = devices.filter(d => d.connectivity === "offline").length;

  return (
    <div style={{ minHeight: "100vh", background: C.bgPage, color: C.textHigh, fontFamily: FONT_UI }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: ${C.bgPage}; }
        input { outline: none; }
        input::placeholder { color: ${C.textDim}; }
        button:hover:not(:disabled) { opacity: 0.85; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-thumb { background: ${C.border}; border-radius: 2px; }
        .app-wrap { max-width: 860px; margin: 0 auto; padding: 32px 20px; }
        @media (max-width: 600px) { .app-wrap { padding: 20px 14px; } }
      `}</style>

      {showSettings  && <SettingsPanel config={config} onSave={saveConfig} onClose={() => setShowSettings(false)} />}
      {showProvision && <ProvisionModal onClose={() => setShowProvision(false)} onDroneAdded={registerDrone} />}

      <div className="app-wrap">
        {backendErr && (
          <div style={{
            padding: "10px 14px", marginBottom: 16, borderRadius: 6,
            background: "rgba(248,81,73,0.06)", border: "1px solid rgba(248,81,73,0.2)",
            display: "flex", alignItems: "center", gap: 10, fontSize: 13,
          }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: C.red, display: "inline-block", flexShrink: 0 }} />
            <span style={{ color: C.red }}>Backend offline</span>
            <span style={{ color: C.textDim }}>run: <code style={{ fontFamily: FONT_MONO, color: C.textMid }}>pixi run api</code></span>
          </div>
        )}

        {/* Header */}
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          marginBottom: 24, paddingBottom: 20, borderBottom: `1px solid ${C.border}`,
          flexWrap: "wrap", gap: 12,
        }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 600, color: C.textHigh, marginBottom: 2 }}>Fleet Sync</h1>
            <p style={{ fontSize: 13, color: C.textDim }}>Syncthing drone log dashboard</p>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Button onClick={() => setShowProvision(true)} variant="primary">Add Drone</Button>
            <Button onClick={() => setShowSettings(true)}>Settings</Button>
            <Button onClick={fetchDevices} disabled={refreshing}>{refreshing ? "…" : "↻"}</Button>
          </div>
        </div>

        {/* Summary bar */}
        <div style={{
          display: "flex", gap: 20, alignItems: "center", marginBottom: 20,
          fontSize: 13, color: C.textDim,
        }}>
          <span><span style={{ color: C.textHigh, fontWeight: 600 }}>{devices.length}</span> devices</span>
          {online  > 0 && <span><span style={{ color: C.green, fontWeight: 600 }}>{online}</span> online</span>}
          {offline > 0 && <span><span style={{ color: C.red,   fontWeight: 600 }}>{offline}</span> offline</span>}
          {lastRefresh && (
            <span style={{ marginLeft: "auto", fontSize: 11, fontFamily: FONT_MONO, color: C.textDim }}>
              {lastRefresh.toLocaleTimeString()}
            </span>
          )}
        </div>

        {/* Device list */}
        {devices.length === 0 && !backendErr ? (
          <div style={{
            padding: "48px 0", textAlign: "center",
            border: `1px dashed ${C.border}`, borderRadius: 8,
          }}>
            <p style={{ color: C.textMid, fontSize: 14, marginBottom: 6 }}>No devices found</p>
            <p style={{ color: C.textDim, fontSize: 12 }}>Is Docker running? Are Syncthing devices paired?</p>
          </div>
        ) : (
          devices.map(d => (
            <DroneCard
              key={d.id || d.deviceID}
              device={{ ...d, id: d.id || d.deviceID }}
              droneHistory={droneHistory}
              onUpdateHistory={updateDroneHistory}
              onRemove={removeDrone}
            />
          ))
        )}

        {/* Footer */}
        <div style={{
          marginTop: 32, paddingTop: 16, borderTop: `1px solid ${C.borderFaint}`,
          display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8,
          fontSize: 11, color: C.textDim, fontFamily: FONT_MONO,
        }}>
          <span>syncthing · 127.0.0.1:8384</span>
          <span>backend · localhost:8000</span>
        </div>
      </div>
    </div>
  );
}
