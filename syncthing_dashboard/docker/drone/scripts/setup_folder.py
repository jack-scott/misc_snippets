#!/usr/bin/env python3
"""Register the organised folder with syncthing if not already present."""
import requests
import os

API_KEY = os.environ.get("SYNCTHING_API_KEY", "syncthing-api-key")
ROLE = os.environ.get("ROLE", "drone")
BASE = "http://localhost:8384/rest"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

resp = requests.get(f"{BASE}/config/folders", headers=HEADERS)
folders = resp.json()

if any(f["id"] == "organised" for f in folders):
    print("organised folder already configured")
else:
    folder_type = "sendonly" if ROLE == "drone" else "receiveonly"
    config = {
        "id": "organised",
        "label": "Organised",
        "path": "/data/organised",
        "type": folder_type,
        "devices": [],
        "paused": False,
        "rescanIntervalS": 60,
        "fsWatcherEnabled": True,
    }
    r = requests.post(f"{BASE}/config/folders", json=config, headers=HEADERS)
    print(f"Added organised folder ({folder_type}): {r.status_code}")
