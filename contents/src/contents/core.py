"""Encode/decode a package's params or diagnostics YAML into image labels."""

import base64
import re

import docker
import yaml

LABEL_PREFIX = "io.ros.pkg"


def label_key(pkg: str, field: str) -> str:
    return f"{LABEL_PREFIX}.{pkg}.{field}"


def env_var_name(pkg: str, field: str) -> str:
    return re.sub(r"[^A-Z0-9_]", "_", f"{pkg}_{field}".upper())


def encode(path: str, canon: bool = False) -> str:
    data = open(path, "rb").read()
    if canon:
        data = yaml.safe_dump(
            yaml.safe_load(data), sort_keys=True, default_flow_style=False
        ).encode()
    return f"{'canon64' if canon else 'raw64'}:{base64.b64encode(data).decode()}"


def decode_value(value: str) -> bytes:
    _scheme, payload = value.split(":", 1)
    return base64.b64decode(payload)


def decode(image_ref: str, pkg: str, field: str) -> bytes:
    labels = docker.from_env().images.get(image_ref).labels or {}
    return decode_value(labels[label_key(pkg, field)])
