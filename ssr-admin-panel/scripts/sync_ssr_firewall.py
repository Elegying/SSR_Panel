#!/usr/bin/env python3
"""Synchronize SSR user ports with the host firewall."""

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path


MUDB_FILE = Path(os.environ.get("SSR_MUDB_FILE", "/usr/local/shadowsocksr/mudb.json"))
STATE_FILE = Path(
    os.environ.get(
        "SSR_FIREWALL_STATE_FILE",
        "/var/lib/ssr-panel-firewall/managed-ports.json",
    )
)
CONFIG_FILE = Path(
    os.environ.get("SSR_FIREWALL_CONFIG_FILE", "/etc/default/ssr-panel-firewall")
)
RULE_ARGS = ("-m", "conntrack", "--ctstate", "NEW")
PROTOCOLS = ("tcp", "udp")


class FirewallSyncError(RuntimeError):
    pass


def parse_port(value, source):
    if isinstance(value, bool):
        raise FirewallSyncError("invalid port in {0}: {1!r}".format(source, value))
    if isinstance(value, int):
        port = value
    elif isinstance(value, str) and value.isdigit():
        port = int(value)
    else:
        raise FirewallSyncError("invalid port in {0}: {1!r}".format(source, value))
    if not 1 <= port <= 65535:
        raise FirewallSyncError("port out of range in {0}: {1}".format(source, port))
    return port


def load_mudb_ports():
    if not MUDB_FILE.is_file() or MUDB_FILE.is_symlink():
        raise FirewallSyncError("SSR user database is missing or unsafe: {0}".format(MUDB_FILE))
    try:
        with MUDB_FILE.open(encoding="utf-8-sig") as handle:
            users = json.load(handle)
    except (OSError, ValueError) as exc:
        raise FirewallSyncError("cannot read SSR user database: {0}".format(exc))
    if not isinstance(users, list):
        raise FirewallSyncError("SSR user database must contain a JSON list")

    ports = set()
    for index, user in enumerate(users):
        if not isinstance(user, dict) or "port" not in user:
            continue
        ports.add(parse_port(user["port"], "mudb.json user {0}".format(index)))
    return ports


def load_extra_ports():
    configured = read_extra_ports_setting()
    ports = set()
    for value in filter(None, re.split(r"[\s,]+", configured.strip())):
        ports.add(parse_port(value, "SSR_EXTRA_PORTS"))
    return ports


def read_extra_ports_setting():
    if "SSR_EXTRA_PORTS" in os.environ:
        return os.environ["SSR_EXTRA_PORTS"]
    if not CONFIG_FILE.exists():
        return "18899"
    if not CONFIG_FILE.is_file() or CONFIG_FILE.is_symlink():
        raise FirewallSyncError("firewall config file is unsafe: {0}".format(CONFIG_FILE))

    value = None
    try:
        with CONFIG_FILE.open(encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, candidate = line.split("=", 1)
                if key.strip() != "SSR_EXTRA_PORTS":
                    continue
                candidate = candidate.strip()
                if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in "\"'":
                    candidate = candidate[1:-1]
                value = candidate
    except OSError as exc:
        raise FirewallSyncError("cannot read firewall config: {0}".format(exc))
    return "18899" if value is None else value


def load_previous_ports():
    if not STATE_FILE.exists():
        return set()
    if not STATE_FILE.is_file() or STATE_FILE.is_symlink():
        raise FirewallSyncError("firewall state file is unsafe: {0}".format(STATE_FILE))
    try:
        with STATE_FILE.open(encoding="utf-8") as handle:
            values = json.load(handle)
    except (OSError, ValueError) as exc:
        raise FirewallSyncError("cannot read firewall state: {0}".format(exc))
    if not isinstance(values, list):
        raise FirewallSyncError("firewall state must contain a JSON list")
    return {parse_port(value, "firewall state") for value in values}


def run(command, check=True):
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=False,
        )
    except OSError as exc:
        raise FirewallSyncError("cannot run {0}: {1}".format(command[0], exc))
    if check and result.returncode != 0:
        details = (result.stderr or result.stdout).strip() or "exit {0}".format(result.returncode)
        raise FirewallSyncError("{0} failed: {1}".format(command[0], details))
    return result


def uses_firewalld():
    return shutil.which("firewall-cmd") is not None and run(
        ["firewall-cmd", "--state"], check=False
    ).returncode == 0


def sync_firewalld(desired, stale):
    changed = False
    for port in sorted(desired):
        for protocol in PROTOCOLS:
            spec = "{0}/{1}".format(port, protocol)
            query = run(
                ["firewall-cmd", "--permanent", "--query-port={0}".format(spec)],
                check=False,
            )
            if query.returncode != 0:
                run(["firewall-cmd", "--permanent", "--add-port={0}".format(spec)])
                changed = True
    for port in sorted(stale):
        for protocol in PROTOCOLS:
            spec = "{0}/{1}".format(port, protocol)
            query = run(
                ["firewall-cmd", "--permanent", "--query-port={0}".format(spec)],
                check=False,
            )
            if query.returncode == 0:
                run(["firewall-cmd", "--permanent", "--remove-port={0}".format(spec)])
                changed = True
    if changed:
        run(["firewall-cmd", "--reload"])
    return changed


def iptables_rule(protocol, port):
    return list(RULE_ARGS) + ["-p", protocol, "--dport", str(port), "-j", "ACCEPT"]


def sync_iptables(desired, stale):
    commands = []
    for name in ("iptables", "ip6tables"):
        if shutil.which(name) and run([name, "-S", "INPUT"], check=False).returncode == 0:
            commands.append(name)
    if not commands:
        raise FirewallSyncError("no supported firewall backend found")

    changed = False
    for command in commands:
        for port in sorted(desired):
            for protocol in PROTOCOLS:
                rule = iptables_rule(protocol, port)
                if run([command, "-C", "INPUT"] + rule, check=False).returncode != 0:
                    run([command, "-I", "INPUT"] + rule)
                    changed = True
        for port in sorted(stale):
            for protocol in PROTOCOLS:
                rule = iptables_rule(protocol, port)
                if run([command, "-C", "INPUT"] + rule, check=False).returncode == 0:
                    run([command, "-D", "INPUT"] + rule)
                    changed = True
    if changed:
        persist_iptables(commands)
    return changed


def atomic_write(path, data, mode=0o600):
    ensure_safe_directory(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=".{0}.".format(path.name), dir=str(path.parent))
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, str(path))
        os.chmod(str(path), mode)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def ensure_safe_directory(path):
    try:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise FirewallSyncError("cannot create directory {0}: {1}".format(path, exc))
    if not path.is_dir() or path.is_symlink():
        raise FirewallSyncError("directory is unsafe: {0}".format(path))


@contextmanager
def firewall_lock():
    ensure_safe_directory(STATE_FILE.parent)
    lock_path = STATE_FILE.parent / ".sync.lock"
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = None
    try:
        descriptor = os.open(str(lock_path), flags, 0o600)
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise FirewallSyncError("cannot lock firewall state: {0}".format(exc))
    try:
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def persist_iptables(commands):
    if shutil.which("netfilter-persistent"):
        run(["netfilter-persistent", "save"])
        return

    locations = {
        "iptables": (
            "/etc/sysconfig/iptables"
            if Path("/etc/sysconfig").is_dir()
            else "/etc/iptables.up.rules"
        ),
        "ip6tables": (
            "/etc/sysconfig/ip6tables"
            if Path("/etc/sysconfig").is_dir()
            else "/etc/ip6tables.up.rules"
        ),
    }
    for command in commands:
        save_command = "{0}-save".format(command)
        if not shutil.which(save_command):
            raise FirewallSyncError("{0} not found; cannot persist firewall rules".format(save_command))
        result = run([save_command])
        atomic_write(Path(locations[command]), result.stdout.encode("utf-8"))


def save_state(ports):
    payload = (json.dumps(sorted(ports), separators=(",", ":")) + "\n").encode("utf-8")
    atomic_write(STATE_FILE, payload)
    marker = STATE_FILE.parent / ".ssr-panel-managed"
    if not marker.exists():
        atomic_write(marker, b"Managed by SSR_Panel\n")


def main():
    with firewall_lock():
        desired = load_mudb_ports() | load_extra_ports()
        previous = load_previous_ports()
        stale = previous - desired
        if uses_firewalld():
            backend = "firewalld"
            changed = sync_firewalld(desired, stale)
        else:
            backend = "iptables"
            changed = sync_iptables(desired, stale)
        save_state(desired)
    print(
        "SSR firewall synchronized: backend={0}, ports={1}, changed={2}".format(
            backend,
            ",".join(str(port) for port in sorted(desired)) or "none",
            "yes" if changed else "no",
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FirewallSyncError as exc:
        print("SSR firewall sync failed: {0}".format(exc), file=sys.stderr)
        sys.exit(1)
