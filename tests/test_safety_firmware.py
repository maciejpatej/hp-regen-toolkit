import hashlib
import unittest

from hp_regen.firmware import MAX_FIRMWARE_SIZE, preflight
from hp_regen.safety import validate_printer_uri, validate_subnet


class ScopeTests(unittest.TestCase):
    def test_private_addresses_and_normalization(self):
        for host in ("10.0.0.2", "172.16.1.2", "192.168.1.2", "127.0.0.1"):
            self.assertEqual(validate_printer_uri(f"ipp://{host}").geturl(), f"ipp://{host}:631/ipp/print")
        self.assertEqual(validate_printer_uri("ipps://192.168.1.2:443/ipp/print").port, 443)

    def test_rejects_external_names_credentials_and_header_controls(self):
        for uri in ("http://192.168.1.2/", "ipp://8.8.8.8/", "ipp://printer.local/", "ipp://user:password@192.168.1.2/", "ipp://169.254.169.254/", "ipp://[::1]/", "ipp://192.168.1.2:9100/", "ipp://192.168.1.2/?a=b", "ipp://192.168.1.2/#x", "ipp://192.168.1.2/%0d%0aX-Test:a", "ipp://192.168.1.2:0/", "ipp://192.168.1.2\\foo/"):
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                validate_printer_uri(uri)

    def test_subnets_are_strict_private_and_capped(self):
        self.assertEqual(validate_subnet("192.168.1.0/24").num_addresses, 256)
        for cidr in ("0.0.0.0/0", "192.168.0.0/16", "192.168.1.1/24", "8.8.8.0/24", "127.0.0.0/24", "10.0.0.0/23", None):
            with self.subTest(cidr=cidr), self.assertRaises(ValueError):
                validate_subnet(cidr)


class FirmwareTests(unittest.TestCase):
    def setUp(self):
        self.data = b"synthetic firmware fixture; never a printer image"
        self.manifest = {"schema_version": 1, "model": "Test exact model", "firmware_version": "test", "sha256": hashlib.sha256(self.data).hexdigest(), "size": len(self.data), "source_url": "https://example.org/image"}

    def test_matching_digest_never_enables_flash(self):
        result = preflight(self.manifest, self.data, self.manifest["model"])
        self.assertTrue(result["integrity_matches"])
        self.assertTrue(result["size_matches"])
        self.assertTrue(result["model_matches"])
        self.assertFalse(result["ready_to_flash"])
        self.assertEqual(result["authenticity"], "unverified")

    def test_mismatch_is_explicit(self):
        result = preflight({**self.manifest, "size": 100}, self.data + b"x", "Other model")
        self.assertFalse(result["model_matches"])
        self.assertFalse(result["integrity_matches"])
        self.assertFalse(result["size_matches"])

    def test_invalid_schema_and_size(self):
        for key, value in (("schema_version", True), ("schema_version", 2), ("size", True), ("size", 0), ("size", MAX_FIRMWARE_SIZE + 1), ("sha256", "xyz"), ("source_url", "http://example.org/image")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                preflight({**self.manifest, key: value}, self.data, self.manifest["model"])

    def test_model_match_is_exact_not_family_or_fuzzy(self):
        self.assertFalse(preflight(self.manifest, self.data, "Test exact model ")["model_matches"])

    def test_upload_bound(self):
        with self.assertRaises(ValueError):
            preflight(self.manifest, b"", self.manifest["model"])
        with self.assertRaises(ValueError):
            preflight(self.manifest, b"x" * (MAX_FIRMWARE_SIZE + 1), self.manifest["model"])
