#!/usr/bin/env python3

import argparse
from typing import Dict, List, Optional, Set, Tuple
import ipaddress
import json
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_MUDB_FILE = "/usr/local/shadowsocksr/mudb.json"
DEFAULT_OUTPUT_FILE = "/var/lib/ssr-admin-panel/device-stats.json"
DEFAULT_INTERVAL = 15
DEFAULT_WINDOW = 900


def utc_now_iso(now: Optional[float] = None) -> str:
    return datetime.fromtimestamp(now or time.time(), timezone.utc).isoformat()


def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_user_ports(mudb_file: Path) -> Set[int]:
    try:
        payload = json.loads(mudb_file.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return set()

    if not isinstance(payload, list):
        return set()

    ports = set()
    for user in payload:
        if not isinstance(user, dict):
            continue
        port = to_int(user.get("port"), 0)
        if 1 <= port <= 65535:
            ports.add(port)
    return ports


def strip_zone_id(host: str) -> str:
    return host.split("%", 1)[0]


def normalize_peer_host(host: str) -> str:
    candidate = strip_zone_id(host.strip("[]"))
    try:
        ip = ipaddress.ip_address(candidate)
    except ValueError:
        return candidate

    if getattr(ip, "ipv4_mapped", None):
        return str(ip.ipv4_mapped)
    return str(ip)


def parse_endpoint(endpoint: str) -> Optional[Tuple[str, int]]:
    endpoint = endpoint.strip()
    if not endpoint:
        return None

    if endpoint.startswith("["):
        match = re.match(r"^\[(?P<host>.+)]:(?P<port>\d+)$", endpoint)
        if not match:
            return None
        return normalize_peer_host(match.group("host")), int(match.group("port"))

    if endpoint.count(":") == 1:
        host, raw_port = endpoint.rsplit(":", 1)
        if raw_port.isdigit():
            return normalize_peer_host(host), int(raw_port)

    host, sep, raw_port = endpoint.rpartition(":")
    if sep and raw_port.isdigit():
        return normalize_peer_host(host), int(raw_port)

    return None


def collect_tcp_peers_from_ss(ports: Set[int]) -> Dict[int, Set[str]]:
    if not ports or not shutil.which("ss"):
        return {}

    result = subprocess.run(
        ["ss", "-H", "-tan", "state", "established"],
        stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
        universal_newlines=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return {}

    peers_by_port: Dict[int, Set[str]] = {port: set() for port in ports}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue

        local = parse_endpoint(parts[-2])
        peer = parse_endpoint(parts[-1])
        if not local or not peer:
            continue

        _, local_port = local
        peer_host, _ = peer
        if local_port in ports and peer_host not in {"", "*", "0.0.0.0", "::"}:
            peers_by_port.setdefault(local_port, set()).add(peer_host)

    return peers_by_port


def load_previous_stats(output_file: Path) -> dict:
    try:
        payload = json.loads(output_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def build_stats(mudb_file: Path, output_file: Path, window_seconds: int) -> dict:
    now = time.time()
    ports = load_user_ports(mudb_file)
    current_peers = collect_tcp_peers_from_ss(ports)
    previous = load_previous_stats(output_file)
    previous_ports = previous.get("ports", {}) if isinstance(previous.get("ports"), dict) else {}
    cutoff = now - max(1, window_seconds)

    stats_ports = {}
    for port in sorted(ports):
        port_key = str(port)
        old_peers = previous_ports.get(port_key, {}).get("peers", {})
        recent_peers = {}

        if isinstance(old_peers, dict):
            for peer, meta in old_peers.items():
                if not isinstance(meta, dict):
                    continue
                last_seen = float(to_int(meta.get("last_seen_ts"), 0))
                if last_seen >= cutoff:
                    recent_peers[str(peer)] = {
                        "first_seen_ts": float(to_int(meta.get("first_seen_ts"), last_seen)),
                        "last_seen_ts": last_seen,
                    }

        for peer in sorted(current_peers.get(port, set())):
            meta = recent_peers.get(peer, {})
            recent_peers[peer] = {
                "first_seen_ts": float(meta.get("first_seen_ts") or now),
                "last_seen_ts": now,
            }

        last_seen_ts = max((meta["last_seen_ts"] for meta in recent_peers.values()), default=0)
        stats_ports[port_key] = {
            "online_count": len(current_peers.get(port, set())),
            "recent_count": len(recent_peers),
            "last_seen": utc_now_iso(last_seen_ts) if last_seen_ts else "",
            "peers": recent_peers,
        }

    return {
        "generated_at": utc_now_iso(now),
        "generated_at_ts": now,
        "window_seconds": max(1, window_seconds),
        "source": "ss",
        "ports": stats_ports,
    }


def write_stats(output_file: Path, stats: dict) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = output_file.with_suffix(output_file.suffix + ".tmp")
    temp_file.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(output_file)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect approximate SSR device counts by user port.")
    parser.add_argument("--mudb", default=DEFAULT_MUDB_FILE)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--watch", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mudb_file = Path(args.mudb)
    output_file = Path(args.output)
    interval = max(5, args.interval)
    window = max(interval, args.window)

    while True:
        stats = build_stats(mudb_file, output_file, window)
        write_stats(output_file, stats)
        if not args.watch:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
