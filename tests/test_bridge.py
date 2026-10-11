import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
import bridge

BRIDGE = Path(__file__).resolve().parents[1] / "bridge" / "bridge.py"


class BridgeTest(unittest.TestCase):
    def test_workspace_matches_active_tab_title(self):
        tabs = [{"id": 1, "windowId": 4, "title": "Other tab", "active": False},
                {"id": 2, "windowId": 4, "title": "Docs", "active": True}]
        clients = [{"class": "google-chrome", "title": "Docs - Google Chrome",
                    "workspace": {"name": "7"}}]
        with patch.object(bridge.subprocess, "check_output", return_value=json.dumps(clients)):
            result = bridge.add_workspaces(tabs)
        self.assertEqual([tab["workspace"] for tab in result], ["7", "7"])

    def test_ambiguous_window_title_does_not_guess_workspace(self):
        tabs = [{"id": 1, "windowId": 4, "title": "Docs", "active": True}]
        clients = [{"class": "google-chrome", "title": "Docs - Google Chrome",
                    "workspace": {"name": name}} for name in ("1", "2")]
        with patch.object(bridge.subprocess, "check_output", return_value=json.dumps(clients)):
            self.assertNotIn("workspace", bridge.add_workspaces(tabs)[0])

    def test_list_round_trip(self):
        with tempfile.TemporaryDirectory() as runtime:
            env = dict(os.environ, XDG_RUNTIME_DIR=runtime)
            host = subprocess.Popen([sys.executable, str(BRIDGE),
                                     "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/",
                                     "--parent-window=0"], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            try:
                path = Path(runtime) / "omarchy-chrome-search.sock"
                for _ in range(100):
                    if path.exists():
                        break
                    time.sleep(0.01)
                with socket.socket(socket.AF_UNIX) as client:
                    client.settimeout(3)
                    client.connect(str(path))
                    client.sendall(b'{"action":"list"}')
                    size = struct.unpack("=I", host.stdout.read(4))[0]
                    request = json.loads(host.stdout.read(size))
                    self.assertEqual(request["action"], "list")
                    response = json.dumps({"id": request["id"], "result": [
                        {"id": 42, "title": "Example"}]}).encode()
                    host.stdin.write(struct.pack("=I", len(response)) + response)
                    host.stdin.flush()
                    self.assertEqual(json.loads(client.recv(4096))["result"][0]["id"], 42)
            finally:
                host.stdin.close()
                host.wait(timeout=3)
                host.stdout.close()
                host.stderr.close()
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
