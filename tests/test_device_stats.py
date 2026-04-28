import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "collect_device_stats.py"

spec = importlib.util.spec_from_file_location("collect_device_stats", SCRIPT_PATH)
device_stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(device_stats)


class DeviceStatsCollectorTests(unittest.TestCase):
    def test_parse_endpoint_handles_ipv4_and_ipv6(self):
        self.assertEqual(device_stats.parse_endpoint("1.2.3.4:443"), ("1.2.3.4", 443))
        self.assertEqual(device_stats.parse_endpoint("[::ffff:1.2.3.4]:443"), ("1.2.3.4", 443))
        self.assertEqual(device_stats.parse_endpoint("[2001:db8::1]:443"), ("2001:db8::1", 443))

    def test_build_stats_counts_current_and_recent_peers(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            mudb = base / "mudb.json"
            output = base / "device-stats.json"
            mudb.write_text(json.dumps([{"port": 2333}]), encoding="utf-8")
            output.write_text(
                json.dumps(
                    {
                        "ports": {
                            "2333": {
                                "peers": {
                                    "9.9.9.9": {
                                        "first_seen_ts": 1999999950,
                                        "last_seen_ts": 1999999960,
                                    }
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(device_stats.time, "time", return_value=2000000000), mock.patch.object(
                device_stats, "collect_tcp_peers_from_ss", return_value={2333: {"1.1.1.1"}}
            ):
                stats = device_stats.build_stats(mudb, output, 900)

            self.assertEqual(stats["ports"]["2333"]["online_count"], 1)
            self.assertEqual(stats["ports"]["2333"]["recent_count"], 2)
            self.assertIn("1.1.1.1", stats["ports"]["2333"]["peers"])
            self.assertIn("9.9.9.9", stats["ports"]["2333"]["peers"])


if __name__ == "__main__":
    unittest.main()
