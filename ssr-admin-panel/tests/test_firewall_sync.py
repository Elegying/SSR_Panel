import json
import os
import stat
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "sync_ssr_firewall.py"


class FirewallSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.action_log = self.root / "actions.log"
        self.rule_state = self.root / "rules"
        self.rule_state.mkdir()
        self.mudb_file = self.root / "mudb.json"
        self.state_file = self.root / "state" / "ports.json"

        firewall_stub = (
            "#!/bin/sh\n"
            "printf '%s' \"${0##*/}\" >> \"$ACTION_LOG\"\n"
            "for arg in \"$@\"; do printf '\\t%s' \"$arg\" >> \"$ACTION_LOG\"; done\n"
            "printf '\\n' >> \"$ACTION_LOG\"\n"
            "action=${1:-}; protocol=unknown; port=unknown; previous=\n"
            "for arg in \"$@\"; do\n"
            "  [ \"$previous\" = -p ] && protocol=$arg\n"
            "  [ \"$previous\" = --dport ] && port=$arg\n"
            "  previous=$arg\n"
            "done\n"
            "marker=\"$RULE_STATE/${0##*/}-${protocol}-${port}\"\n"
            "case \"$action\" in\n"
            "  -C) [ -e \"$marker\" ] ;;\n"
            "  -I) [ -z \"${SYNC_TEST_INSERT_DELAY:-}\" ] || sleep \"$SYNC_TEST_INSERT_DELAY\"; : > \"$marker\" ;;\n"
            "  -D) rm -f \"$marker\" ;;\n"
            "esac\n"
        )
        for command in ("iptables", "ip6tables"):
            self.write_executable(self.bin_dir / command, firewall_stub)

        self.write_executable(
            self.bin_dir / "netfilter-persistent",
            "#!/bin/sh\n"
            "printf 'netfilter-persistent' >> \"$ACTION_LOG\"\n"
            "for arg in \"$@\"; do printf '\\t%s' \"$arg\" >> \"$ACTION_LOG\"; done\n"
            "printf '\\n' >> \"$ACTION_LOG\"\n",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def write_executable(path, content):
        path.write_text(content, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def write_users(self, users):
        self.mudb_file.write_text(json.dumps(users), encoding="utf-8")

    def run_sync(self, extra_ports="18899", config_file=None, env_overrides=None):
        env = {
            **os.environ,
            "PATH": f"{self.bin_dir}:{os.environ['PATH']}",
            "ACTION_LOG": str(self.action_log),
            "RULE_STATE": str(self.rule_state),
            "SSR_MUDB_FILE": str(self.mudb_file),
            "SSR_FIREWALL_STATE_FILE": str(self.state_file),
        }
        if extra_ports is None:
            env.pop("SSR_EXTRA_PORTS", None)
        else:
            env["SSR_EXTRA_PORTS"] = extra_ports
        if config_file is not None:
            env["SSR_FIREWALL_CONFIG_FILE"] = str(config_file)
        env.update(env_overrides or {})
        return subprocess.run(
            [str(SCRIPT)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def actions(self):
        if not self.action_log.exists():
            return ""
        return self.action_log.read_text(encoding="utf-8")

    def test_syncs_mudb_and_default_extra_port_idempotently(self):
        self.write_users([{"port": 2333}, {"port": "24444"}])

        first = self.run_sync()

        self.assertEqual(first.returncode, 0, msg=first.stderr)
        first_actions = self.actions()
        for command in ("iptables", "ip6tables"):
            for protocol in ("tcp", "udp"):
                for port in (2333, 18899, 24444):
                    self.assertIn(
                        f"{command}\t-I\tINPUT\t-m\tconntrack\t--ctstate\tNEW"
                        f"\t-p\t{protocol}\t--dport\t{port}\t-j\tACCEPT",
                        first_actions,
                    )
        self.assertEqual(json.loads(self.state_file.read_text(encoding="utf-8")), [2333, 18899, 24444])
        self.assertEqual(stat.S_IMODE(self.state_file.stat().st_mode), 0o600)
        self.assertIn("netfilter-persistent\tsave", first_actions)

        self.action_log.unlink()
        second = self.run_sync()

        self.assertEqual(second.returncode, 0, msg=second.stderr)
        self.assertNotIn("\t-I\tINPUT", self.actions())
        self.assertNotIn("netfilter-persistent\tsave", self.actions())

    def test_removes_stale_managed_ports(self):
        self.write_users([{"port": 2333}])
        self.assertEqual(self.run_sync().returncode, 0)
        self.action_log.unlink()
        self.write_users([])

        result = self.run_sync()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        actions = self.actions()
        for command in ("iptables", "ip6tables"):
            for protocol in ("tcp", "udp"):
                self.assertIn(
                    f"{command}\t-D\tINPUT\t-m\tconntrack\t--ctstate\tNEW"
                    f"\t-p\t{protocol}\t--dport\t2333\t-j\tACCEPT",
                    actions,
                )
        self.assertEqual(json.loads(self.state_file.read_text(encoding="utf-8")), [18899])

    def test_corrupt_mudb_fails_before_firewall_mutation(self):
        self.mudb_file.write_text("{broken-json", encoding="utf-8")

        result = self.run_sync()

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.actions(), "")
        self.assertFalse(self.state_file.exists())

    def test_invalid_mudb_port_fails_before_firewall_mutation(self):
        self.write_users([{"port": 0}, {"port": "not-a-port"}])

        result = self.run_sync()

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.actions(), "")
        self.assertFalse(self.state_file.exists())

    def test_corrupt_state_fails_before_firewall_mutation(self):
        self.write_users([])
        self.state_file.parent.mkdir()
        self.state_file.write_text("{broken-json", encoding="utf-8")

        result = self.run_sync()

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.actions(), "")
        self.assertEqual(self.state_file.read_text(encoding="utf-8"), "{broken-json")

    def test_invalid_extra_port_fails_before_firewall_mutation(self):
        self.write_users([])

        result = self.run_sync("18899;touch /tmp/should-not-exist")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.actions(), "")
        self.assertFalse(self.state_file.exists())

    def test_reads_extra_ports_config_when_called_outside_ssr_service(self):
        self.write_users([])
        config_file = self.root / "ssr-panel-firewall"
        config_file.write_text(
            "# Managed by SSR_Panel\nSSR_EXTRA_PORTS=24444\n",
            encoding="utf-8",
        )

        result = self.run_sync(extra_ports=None, config_file=config_file)

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(json.loads(self.state_file.read_text(encoding="utf-8")), [24444])
        self.assertIn("\t--dport\t24444\t", self.actions())
        self.assertNotIn("\t--dport\t18899\t", self.actions())

    def test_uses_firewalld_permanent_rules_when_active(self):
        firewalld_state = self.root / "firewalld"
        firewalld_state.mkdir()
        self.write_executable(
            self.bin_dir / "firewall-cmd",
            "#!/bin/sh\n"
            "printf 'firewall-cmd' >> \"$ACTION_LOG\"\n"
            "for arg in \"$@\"; do printf '\\t%s' \"$arg\" >> \"$ACTION_LOG\"; done\n"
            "printf '\\n' >> \"$ACTION_LOG\"\n"
            "[ \"${1:-}\" = --state ] && exit 0\n"
            "for arg in \"$@\"; do\n"
            "  case \"$arg\" in\n"
            "    --query-port=*) spec=${arg#*=}; [ -e \"$FIREWALLD_STATE/${spec%/*}-${spec#*/}\" ]; exit ;;\n"
            "    --add-port=*) spec=${arg#*=}; : > \"$FIREWALLD_STATE/${spec%/*}-${spec#*/}\"; exit ;;\n"
            "    --remove-port=*) spec=${arg#*=}; rm -f \"$FIREWALLD_STATE/${spec%/*}-${spec#*/}\"; exit ;;\n"
            "  esac\n"
            "done\n"
            "exit 0\n",
        )
        self.write_users([])
        original = os.environ.get("FIREWALLD_STATE")
        os.environ["FIREWALLD_STATE"] = str(firewalld_state)
        try:
            first = self.run_sync()
            self.action_log.unlink()
            second = self.run_sync("24444")
        finally:
            if original is None:
                os.environ.pop("FIREWALLD_STATE", None)
            else:
                os.environ["FIREWALLD_STATE"] = original

        self.assertEqual(first.returncode, 0, msg=first.stderr)
        self.assertEqual(second.returncode, 0, msg=second.stderr)
        actions = self.actions()
        self.assertIn("firewall-cmd\t--permanent\t--add-port=24444/tcp", actions)
        self.assertIn("firewall-cmd\t--permanent\t--remove-port=18899/tcp", actions)
        self.assertIn("firewall-cmd\t--reload", actions)
        self.assertNotIn("iptables\t", actions)

    def test_concurrent_syncs_do_not_insert_duplicate_rules(self):
        self.write_users([])

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _index: self.run_sync(
                        env_overrides={"SYNC_TEST_INSERT_DELAY": "0.1"}
                    ),
                    range(2),
                )
            )

        for result in results:
            self.assertEqual(result.returncode, 0, msg=result.stderr)
        insertions = [line for line in self.actions().splitlines() if "\t-I\tINPUT" in line]
        self.assertEqual(len(insertions), 4, msg="concurrent sync inserted duplicate firewall rules")

    def test_skips_unavailable_ipv6_firewall_backend(self):
        self.write_executable(
            self.bin_dir / "ip6tables",
            "#!/bin/sh\n"
            "printf 'ip6tables' >> \"$ACTION_LOG\"\n"
            "for arg in \"$@\"; do printf '\\t%s' \"$arg\" >> \"$ACTION_LOG\"; done\n"
            "printf '\\n' >> \"$ACTION_LOG\"\n"
            "exit 1\n",
        )
        self.write_users([])

        result = self.run_sync()

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("iptables\t-I\tINPUT", self.actions())
        self.assertNotIn("ip6tables\t-I\tINPUT", self.actions())


if __name__ == "__main__":
    unittest.main()
