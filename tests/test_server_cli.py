import base64
import hashlib
import http.client
import io
import json
import socket
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from hp_regen.cli import main
from hp_regen.server import LocalServer, Workbench


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Workbench(demo=True)
        cls.server = LocalServer(("127.0.0.1", 0), cls.app)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(3)

    def request(self, method, path, payload=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        raw = json.dumps(payload) if payload is not None else None
        h = {"Content-Type": "application/json"}
        h.update(headers or {})
        connection.request(method, path, raw, h)
        response = connection.getresponse()
        body = response.read()
        status, response_headers = response.status, dict(response.getheaders())
        connection.close()
        return status, body, response_headers

    def test_session_and_demo_banner_data(self):
        status, body, headers = self.request("GET", "/api/session")
        result = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(result["demo"])
        self.assertEqual(result["csrf_token"], self.app.token)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_wrong_host_cannot_obtain_token(self):
        status, _, _ = self.request("GET", "/api/session", headers={"Host": "evil.example"})
        self.assertEqual(status, 403)

    def test_cross_origin_and_fetch_site_blocked(self):
        for headers in ({"Origin": "https://evil.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"}):
            self.assertEqual(self.request("GET", "/api/session", headers=headers)[0], 403)

    def test_missing_wrong_and_non_ascii_token_blocked(self):
        for headers in ({}, {"X-Regen-Token": "bad"}, {"X-Regen-Token": "é"}):
            self.assertEqual(self.request("POST", "/api/discover", {"acknowledged": True}, headers)[0], 403)

    def test_authorized_demo_discovery_has_no_network_side_effect(self):
        with patch("hp_regen.network.discover_mdns", side_effect=AssertionError("No live network in demo")):
            status, body, _ = self.request("POST", "/api/discover", {"method": "mdns", "acknowledged": True}, {"X-Regen-Token": self.app.token})
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(body)["devices"]), 2)

    def test_discovery_requires_ack_and_scope(self):
        for payload in ({"method": "mdns"}, {"method": "subnet", "cidr": "8.8.8.0/24", "acknowledged": True}, {"method": "all", "acknowledged": True}):
            self.assertEqual(self.request("POST", "/api/discover", payload, {"X-Regen-Token": self.app.token})[0], 400)

    def test_demo_never_installs_real_queue(self):
        with patch("hp_regen.bridge.install_queue", side_effect=AssertionError("No CUPS writes in demo")):
            self.assertEqual(self.request("POST", "/api/bridge/install", {"uri": "ipp://192.168.50.21/ipp/print", "queue_name": "Regen", "acknowledged": True}, {"X-Regen-Token": self.app.token})[0], 400)

    def test_offline_preflight_over_api(self):
        data = b"offline-fixture"
        manifest = {"schema_version": 1, "model": "Fixture", "firmware_version": "1", "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "source_url": "https://example.org/image"}
        status, body, _ = self.request("POST", "/api/firmware/preflight", {"manifest": manifest, "model": "Fixture", "data_base64": base64.b64encode(data).decode()}, {"X-Regen-Token": self.app.token})
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["preflight"]["ready_to_flash"])

    def test_path_traversal_not_served(self):
        self.assertEqual(self.request("GET", "/../../LICENSE")[0], 404)

    def test_unsupported_operation_not_available(self):
        self.assertEqual(self.request("POST", "/api/flash", {}, {"X-Regen-Token": self.app.token})[0], 400)

    def test_malformed_absolute_target_returns_json(self):
        with socket.create_connection(("127.0.0.1", self.port), timeout=3) as transport:
            transport.sendall(f"GET http://[ HTTP/1.0\r\nHost: 127.0.0.1:{self.port}\r\n\r\n".encode())
            response = http.client.HTTPResponse(transport)
            response.begin()
            self.assertEqual(response.status, 400)
            self.assertIn("error", json.loads(response.read()))

    def test_discovery_retains_inspection_and_report_inventory(self):
        app = Workbench(demo=False)
        app.devices = [{"uri": "ipp://192.168.1.2:631/ipp/print", "name": "Previously checked", "firmware": "fixture"}]
        with patch("hp_regen.network.discover_mdns", return_value=[]):
            app.action("/api/discover", {"method": "mdns", "acknowledged": True})
        self.assertEqual(app.report()["devices"][0]["firmware"], "fixture")
        app.last_discovery = -float("inf")
        with patch("hp_regen.network.discover_mdns", return_value=[{"uri": "ipp://192.168.1.2:631/ipp/print", "name": "Found again"}]):
            app.action("/api/discover", {"method": "mdns", "acknowledged": True})
        self.assertEqual(len(app.devices), 1)
        self.assertEqual(app.report()["devices"][0]["firmware"], "fixture")

    def test_live_workbench_starts_empty(self):
        self.assertEqual(Workbench(demo=False).devices, [])

    def test_network_bind_refused(self):
        with self.assertRaises(ValueError):
            LocalServer(("0.0.0.0", 8765), self.app)

    def test_report_does_not_contain_csrf_token(self):
        _, body, _ = self.request("GET", "/api/report")
        self.assertNotIn(self.app.token.encode(), body)

    def test_wrong_content_type_and_oversized_body(self):
        self.assertEqual(self.request("POST", "/api/discover", {}, {"X-Regen-Token": self.app.token, "Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("POST", "/api/discover", {}, {"X-Regen-Token": self.app.token, "Content-Length": "999999999"})[0], 413)


class CliTests(unittest.TestCase):
    def test_inspect_requires_ownership_flag(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["inspect", "ipp://192.168.1.25/ipp/print"]), 2)

    def test_discover_requires_ownership_flag(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["discover"]), 2)

    def test_bridge_is_plan_only_by_default(self):
        with patch("hp_regen.bridge.bridge_plan", return_value={"supported": False}), patch("hp_regen.bridge.install_queue", side_effect=AssertionError("must not install")), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["bridge", "ipp://192.168.1.25/", "--name", "Regen"]), 0)

    def test_bridge_apply_requires_ownership_flag(self):
        with patch("hp_regen.bridge.install_queue", side_effect=AssertionError("must not install")), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["bridge", "ipp://192.168.1.25/", "--name", "Regen", "--apply"]), 2)
