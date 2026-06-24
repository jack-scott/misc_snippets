# Syncthing API — Learnings from Quick Experiment

## Auth & CORS

- Every request needs `X-API-Key: {key}` header. Find it in Syncthing web UI → Actions → Settings.
- For a browser dashboard making cross-origin requests, Syncthing needs `insecureSkipHostcheck: true` in `config.xml`:
  ```xml
  <gui>
    <address>0.0.0.0:8384</address>
    <insecureSkipHostcheck>true</insecureSkipHostcheck>
  </gui>
  ```
  Or patch via API:
  ```bash
  curl -X PATCH http://{ip}:8384/rest/config/gui \
    -H "X-API-Key: {key}" -H "Content-Type: application/json" \
    -d '{"insecureSkipHostcheck": true}'
  ```
- Dashboard must be served over HTTP — `fetch` does not work from `file://` origins.

---

## Key Endpoints

| Purpose | Method | Endpoint |
|---|---|---|
| Device ID, uptime, memory | GET | `/system/status` |
| All peer connections | GET | `/system/connections` |
| Full config (folders, devices) | GET | `/config` |
| Folder sync state | GET | `/db/status?folder={id}` |
| Local completion for folder | GET | `/db/completion?folder={id}` |
| Peer's completion for folder | GET | `/db/completion?folder={id}&device={deviceId}` |
| Browse filesystem dirs | GET | `/system/browse?current={path}` |
| Pause/resume folder | PATCH | `/config/folders/{id}` → `{"paused": true/false}` |
| Trigger folder scan | POST | `/db/scan?folder={id}` |
| Add new folder | POST | `/config/folders` |
| Pause all sync | POST | `/system/pause` |
| Resume all sync | POST | `/system/resume` |

---

## Completion Accuracy — The Main Gotcha

`/db/completion?folder={id}` without a device returns **local** completion — how much of the global index the local device has. For a `sendonly` folder this is always ~100%, because the local device has all its own files regardless of whether any peer has received anything. This makes it look fully synced when it isn't.

**Correct approach by folder type:**

- `sendonly` — query `/db/completion?folder={id}&device={deviceId}` for each peer device. Use worst-case peer (minimum completion, maximum needBytes) as the displayed value.
- `receiveonly` / `sendreceive` — no-device completion is accurate (shows how much local still needs to pull).

Also: `globalBytes` from `/db/status` is `0` if a folder was added paused before its first scan. Don't compute a percentage from it — use the `/db/completion` endpoint instead.

---

## Paused Folder Behaviour

- Paused folders do not rescan. If a folder is added as paused before ever syncing, the index is empty and all byte/file counts are 0.
- Per-peer completion (`/db/completion?folder={id}&device={deviceId}`) still reflects the last known index state — it is the most reliable progress metric regardless of pause state.
- The `paused` flag comes from the folder config (`GET /config` → `folders[].paused`), not from `db/status`. The state field in `db/status` shows `idle` even when paused.

---

## Setting Up a Two-Way Sync Programmatically

1. **Devices must be paired first.** There is no API shortcut — initial device pairing has to go through each instance's Syncthing web UI.
2. **Folder ID must be identical on both instances.** That is how Syncthing matches them up. If the IDs differ, the two folders will never connect.
3. POST to the sender instance: `type: sendonly`, include the receiver's device ID in `devices[]`.
4. POST to the receiver instance: same folder ID, `type: receiveonly`, include the sender's device ID in `devices[]`.
5. Get a device's ID from `GET /system/status` → `myID`.

Device entry format in the `devices[]` array:
```json
{"deviceID": "XXXX-YYYY-...", "introducedBy": "", "encryptionPassword": ""}
```

Both folders can start paused and be resumed when ready.
