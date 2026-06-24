import asyncio
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from backend.config import settings


@dataclass
class Tunnel:
    name: str
    host: str
    ssh_port: int
    local_port: int
    key_path: str
    api_key: str
    proc: subprocess.Popen = field(repr=False)


_tunnels: dict[str, Tunnel] = {}
_used_ports: set[int] = set()


def _next_port() -> int:
    port = settings.tunnel_port_start
    while port in _used_ports:
        port += 1
    return port


def _wait_for_port(port: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


def open_tunnel(name: str, host: str, ssh_port: int, key_path: str, api_key: str = "") -> Tunnel:
    if name in _tunnels:
        return _tunnels[name]

    local_port = _next_port()
    _used_ports.add(local_port)

    proc = subprocess.Popen(
        [
            "ssh", "-N",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ConnectTimeout=5",
            "-o", "ServerAliveInterval=10",
            "-i", key_path,
            "-p", str(ssh_port),
            "-L", f"{local_port}:127.0.0.1:8384",
            f"root@{host}",
        ],
        stderr=subprocess.DEVNULL,
    )

    if not _wait_for_port(local_port, timeout=10.0):
        proc.terminate()
        proc.wait()
        _used_ports.discard(local_port)
        raise RuntimeError(f"SSH tunnel to {host}:{ssh_port} did not open within 10s")

    tunnel = Tunnel(
        name=name,
        host=host,
        ssh_port=ssh_port,
        local_port=local_port,
        key_path=key_path,
        api_key=api_key,
        proc=proc,
    )
    _tunnels[name] = tunnel
    return tunnel


def close_tunnel(name: str) -> bool:
    tunnel = _tunnels.pop(name, None)
    if tunnel is None:
        return False
    _used_ports.discard(tunnel.local_port)
    tunnel.proc.terminate()
    tunnel.proc.wait()
    return True


def get_all_tunnels() -> list[dict]:
    return [
        {
            "name": t.name,
            "host": t.host,
            "ssh_port": t.ssh_port,
            "local_port": t.local_port,
            "api_key": t.api_key,
        }
        for t in _tunnels.values()
    ]


def get_tunnel(name: str) -> Tunnel | None:
    return _tunnels.get(name)


def cleanup_all() -> None:
    for tunnel in list(_tunnels.values()):
        tunnel.proc.terminate()
        tunnel.proc.wait()
    _tunnels.clear()
    _used_ports.clear()


async def run_ssh_command(
    host: str,
    ssh_port: int,
    key_path: str,
    command: str,
    timeout: float = 15.0,
) -> str:
    proc = await asyncio.create_subprocess_exec(
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=5",
        "-i", key_path,
        "-p", str(ssh_port),
        f"root@{host}",
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"SSH command timed out after {timeout}s")

    if proc.returncode != 0:
        raise RuntimeError(f"SSH command failed (exit {proc.returncode}): {stderr.decode().strip()}")
    return stdout.decode().strip()


def key_path_for(drone_name: str) -> str:
    return str(settings.keys_dir / drone_name / "id_ed25519")
