#!/usr/bin/env python3
"""Patch syncthing config.xml with known API key and GUI settings."""
import xml.etree.ElementTree as ET
import os
import sys

config_path = sys.argv[1]
api_key = os.environ.get("SYNCTHING_API_KEY", "syncthing-api-key")
role = os.environ.get("ROLE", "drone")

# Server needs 0.0.0.0 so Docker NAT can forward the port.
# Drones stay on 127.0.0.1 — only reachable via SSH tunnel, never exposed.
address = "0.0.0.0:8384" if role == "server" else "127.0.0.1:8384"

tree = ET.parse(config_path)
root = tree.getroot()

gui = root.find("gui")
if gui is None:
    gui = ET.SubElement(root, "gui")
    gui.set("enabled", "true")
    gui.set("tls", "false")

def set_el(parent, tag, text):
    el = parent.find(tag)
    if el is None:
        el = ET.SubElement(parent, tag)
    el.text = text

set_el(gui, "address", address)
set_el(gui, "apikey", api_key)
# insecureSkipHostcheck deliberately omitted — browser never talks to Syncthing directly

# Remove insecureSkipHostcheck if a previous run set it
hc = gui.find("insecureSkipHostcheck")
if hc is not None:
    gui.remove(hc)

tree.write(config_path, xml_declaration=True, encoding="unicode")
print(f"Config patched: role={role}, GUI={address}, API key set")
