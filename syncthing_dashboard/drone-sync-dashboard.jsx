import { useState, useEffect, useRef } from "react";

// ─────────────────────────────────────────────────────────────────────────────
// CONFIG & DEFAULTS
// ─────────────────────────────────────────────────────────────────────────────
const MOCK_MODE = true;
const STORAGE_CONFIG_KEY  = "fleet-sync-config";
const STORAGE_DRONES_KEY  = "fleet-sync-drones";

const DEFAULT_CONFIG = {
  localSubnet : "192.168.1.0/24",
  sshUser     : "drone",
  sshKeysDir  : "/etc/fleet/keys",
  fieldServers: [],
};

// ─────────────────────────────────────────────────────────────────────────────
// MOCK DATA
// ─────────────────────────────────────────────────────────────────────────────
const MOCK_CONNECTIONS = {
  "AAAA-1111": { address:"192.168.1.45:22000", connected:true,  type:"tcp-client", inBytesTotal:1200000, outBytesTotal:400000 },
  "BBBB-2222": { address:"192.168.1.62:22000", connected:true,  type:"tcp-client", inBytesTotal:800000,  outBytesTotal:100000 },
  "CCCC-3333": { address:"relay://relay.syncthing.net/CCCC", connected:true, type:"relay", inBytesTotal:300000, outBytesTotal:50000 },
  "DDDD-4444": { address:"192.168.1.88:22000", connected:false, type:"tcp-client", inBytesTotal:0, outBytesTotal:0 },
};
const MOCK_DEVICES_CFG = [
  { deviceID:"AAAA-1111", name:"Drone Alpha-1" },
  { deviceID:"BBBB-2222", name:"Drone Beta-2"  },
  { deviceID:"CCCC-3333", name:"Drone Gamma-3" },
  { deviceID:"DDDD-4444", name:"Drone Delta-4" },
];
const MOCK_FOLDERS = {
  "AAAA-1111": [
    { name:"2025-06-10", sizeBytes:4831838208, files:312 },
    { name:"2025-06-08", sizeBytes:2147483648, files:187 },
    { name:"2025-05-30", sizeBytes:1073741824, files:95  },
    { name:"2025-05-22", sizeBytes:3221225472, files:241 },
  ],
  "BBBB-2222": [
    { name:"2025-06-09", sizeBytes:6442450944, files:502 },
    { name:"2025-06-07", sizeBytes:1610612736, files:133 },
    { name:"2025-05-28", sizeBytes:2684354560, files:198 },
  ],
  "CCCC-3333": [
    { name:"2025-06-05", sizeBytes:858993459,  files:71  },
    { name:"2025-05-18", sizeBytes:1932735283, files:155 },
  ],
  "DDDD-4444": [],
};
const MOCK_SYNC_PROGRESS = {
  "AAAA-1111": { "2025-06-08":100, "2025-06-10":54 },
  "BBBB-2222": {},
  "CCCC-3333": { "2025-06-05":100 },
  "DDDD-4444": {},
};

// ─────────────────────────────────────────────────────────────────────────────
// UTILS
// ─────────────────────────────────────────────────────────────────────────────
function fmtBytes(b) {
  if (!b) return "0 B";
  const u = ["B","KB","MB","GB","TB"];
  const i = Math.floor(Math.log(b)/Math.log(1024));
  return `${(b/Math.pow(1024,i)).toFixed(1)} ${u[i]}`;
}
function fmtRate(bps) {
  const mb = bps/1024/1024;
  return mb < 0.05 ? "—" : `${mb.toFixed(1)} MB/s`;
}
function ipInSubnet(address, subnet) {
  try {
    const ip = address.split(":")[0];
    const [net, bits] = subnet.split("/");
    const mask = ~((1<<(32-parseInt(bits)))-1);
    const toInt = s => s.split(".").reduce((a,b)=>(a<<8)|parseInt(b),0);
    return (toInt(ip) & mask) === (toInt(net) & mask);
  } catch { return false; }
}
function deriveStatus(conn, subnet) {
  if (!conn || !conn.connected) return "offline";
  if (conn.type === "relay") return "relay";
  if (subnet && ipInSubnet(conn.address, subnet)) return "local";
  return "wan";
}
const STATUS_META = {
  local  : { label:"LOCAL",   color:"#00ff88", pulse:true  },
  relay  : { label:"RELAY",   color:"#ffaa00", pulse:true  },
  wan    : { label:"WAN",     color:"#4488ff", pulse:true  },
  offline: { label:"OFFLINE", color:"#ff4444", pulse:false },
};

// Storage helpers
async function loadStorage(key, fallback) {
  try { const r = await window.storage.get(key); return r ? JSON.parse(r.value) : fallback; }
  catch { return fallback; }
}
async function saveStorage(key, value) {
  try { await window.storage.set(key, JSON.stringify(value)); } catch(e) { console.error(e); }
}

// ─────────────────────────────────────────────────────────────────────────────
// PRIMITIVE UI COMPONENTS
// ─────────────────────────────────────────────────────────────────────────────
function Mono({ children, color="#888", size=11 }) {
  return <span style={{ fontFamily:"'Fira Code',monospace", fontSize:size, color }}>{children}</span>;
}
function Tag({ children, color="#444" }) {
  return (
    <span style={{
      fontSize:9, letterSpacing:2, padding:"2px 6px", borderRadius:2,
      border:`1px solid ${color}`, color, fontFamily:"'Fira Code',monospace",
    }}>{children}</span>
  );
}
function Btn({ children, onClick, disabled, variant="default", small, fullWidth }) {
  const V = { default:{b:"#333",c:"#666"}, primary:{b:"#00ff88",c:"#00ff88"},
               warn:{b:"#ffaa00",c:"#ffaa00"}, danger:{b:"#ff4444",c:"#ff4444"},
               ghost:{b:"#222",c:"#444"} };
  const v = V[variant] || V.default;
  return (
    <button onClick={onClick} disabled={disabled} style={{
      fontFamily:"'Fira Code',monospace", fontSize:small?10:11, letterSpacing:2,
      padding:small?"4px 10px":"6px 14px", borderRadius:3,
      border:`1px solid ${disabled?"#222":v.b}`, background:"transparent",
      color:disabled?"#333":v.c, cursor:disabled?"default":"pointer",
      transition:"all 0.1s", whiteSpace:"nowrap",
      width:fullWidth?"100%":"auto",
    }}>{children}</button>
  );
}
function StatusDot({ status }) {
  const m = STATUS_META[status];
  return (
    <span style={{ display:"inline-flex", alignItems:"center", gap:6 }}>
      <span style={{
        width:7, height:7, borderRadius:"50%", background:m.color, display:"inline-block",
        boxShadow:m.pulse?`0 0 5px ${m.color}`:"none",
        animation:m.pulse?"pulse 2s ease-in-out infinite":"none",
      }}/>
      <Mono color={m.color} size={10}>{m.label}</Mono>
    </span>
  );
}
function ProgressBar({ value, color }) {
  const c = value===100 ? "#00ff88" : (color||"#ffaa00");
  return (
    <div style={{ height:2, background:"#1a1a1a", borderRadius:1, overflow:"hidden" }}>
      <div style={{ height:"100%", width:`${Math.min(value,100)}%`, background:c, transition:"width 0.4s" }}/>
    </div>
  );
}
function Input({ value, onChange, placeholder, mono, dim }) {
  return (
    <input value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder} style={{
      width:"100%", background:"#0a0a0a", border:`1px solid ${dim?"#1a1a1a":"#222"}`,
      borderRadius:3, padding:"6px 10px", color: dim?"#555":"#ccc",
      fontFamily:mono?"'Fira Code',monospace":"inherit", fontSize:11, outline:"none",
    }}/>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CODE BLOCK with copy
// ─────────────────────────────────────────────────────────────────────────────
function CodeBlock({ children }) {
  const [copied, setCopied] = useState(false);
  return (
    <div style={{ position:"relative", marginBottom:8 }}>
      <pre style={{
        background:"#080808", border:"1px solid #1c1c1c", borderRadius:4,
        padding:"10px 40px 10px 12px", margin:0, overflowX:"auto",
        fontFamily:"'Fira Code',monospace", fontSize:11, color:"#9a9a9a", lineHeight:1.75,
        whiteSpace:"pre-wrap", wordBreak:"break-all",
      }}>{children}</pre>
      <button onClick={()=>{ navigator.clipboard.writeText(children); setCopied(true); setTimeout(()=>setCopied(false),1500); }} style={{
        position:"absolute", top:6, right:6, background:"#111", border:"1px solid #222",
        borderRadius:3, padding:"2px 8px", fontFamily:"'Fira Code',monospace",
        fontSize:9, color:copied?"#00ff88":"#444", cursor:"pointer", letterSpacing:1,
      }}>{copied?"✓":"COPY"}</button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CAPTURED VALUE FIELD — shown after a step produces a value
// ─────────────────────────────────────────────────────────────────────────────
function CapturedValue({ label, value, onChange, placeholder, hint, verified }) {
  return (
    <div style={{
      marginTop:10, padding:"10px 12px", borderRadius:4,
      background:"rgba(0,255,136,0.03)", border:"1px solid rgba(0,255,136,0.1)",
    }}>
      <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:6 }}>
        <div style={{ fontSize:9, color:"#00ff88", letterSpacing:2, fontFamily:"'Fira Code',monospace" }}>
          ↳ {label}
        </div>
        {verified && <Tag color="#00ff88">VERIFIED</Tag>}
      </div>
      <input
        value={value}
        onChange={e=>onChange(e.target.value)}
        placeholder={placeholder}
        style={{
          width:"100%", background:"#050505", border:"1px solid rgba(0,255,136,0.15)",
          borderRadius:3, padding:"6px 10px", color:"#00ff88",
          fontFamily:"'Fira Code',monospace", fontSize:11, outline:"none",
        }}
      />
      {hint && <div style={{ fontSize:10, color:"#444", marginTop:5 }}>{hint}</div>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// VERIFY BUTTON — calls backend to confirm step
// ─────────────────────────────────────────────────────────────────────────────
function VerifyBtn({ label, onVerify, disabled, result }) {
  const [pending, setPending] = useState(false);

  async function run() {
    setPending(true);
    await onVerify();
    setPending(false);
  }

  const statusColor = result === "ok" ? "#00ff88" : result === "fail" ? "#ff4444" : "#ffaa00";
  const statusLabel = result === "ok" ? "✓ PASSED" : result === "fail" ? "✕ FAILED" : pending ? "CHECKING..." : `▶ ${label}`;

  return (
    <div style={{
      marginTop:10, display:"flex", alignItems:"center", gap:10,
      padding:"8px 12px", borderRadius:4,
      background: result==="ok"?"rgba(0,255,136,0.04)":result==="fail"?"rgba(255,68,68,0.04)":"rgba(255,255,255,0.02)",
      border:`1px solid ${result?"rgba(255,255,255,0.08)":"rgba(255,255,255,0.04)"}`,
    }}>
      <button
        onClick={run}
        disabled={disabled || pending || result==="ok"}
        style={{
          fontFamily:"'Fira Code',monospace", fontSize:10, letterSpacing:2,
          padding:"4px 12px", borderRadius:3,
          border:`1px solid ${disabled||pending?"#222":statusColor}`,
          background:"transparent", color:disabled?"#333":statusColor,
          cursor:disabled||result==="ok"?"default":"pointer", whiteSpace:"nowrap",
        }}
      >{statusLabel}</button>
      {result==="fail" && <Mono color="#555" size={10}>check terminal / backend logs</Mono>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// PROVISION MODAL
// ─────────────────────────────────────────────────────────────────────────────
function ProvisionModal({ config, onClose, onDroneAdded }) {
  // Fields filled in by user / captured from steps
  const [droneName,  setDroneName ] = useState("");
  const [droneIp,    setDroneIp   ] = useState("");
  const [pubKey,     setPubKey    ] = useState("");
  const [droneApiKey,setDroneApiKey] = useState("");
  const [droneDevId, setDroneDevId ] = useState("");
  const [fsSyncId,   setFsSyncId  ] = useState("");

  // Verify results per step
  const [vr, setVr] = useState({});
  function setV(step, result) { setVr(p=>({...p,[step]:result})); }

  const sshUser   = config.sshUser   || "drone";
  const keysDir   = config.sshKeysDir || "/etc/fleet/keys";
  const safeName  = droneName.replace(/\s+/g,"-").toLowerCase() || "<drone-name>";
  const keyDir    = `${keysDir}/${safeName}`;
  const keyPath   = `${keyDir}/id_ed25519`;
  const ip        = droneIp   || "<DRONE_IP>";
  const apiKey    = droneApiKey || "<DRONE_API_KEY>";
  const devId     = droneDevId  || "<DRONE_DEVICE_ID>";
  const fsId      = fsSyncId    || "<FIELD_SERVER_DEVICE_ID>";

  // Mock verify calls — in real impl these POST to your Flask backend
  async function verify(step) {
    await new Promise(r=>setTimeout(r, MOCK_MODE?700:2000));
    // real: const res = await fetch(`/api/provision/verify/${step}`, { method:"POST", body: JSON.stringify({...}) })
    const mockResults = { ssh:"ok", tunnel:"ok", apikey:"ok", deviceid:"ok", folder: droneDevId?"ok":"fail" };
    setV(step, mockResults[step] || "ok");
    // If step returned a value, mock populate it
    if (step==="apikey" && !droneApiKey) setDroneApiKey("abc123-mock-api-key-xyz");
    if (step==="deviceid" && !droneDevId) setDroneDevId("NEWDR-ONEVIC-EIDED-XAMPLE-TESTID-FORMAT-DEVICE-001X");
    if (step==="fsid" && !fsSyncId) setFsSyncId("SERV1-DFIELD-XXXXXX-YYYYYY-ZZZZZZ-AAAAAA-BBBBBB-CCC001");
  }

  const hasName = droneName.trim().length > 0;
  const hasIp   = droneIp.trim().length > 0;

  return (
    <div style={{
      position:"fixed", inset:0, background:"rgba(0,0,0,0.88)",
      display:"flex", alignItems:"center", justifyContent:"center",
      zIndex:100, padding:24,
    }} onClick={onClose}>
      <div onClick={e=>e.stopPropagation()} style={{
        background:"#0c0c0c", border:"1px solid #222", borderRadius:8,
        width:"100%", maxWidth:700, maxHeight:"90vh", overflowY:"auto", padding:28,
      }}>
        {/* Header */}
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:24 }}>
          <div>
            <Mono size={14} color="#e0e0e0">CONNECT NEW DRONE</Mono>
            <div style={{ fontSize:11, color:"#444", marginTop:4 }}>
              Fill name + IP first — commands below update as you go.
            </div>
          </div>
          <Btn onClick={onClose} small>✕</Btn>
        </div>

        {/* Name + IP — needed to parameterise everything */}
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginBottom:24 }}>
          <div>
            <div style={{ fontSize:9, color:"#444", letterSpacing:2, marginBottom:5, fontFamily:"'Fira Code',monospace" }}>DRONE NAME *</div>
            <Input value={droneName} onChange={setDroneName} placeholder="Charlie-5" />
          </div>
          <div>
            <div style={{ fontSize:9, color:"#444", letterSpacing:2, marginBottom:5, fontFamily:"'Fira Code',monospace" }}>DRONE IP (local) *</div>
            <Input value={droneIp} onChange={setDroneIp} placeholder="192.168.1.77" />
          </div>
        </div>

        {/* ── STEP 1 ── */}
        <StepBlock n="1" label="GENERATE SSH KEY FOR THIS DRONE" complete={!!pubKey}>
          <div style={{ fontSize:11, color:"#555", marginBottom:8 }}>
            Creates a dedicated keypair scoped to this drone under <Mono color="#666">{keyDir}/</Mono>
          </div>
          <CodeBlock>{`mkdir -p ${keyDir}
ssh-keygen -t ed25519 -f ${keyPath} -N "" -C "fleet-${safeName}"
cat ${keyPath}.pub`}</CodeBlock>
          <CapturedValue
            label="PUBLIC KEY (paste output of cat above)"
            value={pubKey}
            onChange={setPubKey}
            placeholder="ssh-ed25519 AAAAC3Nza..."
            hint="Paste the full line. Used in step 2."
          />
        </StepBlock>

        {/* ── STEP 2 ── */}
        <StepBlock n="2" label="INSTALL KEY ON DRONE" complete={vr.ssh==="ok"} disabled={!pubKey||!hasIp}>
          <div style={{ fontSize:11, color:"#555", marginBottom:8 }}>
            Copy key to drone. Requires temporary password auth or physical access.
          </div>
          <CodeBlock>{`ssh-copy-id -i ${keyPath}.pub ${sshUser}@${ip}
# or manually:
ssh ${sshUser}@${ip} "mkdir -p ~/.ssh && echo '${pubKey||"<paste pub key>"}' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"`}</CodeBlock>
          <VerifyBtn
            label="VERIFY SSH ACCESS"
            disabled={!pubKey || !hasIp}
            result={vr.ssh}
            onVerify={()=>verify("ssh")}
          />
        </StepBlock>

        {/* ── STEP 3 ── */}
        <StepBlock n="3" label="RETRIEVE DRONE API KEY" complete={!!droneApiKey} disabled={vr.ssh!=="ok"}>
          <div style={{ fontSize:11, color:"#555", marginBottom:8 }}>
            Pull the API key from the drone's Syncthing config over SSH.
          </div>
          <CodeBlock>{`ssh -i ${keyPath} ${sshUser}@${ip} \\
  "grep -oP '(?<=<apikey>)[^<]+' ~/.config/syncthing/config.xml"`}</CodeBlock>
          <VerifyBtn
            label="FETCH API KEY"
            disabled={vr.ssh!=="ok"}
            result={vr.apikey}
            onVerify={()=>verify("apikey")}
          />
          <CapturedValue
            label="DRONE API KEY (auto-filled on verify, or paste manually)"
            value={droneApiKey}
            onChange={setDroneApiKey}
            placeholder="abc123xyz..."
            verified={vr.apikey==="ok"}
          />
        </StepBlock>

        {/* ── STEP 4 ── */}
        <StepBlock n="4" label="OPEN TEST TUNNEL + GET DEVICE ID" complete={!!droneDevId} disabled={!droneApiKey||!hasIp}>
          <div style={{ fontSize:11, color:"#555", marginBottom:8 }}>
            Open a temporary tunnel to verify API access and retrieve the drone's Syncthing device ID.
          </div>
          <CodeBlock>{`ssh -i ${keyPath} -N -L 19384:127.0.0.1:8384 ${sshUser}@${ip} &
TUNNEL_PID=$!

curl -s http://127.0.0.1:19384/rest/system/status \\
  -H "X-API-Key: ${apiKey}" | python3 -m json.tool | grep myID

kill $TUNNEL_PID`}</CodeBlock>
          <VerifyBtn
            label="VERIFY TUNNEL + FETCH DEVICE ID"
            disabled={!droneApiKey || !hasIp}
            result={vr.deviceid}
            onVerify={()=>verify("deviceid")}
          />
          <CapturedValue
            label="DRONE DEVICE ID (auto-filled on verify, or paste manually)"
            value={droneDevId}
            onChange={setDroneDevId}
            placeholder="XXXXXXX-XXXXXXX-XXXXXXX-..."
            verified={vr.deviceid==="ok"}
          />
        </StepBlock>

        {/* ── STEP 5 ── */}
        <StepBlock n="5" label="GET FIELD SERVER DEVICE ID" complete={!!fsSyncId} disabled={!droneApiKey}>
          <div style={{ fontSize:11, color:"#555", marginBottom:8 }}>
            Needed so the drone knows who to accept the folder share from.
          </div>
          <CodeBlock>{`curl -s http://127.0.0.1:8384/rest/system/status \\
  -H "X-API-Key: ${config.syncthingApiKey||"<SERVER_API_KEY>"}" \\
  | python3 -m json.tool | grep myID`}</CodeBlock>
          <VerifyBtn
            label="FETCH FROM LOCAL SYNCTHING"
            disabled={!droneApiKey}
            result={vr.fsid}
            onVerify={()=>verify("fsid")}
          />
          <CapturedValue
            label="FIELD SERVER DEVICE ID"
            value={fsSyncId}
            onChange={setFsSyncId}
            placeholder="XXXXXXX-XXXXXXX-XXXXXXX-..."
            verified={vr.fsid==="ok"}
          />
        </StepBlock>

        {/* ── STEP 6 ── */}
        <StepBlock n="6" label="PAIR DEVICES IN SYNCTHING" complete={vr.folder==="ok"} disabled={!droneDevId||!fsSyncId}>
          <div style={{ fontSize:11, color:"#555", marginBottom:8 }}>
            Add the drone to this server's Syncthing and share the organised folder. Then add server to drone.
          </div>
          <CodeBlock>{`# On field server — add drone as a device
curl -s -X POST http://127.0.0.1:8384/rest/config/devices \\
  -H "X-API-Key: ${config.syncthingApiKey||"<SERVER_API_KEY>"}" \\
  -H "Content-Type: application/json" \\
  -d '{"deviceID":"${devId}","name":"${droneName||"<drone-name>"}","addresses":["dynamic"]}'

# On drone (via tunnel) — add field server
curl -s -X POST http://127.0.0.1:19384/rest/config/devices \\
  -H "X-API-Key: ${apiKey}" \\
  -H "Content-Type: application/json" \\
  -d '{"deviceID":"${fsId}","name":"field-server","addresses":["dynamic"]}'`}</CodeBlock>
          <VerifyBtn
            label="VERIFY DEVICES PAIRED"
            disabled={!droneDevId||!fsSyncId}
            result={vr.folder}
            onVerify={()=>verify("folder")}
          />
        </StepBlock>

        {/* ── STEP 7 ── */}
        <StepBlock n="7" label="SHARE ORGANISED FOLDER" complete={vr.share==="ok"} disabled={vr.folder!=="ok"}>
          <div style={{ fontSize:11, color:"#555", marginBottom:8 }}>
            Share the organised folder from the field server with the drone.
            The drone needs to accept — trigger via API or wait for GUI prompt.
          </div>
          <CodeBlock>{`# On field server — PATCH organised folder to include drone
# Get current folder config first
curl -s http://127.0.0.1:8384/rest/config/folders/organised \\
  -H "X-API-Key: ${config.syncthingApiKey||"<SERVER_API_KEY>"}" > /tmp/folder.json

# Add drone deviceID to devices array, then PATCH back
# (edit /tmp/folder.json to add {"deviceID":"${devId}"} to devices[])

curl -s -X PATCH http://127.0.0.1:8384/rest/config/folders/organised \\
  -H "X-API-Key: ${config.syncthingApiKey||"<SERVER_API_KEY>"}" \\
  -H "Content-Type: application/json" \\
  -d @/tmp/folder.json

# Accept on drone (via tunnel on port 19384)
curl -s -X POST http://127.0.0.1:19384/rest/config/folders \\
  -H "X-API-Key: ${apiKey}" \\
  -H "Content-Type: application/json" \\
  -d '{"id":"organised","label":"Organised","path":"/home/${sshUser}/organised","type":"sendreceive","devices":[{"deviceID":"${fsId}"}]}'`}</CodeBlock>
          <VerifyBtn
            label="VERIFY FOLDER SHARED"
            disabled={vr.folder!=="ok"}
            result={vr.share}
            onVerify={()=>verify("share")}
          />
        </StepBlock>

        {/* Register button */}
        <div style={{
          marginTop:20, paddingTop:16, borderTop:"1px solid #1a1a1a",
          display:"flex", justifyContent:"space-between", alignItems:"center",
        }}>
          <div style={{ fontSize:11, color:"#444" }}>
            {droneDevId ? <Mono color="#555">{droneDevId.slice(0,24)}...</Mono> : <Mono color="#333">complete steps to register</Mono>}
          </div>
          <Btn
            variant={droneDevId && droneName ? "primary" : "default"}
            disabled={!droneDevId || !droneName || !droneApiKey}
            onClick={()=>{
              onDroneAdded({ id:droneDevId, name:droneName, apiKey:droneApiKey, keyPath, sshUser, addedAt:Date.now() });
              onClose();
            }}
          >
            + REGISTER DRONE
          </Btn>
        </div>

      </div>
    </div>
  );
}

// Step wrapper with visual numbering + completion state
function StepBlock({ n, label, children, complete, disabled }) {
  return (
    <div style={{
      marginBottom:20,
      opacity: disabled ? 0.4 : 1,
      pointerEvents: disabled ? "none" : "auto",
      transition:"opacity 0.2s",
    }}>
      <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:8 }}>
        <div style={{
          width:20, height:20, borderRadius:"50%", flexShrink:0,
          border:`1px solid ${complete?"#00ff88":"#2a2a2a"}`,
          background: complete?"rgba(0,255,136,0.1)":"transparent",
          display:"flex", alignItems:"center", justifyContent:"center",
          fontFamily:"'Fira Code',monospace", fontSize:10, color:complete?"#00ff88":"#444",
        }}>{complete ? "✓" : n}</div>
        <div style={{ fontSize:9, color:complete?"#00ff88":"#555", letterSpacing:2, fontFamily:"'Fira Code',monospace" }}>
          {label}
        </div>
      </div>
      <div style={{ marginLeft:28 }}>{children}</div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SETTINGS PANEL
// ─────────────────────────────────────────────────────────────────────────────
function SettingsPanel({ config, onSave, onClose }) {
  const [local, setLocal] = useState({...config});
  const [newFs, setNewFs] = useState({ name:"", tailscaleIp:"", apiKey:"" });
  function upd(k,v) { setLocal(p=>({...p,[k]:v})); }
  function addFs() {
    if (!newFs.name||!newFs.tailscaleIp) return;
    setLocal(p=>({...p, fieldServers:[...(p.fieldServers||[]),{...newFs}]}));
    setNewFs({name:"",tailscaleIp:"",apiKey:""});
  }
  return (
    <div style={{
      position:"fixed", inset:0, background:"rgba(0,0,0,0.88)",
      display:"flex", alignItems:"center", justifyContent:"center",
      zIndex:100, padding:24,
    }} onClick={onClose}>
      <div onClick={e=>e.stopPropagation()} style={{
        background:"#0c0c0c", border:"1px solid #222", borderRadius:8,
        width:"100%", maxWidth:540, maxHeight:"85vh", overflowY:"auto", padding:28,
      }}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:24 }}>
          <Mono size={13} color="#e0e0e0">SETTINGS</Mono>
          <Btn onClick={onClose} small>✕</Btn>
        </div>
        {[
          { key:"localSubnet",      label:"LOCAL OFFICE SUBNET",    hint:"Drones with IPs in this range show CONNECT button", ph:"192.168.1.0/24" },
          { key:"sshUser",          label:"DRONE SSH USER",          hint:"Username on drone OS",                              ph:"drone"          },
          { key:"sshKeysDir",       label:"SSH KEYS BASE DIRECTORY", hint:"Per-drone keys stored here under /<drone-name>/",  ph:"/etc/fleet/keys" },
          { key:"syncthingApiKey",  label:"LOCAL SYNCTHING API KEY", hint:"This server's Syncthing API key",                  ph:"your-api-key",  mono:true },
        ].map(f=>(
          <div key={f.key} style={{ marginBottom:16 }}>
            <div style={{ fontSize:9, color:"#444", letterSpacing:2, marginBottom:3, fontFamily:"'Fira Code',monospace" }}>{f.label}</div>
            <div style={{ fontSize:10, color:"#333", marginBottom:5 }}>{f.hint}</div>
            <Input value={local[f.key]||""} onChange={v=>upd(f.key,v)} placeholder={f.ph} mono={f.mono} />
          </div>
        ))}

        <div style={{ fontSize:9, color:"#444", letterSpacing:2, marginBottom:8, fontFamily:"'Fira Code',monospace" }}>FIELD SERVERS (TAILSCALE)</div>
        {(local.fieldServers||[]).map((fs,i)=>(
          <div key={i} style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr auto", gap:8, marginBottom:6, alignItems:"center" }}>
            <Mono color="#777">{fs.name}</Mono>
            <Mono color="#555">{fs.tailscaleIp}</Mono>
            <Mono color="#444">{fs.apiKey?"key set":"no key"}</Mono>
            <Btn onClick={()=>setLocal(p=>({...p,fieldServers:p.fieldServers.filter((_,j)=>j!==i)}))} small variant="danger">✕</Btn>
          </div>
        ))}
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr auto", gap:8, marginBottom:20 }}>
          {[
            {v:newFs.name,     f:"name",       ph:"FS-01"      },
            {v:newFs.tailscaleIp,f:"tailscaleIp",ph:"100.64.0.5"},
            {v:newFs.apiKey,   f:"apiKey",     ph:"api key"    },
          ].map(({v,f,ph})=>(
            <input key={f} value={v} onChange={e=>setNewFs(p=>({...p,[f]:e.target.value}))} placeholder={ph} style={{
              background:"#0a0a0a", border:"1px solid #222", borderRadius:3,
              padding:"6px 8px", color:"#ccc", fontFamily:"'Fira Code',monospace", fontSize:11, outline:"none",
            }}/>
          ))}
          <Btn onClick={addFs} small variant="primary">ADD</Btn>
        </div>
        <div style={{ display:"flex", justifyContent:"flex-end", gap:8 }}>
          <Btn onClick={onClose}>CANCEL</Btn>
          <Btn onClick={()=>{ onSave(local); onClose(); }} variant="primary">SAVE</Btn>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// DATE ROW
// ─────────────────────────────────────────────────────────────────────────────
function DateRow({ date, size, files, selected, progress, onToggle, browsable }) {
  const done = progress===100;
  const syncing = selected && progress!==undefined && progress<100;
  return (
    <div onClick={()=>!done&&onToggle(date)} style={{
      display:"grid", gridTemplateColumns:"18px 1fr 80px 55px 65px",
      alignItems:"center", gap:10, padding:"7px 10px", borderRadius:3,
      cursor:done?"default":"pointer",
      background:selected?"rgba(0,255,136,0.03)":"transparent",
      border:`1px solid ${selected?"rgba(0,255,136,0.12)":"rgba(255,255,255,0.03)"}`,
      marginBottom:3, opacity:done?0.5:1, transition:"all 0.1s",
    }}>
      <div style={{
        width:13, height:13, border:`1px solid ${selected?"#00ff88":"#333"}`,
        borderRadius:2, background:selected?"#00ff88":"transparent",
        display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0,
      }}>
        {selected&&<svg width="7" height="5" viewBox="0 0 7 5"><path d="M1 2.5L2.8 4.2L6 1" stroke="#000" strokeWidth="1.4" strokeLinecap="round" fill="none"/></svg>}
      </div>
      <div>
        <Mono size={12} color={done?"#555":"#ccc"}>
          {date}{done&&<span style={{marginLeft:8,color:"#00ff88",fontSize:9}}>✓</span>}
        </Mono>
        {syncing&&<div style={{marginTop:3}}><ProgressBar value={progress}/></div>}
      </div>
      <Mono color="#555">{browsable?fmtBytes(size):"—"}</Mono>
      <Mono color="#444">{browsable?`${files}f`:"—"}</Mono>
      <Mono color={syncing?"#ffaa00":"#333"}>{syncing?`${progress}%`:selected&&!done?"QUEUED":"—"}</Mono>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// DRONE CARD
// ─────────────────────────────────────────────────────────────────────────────
const tunnelState = {};

function DroneCard({ device, config, droneHistory, onUpdateHistory }) {
  const [expanded,      setExpanded     ] = useState(false);
  const [selected,      setSelected     ] = useState(new Set(droneHistory[device.id]?.selectedDates||[]));
  const [tunnelOpen,    setTunnelOpen   ] = useState(!!tunnelState[device.id]);
  const [tunnelPending, setTunnelPending] = useState(false);
  const [applying,      setApplying     ] = useState(false);

  const stored     = droneHistory[device.id] || {};
  const status     = device.status;
  const canBrowse  = (status==="local"&&tunnelOpen) || status==="relay";
  const canConnect = status==="local" && !tunnelOpen;
  const dates      = device.folders || [];

  const totalSelected = [...selected].reduce((acc,d)=>{
    const f = dates.find(x=>x.name===d);
    return acc+(f?f.sizeBytes:0);
  }, 0);

  const hasChanges = JSON.stringify([...selected].sort()) !==
    JSON.stringify([...(stored.selectedDates||[])].sort());

  function toggleDate(d) {
    setSelected(prev=>{ const n=new Set(prev); n.has(d)?n.delete(d):n.add(d); return n; });
  }

  async function openTunnel() {
    setTunnelPending(true);
    // real: POST /api/tunnel/open { deviceId, droneIp, keyPath, sshUser }
    await new Promise(r=>setTimeout(r,800));
    tunnelState[device.id]=true;
    setTunnelOpen(true);
    setTunnelPending(false);
  }

  async function applySync() {
    setApplying(true);
    await new Promise(r=>setTimeout(r,600));
    onUpdateHistory(device.id, {...stored, selectedDates:[...selected]});
    setApplying(false);
  }

  return (
    <div style={{
      border:"1px solid rgba(255,255,255,0.06)", borderRadius:6, overflow:"hidden",
      background:"rgba(255,255,255,0.01)", marginBottom:10,
    }}>
      {/* Header */}
      <div onClick={()=>setExpanded(v=>!v)} style={{
        display:"grid", gridTemplateColumns:"1fr auto auto auto auto",
        alignItems:"center", gap:12, padding:"12px 16px", cursor:"pointer",
        borderBottom:expanded?"1px solid rgba(255,255,255,0.05)":"none",
      }}>
        <div>
          <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:3 }}>
            <Mono size={12} color="#ddd">{device.name}</Mono>
            {tunnelOpen && <Tag color="#00ff88">TUNNEL OPEN</Tag>}
            {stored.keyPath && <Tag color="#333">KEY SET</Tag>}
          </div>
          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
            <StatusDot status={status}/>
            {device.address && <Mono color="#2e2e2e" size={10}>{device.address}</Mono>}
          </div>
        </div>

        <div style={{ textAlign:"right" }}>
          <div><Mono color="#00ff88" size={10}>↓ {fmtRate(device.inBps||0)}</Mono></div>
          <div><Mono color="#444"    size={10}>↑ {fmtRate(device.outBps||0)}</Mono></div>
        </div>

        <div onClick={e=>e.stopPropagation()}>
          {canConnect && (
            <Btn onClick={openTunnel} disabled={tunnelPending} variant="primary" small>
              {tunnelPending?"CONNECTING...":"⇄ CONNECT"}
            </Btn>
          )}
          {tunnelOpen && (
            <Btn onClick={()=>{ tunnelState[device.id]=false; setTunnelOpen(false); }} variant="warn" small>
              DISCONNECT
            </Btn>
          )}
          {status==="relay"   && <Tag color="#ffaa00">RELAY</Tag>}
          {status==="wan"     && <Tag color="#4488ff">WAN</Tag>}
          {status==="offline" && <Tag>OFFLINE</Tag>}
        </div>

        <Mono color="#333" size={10}>{dates.length} FOLDERS</Mono>
        <div style={{ color:"#2a2a2a", fontSize:11, transform:expanded?"rotate(180deg)":"none", transition:"transform 0.2s" }}>▼</div>
      </div>

      {/* Expanded body */}
      {expanded && (
        <div style={{ padding:"12px 16px 14px" }}>
          {status==="local"&&!tunnelOpen && (
            <div style={{
              padding:"9px 12px", marginBottom:10, borderRadius:3,
              background:"rgba(0,255,136,0.03)", border:"1px solid rgba(0,255,136,0.08)",
              fontSize:11, color:"#666",
            }}>Drone detected on local subnet. Open tunnel to browse date folders.</div>
          )}
          {status==="offline" && (
            <div style={{
              padding:"9px 12px", marginBottom:10, borderRadius:3,
              background:"rgba(255,68,68,0.03)", border:"1px solid rgba(255,68,68,0.08)",
              fontSize:11, color:"#555",
            }}>Offline. Showing last known state.</div>
          )}

          {dates.length>0 ? (
            <>
              <div style={{ display:"grid", gridTemplateColumns:"18px 1fr 80px 55px 65px", gap:10, padding:"0 10px", marginBottom:6 }}>
                {["","DATE","SIZE","FILES","STATUS"].map(h=>(
                  <div key={h} style={{ fontSize:9, color:"#2a2a2a", letterSpacing:2, textAlign:h==="DATE"?"left":"right", fontFamily:"'Fira Code',monospace" }}>{h}</div>
                ))}
              </div>
              {dates.map(d=>(
                <DateRow
                  key={d.name} date={d.name} size={d.sizeBytes} files={d.files}
                  selected={selected.has(d.name)} progress={device.syncProgress?.[d.name]}
                  browsable={canBrowse||status==="offline"} onToggle={toggleDate}
                />
              ))}
              <div style={{ marginTop:10, display:"flex", alignItems:"center", justifyContent:"space-between", borderTop:"1px solid rgba(255,255,255,0.04)", paddingTop:10 }}>
                <div>
                  {selected.size>0 && (
                    <Mono color="#555">
                      {selected.size} selected
                      {canBrowse && <span style={{ marginLeft:8, color:"#00ff88" }}>{fmtBytes(totalSelected)}</span>}
                    </Mono>
                  )}
                </div>
                <Btn onClick={applySync} disabled={!hasChanges||applying} variant={hasChanges?"primary":"default"}>
                  {applying?"APPLYING...":"APPLY SYNC"}
                </Btn>
              </div>
            </>
          ) : (
            <Mono color="#333">No date folders found.</Mono>
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
  const [config,       setConfig      ] = useState(DEFAULT_CONFIG);
  const [droneHistory, setDroneHistory] = useState({});
  const [devices,      setDevices     ] = useState([]);
  const [loaded,       setLoaded      ] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showProvision,setShowProvision] = useState(false);
  const [refreshing,   setRefreshing  ] = useState(false);
  const [lastRefresh,  setLastRefresh ] = useState(null);

  useEffect(()=>{
    async function load() {
      const cfg  = await loadStorage(STORAGE_CONFIG_KEY,  DEFAULT_CONFIG);
      const hist = await loadStorage(STORAGE_DRONES_KEY,  {});
      setConfig(cfg); setDroneHistory(hist); setLoaded(true);
    }
    load();
  },[]);

  useEffect(()=>{ if(loaded) fetchDevices(); },[loaded]);

  async function fetchDevices() {
    setRefreshing(true);
    if (MOCK_MODE) {
      await new Promise(r=>setTimeout(r,400));
      setDevices(MOCK_DEVICES_CFG.map(d=>{
        const conn = MOCK_CONNECTIONS[d.deviceID];
        return {
          id:d.deviceID,
          name:droneHistory[d.deviceID]?.name || d.name,
          status:deriveStatus(conn, config.localSubnet),
          address:conn?.address||"",
          inBps:conn?(conn.inBytesTotal/1000):0,
          outBps:conn?(conn.outBytesTotal/10000):0,
          folders:MOCK_FOLDERS[d.deviceID]||[],
          syncProgress:MOCK_SYNC_PROGRESS[d.deviceID]||{},
        };
      }));
    }
    setLastRefresh(new Date()); setRefreshing(false);
  }

  async function saveConfig(cfg) {
    setConfig(cfg); await saveStorage(STORAGE_CONFIG_KEY, cfg);
  }

  async function updateDroneHistory(id, data) {
    const next = {...droneHistory,[id]:data};
    setDroneHistory(next); await saveStorage(STORAGE_DRONES_KEY, next);
  }

  async function registerDrone(drone) {
    // drone = { id, name, apiKey, keyPath, sshUser, addedAt }
    const next = { ...droneHistory, [drone.id]: { ...droneHistory[drone.id], ...drone, selectedDates:[] }};
    setDroneHistory(next); await saveStorage(STORAGE_DRONES_KEY, next);
    fetchDevices();
  }

  if (!loaded) return (
    <div style={{ minHeight:"100vh", background:"#0a0a0a", display:"flex", alignItems:"center", justifyContent:"center" }}>
      <Mono color="#2a2a2a" size={11}>LOADING...</Mono>
    </div>
  );

  const counts = {
    total:devices.length,
    local:devices.filter(d=>d.status==="local").length,
    relay:devices.filter(d=>d.status==="relay"||d.status==="wan").length,
    offline:devices.filter(d=>d.status==="offline").length,
  };

  return (
    <div style={{ minHeight:"100vh", background:"#0a0a0a", color:"#e0e0e0", padding:24, maxWidth:900, margin:"0 auto" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;700&family=DM+Sans:wght@300;400&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.3}}
        input{outline:none;}
        input::placeholder{color:#2a2a2a;}
        ::-webkit-scrollbar{width:3px;}
        ::-webkit-scrollbar-thumb{background:#1e1e1e;}
      `}</style>

      {showSettings  && <SettingsPanel  config={config} onSave={saveConfig} onClose={()=>setShowSettings(false)}/>}
      {showProvision && <ProvisionModal config={config} onClose={()=>setShowProvision(false)} onDroneAdded={registerDrone}/>}

      {/* Header */}
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:28, paddingBottom:18, borderBottom:"1px solid rgba(255,255,255,0.04)" }}>
        <div>
          <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:3 }}>
            <Mono size={15} color="#fff">FLEET SYNC</Mono>
            <Tag color="#2a2a2a">SYNCTHING</Tag>
            {MOCK_MODE && <Tag color="#ffaa00">MOCK</Tag>}
          </div>
          <Mono color="#2e2e2e" size={10}>DRONE LOG SYNCHRONISATION</Mono>
        </div>
        <div style={{ display:"flex", gap:8 }}>
          <Btn onClick={()=>setShowProvision(true)} variant="primary" small>+ NEW DRONE</Btn>
          <Btn onClick={()=>setShowSettings(true)} small>⚙ SETTINGS</Btn>
          <Btn onClick={fetchDevices} disabled={refreshing} small>{refreshing?"...":"↻"}</Btn>
        </div>
      </div>

      {/* Stats */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:10, marginBottom:22 }}>
        {[
          {label:"TOTAL",    value:counts.total,   color:"#555"  },
          {label:"LOCAL",    value:counts.local,   color:"#00ff88"},
          {label:"RELAY/WAN",value:counts.relay,   color:"#ffaa00"},
          {label:"OFFLINE",  value:counts.offline, color:"#ff4444"},
        ].map(s=>(
          <div key={s.label} style={{ border:"1px solid rgba(255,255,255,0.04)", borderRadius:5, padding:"10px 14px", background:"rgba(255,255,255,0.01)" }}>
            <div style={{ fontSize:8, color:"#2a2a2a", letterSpacing:2, marginBottom:5, fontFamily:"'Fira Code',monospace" }}>{s.label}</div>
            <div style={{ fontFamily:"'Fira Code',monospace", fontSize:22, color:s.value>0?s.color:"#2a2a2a" }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Config bar */}
      <div style={{ marginBottom:14, display:"flex", alignItems:"center", gap:8, flexWrap:"wrap", fontSize:9, color:"#2a2a2a", fontFamily:"'Fira Code',monospace", letterSpacing:1 }}>
        <span>SUBNET</span>
        <span style={{ color:"#383838", background:"#111", padding:"2px 8px", borderRadius:2 }}>{config.localSubnet||"not set"}</span>
        <span style={{ color:"#1e1e1e" }}>·</span>
        <span>KEYS</span>
        <span style={{ color:"#383838", background:"#111", padding:"2px 8px", borderRadius:2 }}>{config.sshKeysDir||"not set"}</span>
        {lastRefresh && <>
          <span style={{ color:"#1e1e1e" }}>·</span>
          <span style={{ color:"#1e1e1e" }}>{lastRefresh.toLocaleTimeString()}</span>
        </>}
      </div>

      {/* Divider */}
      <div style={{ fontSize:8, letterSpacing:3, color:"#1e1e1e", marginBottom:10, display:"flex", alignItems:"center", gap:10, fontFamily:"'Fira Code',monospace" }}>
        <span>DEVICES</span>
        <div style={{ flex:1, height:1, background:"rgba(255,255,255,0.025)" }}/>
        <span>EXPAND · SELECT DATES · APPLY</span>
      </div>

      {devices.length===0 ? (
        <div style={{ padding:"40px 0", textAlign:"center" }}>
          <Mono color="#2a2a2a" size={12}>NO DEVICES — configure API key in settings</Mono>
        </div>
      ) : devices.map(d=>(
        <DroneCard
          key={d.id} device={d} config={config}
          droneHistory={droneHistory} onUpdateHistory={updateDroneHistory}
        />
      ))}

      {/* Footer */}
      <div style={{ marginTop:28, paddingTop:14, borderTop:"1px solid rgba(255,255,255,0.025)", display:"flex", justifyContent:"space-between", fontSize:9, color:"#1e1e1e", fontFamily:"'Fira Code',monospace", letterSpacing:1 }}>
        <span>SYNCTHING REST · 127.0.0.1:8384</span>
        <span>/rest/config/folders · ignore patterns</span>
      </div>
    </div>
  );
}
