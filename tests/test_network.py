"""Offline packet and transport tests; never contact a printer or LAN."""

import io
import ipaddress
import socket
import struct
import unittest
from unittest.mock import Mock, patch

from hp_regen import network


def rr(name, kind, value):
    return name + struct.pack("!HHIH", kind, 0x8001, 120, len(value)) + value


def dns_packet(address="192.168.7.20", port=631, host="office.local", txt=None):
    service = network._encode_dns_name("_ipp._tcp.local")
    instance = network._encode_dns_name("Office._ipp._tcp.local")
    hostname = network._encode_dns_name(host)
    pointer = lambda offset: struct.pack("!H", 0xC000 | offset)
    instance_offset = 12 + len(service) + 10
    ptr = rr(service, 12, instance)
    srv_offset = 12 + len(ptr) + 2 + 10 + 6
    srv = rr(pointer(instance_offset), 33, struct.pack("!HHH", 0, 0, port) + hostname)
    text = txt if txt is not None else b"".join(bytes((len(part),)) + part for part in (
        b"rp=ipp/print", b"ty=Office Printer", b"product=(Laser 1000)"
    ))
    records = ptr + srv + rr(pointer(instance_offset), 16, text)
    records += rr(pointer(srv_offset), 1, socket.inet_aton(address))
    return struct.pack("!6H", 0, 0x8400, 0, 4, 0, 0) + records


def ipp_response(request_id=7, attributes=(), status=0, ending=b"\x03"):
    message = struct.pack("!BBHI", 1, 1, status, request_id) + b"\x01"
    message += network._ipp_attribute(0x47, "attributes-charset", b"utf-8")
    message += network._ipp_attribute(0x48, "attributes-natural-language", b"en")
    message += b"\x04"
    for tag, name, value in attributes:
        message += network._ipp_attribute(tag, name, value)
    return message + ending


class DNSPacketTests(unittest.TestCase):
    def test_compressed_ptr_srv_a_and_txt_join(self):
        parsed = network._parse_dns_packet(dns_packet())
        devices = network._mdns_entries(parsed)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["uri"], "ipp://192.168.7.20:631/ipp/print")
        self.assertEqual(devices[0]["name"], "Office Printer")
        self.assertEqual(devices[0]["model"], "Laser 1000")

    def test_ipps_service_uses_advertised_port(self):
        # Rebuild without compression because insertion changes offsets.
        instance = network._encode_dns_name("Office._ipps._tcp.local")
        service = network._encode_dns_name("_ipps._tcp.local")
        host = network._encode_dns_name("office.local")
        body = rr(service, 12, instance) + rr(instance, 33, struct.pack("!HHH", 0, 0, 443) + host)
        body += rr(host, 1, socket.inet_aton("10.1.2.3"))
        packet = struct.pack("!6H", 0, 0x8400, 0, 3, 0, 0) + body
        self.assertEqual(network._mdns_entries(network._parse_dns_packet(packet))[0]["uri"], "ipps://10.1.2.3:443/ipp/print")

    def test_private_record_and_local_domain_are_required(self):
        for options in ({"address": "8.8.8.8"}, {"address": "127.0.0.1"},
                        {"address": "169.254.1.20"}, {"host": "office.attacker.test"},
                        {"port": 9100}):
            with self.subTest(options=options):
                self.assertEqual(network._mdns_entries(network._parse_dns_packet(dns_packet(**options))), [])

    def test_every_truncated_packet_prefix_fails(self):
        packet = dns_packet()
        for length in range(len(packet)):
            with self.subTest(length=length), self.assertRaises((ValueError, UnicodeError)):
                network._parse_dns_packet(packet[:length])

    def test_compression_cycle_and_out_of_range_pointer_fail(self):
        for name in (b"\xc0\x00", b"\xc0\x02\xc0\x00", b"\xff\xff", b"\xc0"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                network._dns_name(name, 0)

    def test_compression_depth_and_expanded_name_are_bounded(self):
        pointers = b"".join(struct.pack("!H", 0xC000 | ((n + 1) * 2)) for n in range(129)) + b"\x00"
        long_name = (b"\x3f" + b"a" * 63) * 4 + b"\x00"
        for name in (pointers, long_name):
            with self.assertRaises(ValueError):
                network._dns_name(name, 0)

    def test_instance_label_dots_and_utf8_round_trip(self):
        name = "Office\\.v2-日本._ipp._tcp.local"
        encoded = network._encode_dns_name(name)
        self.assertEqual(network._dns_name(encoded, 0), (name, len(encoded)))
        self.assertFalse(network._local_name("office\\.local"))
        self.assertTrue(network._local_name("office.local"))

    def test_discovery_device_limit_and_stable_ids(self):
        records = []
        for index in range(network.MAX_DISCOVERED_PRINTERS + 10):
            instance = f"office-{index}._ipp._tcp.local"
            hostname = f"office-{index}.local"
            records.extend([
                {"name": "_ipp._tcp.local", "type": 12, "value": instance},
                {"name": instance, "type": 33, "value": {"port": 631, "target": hostname}},
                {"name": hostname, "type": 1, "value": f"192.168.1.{index + 1}"},
            ])
        devices = network._mdns_entries(records)
        self.assertEqual(len(devices), network.MAX_DISCOVERED_PRINTERS)
        self.assertEqual(devices, network._mdns_entries(records))

    def test_duplicate_or_truncated_txt_fail(self):
        for text in (b"\x04rp=a\x04rp=b", b"\x05rp=x"):
            with self.assertRaises(ValueError):
                network._parse_dns_packet(dns_packet(txt=text))

    def test_oversized_packets_record_counts_and_trailing_data_fail(self):
        for packet in (b"x" * (network.MAX_DNS_PACKET + 1),
                       struct.pack("!6H", 0, 0x8000, 0, 257, 0, 0),
                       dns_packet() + b"junk"):
            with self.assertRaises(ValueError):
                network._parse_dns_packet(packet)

    def test_only_successful_response_packets_are_accepted(self):
        for flags in (0, 0x8003, 0x8800):
            packet = struct.pack("!6H", 0, flags, 0, 0, 0, 0)
            with self.assertRaises(ValueError):
                network._parse_dns_packet(packet)


class MDNSTransportTests(unittest.TestCase):
    def transport(self, responses):
        transport = Mock()
        transport.__enter__ = Mock(return_value=transport)
        transport.__exit__ = Mock(return_value=False)
        transport.recvfrom.side_effect = responses
        return transport

    def test_mocked_mdns_filters_sender_and_malformed_packets(self):
        transport = self.transport([
            (dns_packet(), ("8.8.8.8", 5353)),
            (dns_packet(), ("192.168.7.20", 9999)),
            (b"bad", ("192.168.7.20", 5353)),
            (dns_packet(), ("192.168.7.20", 5353)),
            socket.timeout(),
        ])
        with patch.object(network.socket, "socket", return_value=transport):
            devices = network.discover_mdns(0.5)
        self.assertEqual(len(devices), 1)
        transport.bind.assert_called_once_with(("", 0))
        query, destination = transport.sendto.call_args.args
        self.assertEqual(destination, network.MDNS_ADDRESS)
        self.assertIn(b"_ipp", query)
        self.assertIn(b"_ipps", query)

    def test_mdns_packet_budget_stops_flood(self):
        transport = self.transport([(b"bad", ("192.168.7.20", 5353))] * 1000)
        with patch.object(network.socket, "socket", return_value=transport):
            self.assertEqual(network.discover_mdns(1), [])
        self.assertEqual(transport.recvfrom.call_count, network.MAX_DISCOVERY_PACKETS)

    def test_mdns_requests_missing_srv_txt_and_address(self):
        name = network._encode_dns_name
        instance = "office._ipp._tcp.local"
        hostname = "office.local"
        packet = lambda body, count: struct.pack("!6H", 0, 0x8400, 0, count, 0, 0) + body
        responses = [
            (packet(rr(name("_ipp._tcp.local"), 12, name(instance)), 1), ("192.168.1.20", 5353)),
            (packet(rr(name(instance), 33, struct.pack("!HHH", 0, 0, 631) + name(hostname)), 1), ("192.168.1.20", 5353)),
            (packet(rr(name(hostname), 1, socket.inet_aton("192.168.1.20")), 1), ("192.168.1.20", 5353)),
            socket.timeout(),
        ]
        transport = self.transport(responses)
        with patch.object(network.socket, "socket", return_value=transport):
            devices = network.discover_mdns(1)
        self.assertEqual(len(devices), 1)
        self.assertEqual(transport.sendto.call_count, 4)  # Initial + SRV + TXT + A.
        query_types = [struct.unpack("!HH", call.args[0][-4:])[0] for call in transport.sendto.call_args_list[1:]]
        self.assertEqual(sorted(query_types), [1, 16, 33])

    def test_mdns_followup_query_budget_stops_advertisement_flood(self):
        records = b"".join(rr(network._encode_dns_name("_ipp._tcp.local"), 12,
                              network._encode_dns_name(f"office-{n}._ipp._tcp.local")) for n in range(80))
        packet = struct.pack("!6H", 0, 0x8400, 0, 80, 0, 0) + records
        transport = self.transport([(packet, ("192.168.1.20", 5353)), socket.timeout()])
        with patch.object(network.socket, "socket", return_value=transport):
            self.assertEqual(network.discover_mdns(1), [])
        self.assertEqual(transport.sendto.call_count, network.MAX_DISCOVERY_QUERIES + 1)

    def test_timeout_validation_precedes_socket(self):
        with patch.object(network.socket, "socket") as constructor:
            for timeout in (0, -1, 11, float("nan"), float("inf")):
                with self.assertRaises(ValueError):
                    network.discover_mdns(timeout)
        constructor.assert_not_called()


class IPPPacketTests(unittest.TestCase):
    def test_request_is_only_get_printer_attributes(self):
        data = network._build_ipp_request("ipp://192.168.1.2:631/ipp/print", 7)
        self.assertEqual(struct.unpack("!BBHI", data[:8]), (1, 1, 0x000B, 7))
        self.assertTrue(data.endswith(b"\x03"))
        self.assertIn(b"requested-attributes", data)
        self.assertIn(b"printer-uri", data)

    def test_typed_response_and_repeated_values(self):
        packet = ipp_response(attributes=[
            (0x42, "printer-name", b"Office"),
            (0x23, "printer-state", struct.pack("!i", 3)),
            (0x22, "color-supported", b"\x01"),
            (0x49, "document-format-supported", b"application/pdf"),
            (0x49, "", b"image/pwg-raster"),
        ])
        attributes, status = network._parse_ipp_response(packet, 7)
        self.assertEqual(status, 0)
        self.assertEqual(attributes["printer-state"], [3])
        self.assertEqual(attributes["color-supported"], [True])
        self.assertEqual(attributes["document-format-supported"], ["application/pdf", "image/pwg-raster"])

    def test_error_and_mismatched_request_id_fail(self):
        for packet in (ipp_response(request_id=9), ipp_response(status=0x0401), ipp_response(status=0x00FF)):
            with self.assertRaises(ValueError):
                network._parse_ipp_response(packet, 7)

    def test_unsupported_version_and_collection_fail(self):
        unsupported = b"\x03\x00" + ipp_response()[2:]
        collection = ipp_response(attributes=[(0x34, "media-col", b"")])
        for packet in (unsupported, collection):
            with self.assertRaises(ValueError):
                network._parse_ipp_response(packet, 7)

    def test_truncated_response_and_document_payload_fail(self):
        valid = ipp_response(attributes=[(0x42, "printer-name", b"Office")])
        for packet in (valid[:-1], valid[:-3], valid + b"document"):
            with self.assertRaises(ValueError):
                network._parse_ipp_response(packet, 7)

    def test_invalid_scalar_and_missing_name_fail(self):
        for attribute in ((0x23, "printer-state", b"\x00"),
                          (0x22, "color-supported", b"\x02"),
                          (0x44, "", b"unnamed"),
                          (0x42, "bad name", b"x"),
                          (0x13, "firmware", b"nonempty")):
            with self.assertRaises(ValueError):
                network._parse_ipp_response(ipp_response(attributes=[attribute]), 7)

    def test_response_value_and_attribute_limits(self):
        oversized_value = ipp_response(attributes=[(0x42, "printer-name", b"a" * 4097)])
        repeated = ipp_response(attributes=[(0x44, "values", b"a")] + [(0x44, "", b"a")] * 512)
        names = ipp_response(attributes=[(0x44, f"attr-{i}", b"a") for i in range(256)])
        for packet in (oversized_value, repeated, names, b"a" * (network.MAX_IPP_RESPONSE + 1)):
            with self.assertRaises(ValueError):
                network._parse_ipp_response(packet, 7)

    def test_charset_is_required_and_bounded(self):
        no_charset = struct.pack("!BBHI", 1, 1, 0, 7) + b"\x04\x03"
        bad_charset = ipp_response().replace(b"utf-8", b"other")
        for packet in (no_charset, bad_charset):
            with self.assertRaises(ValueError):
                network._parse_ipp_response(packet, 7)

    def test_language_and_octet_values_preserve_typed_information(self):
        localized = struct.pack("!H", 2) + b"en" + struct.pack("!H", 6) + b"Office"
        self.assertEqual(network._ipp_value(0x36, localized), {"language": "en", "text": "Office"})
        self.assertEqual(network._ipp_value(0x30, b"\x00\x10"), {"hex": "0010"})
        with self.assertRaises(ValueError):
            network._ipp_value(0x36, localized[:-1])


class IPPTransportTests(unittest.TestCase):
    def make_connection(self, attributes=(), headers=None, status=200, data=None):
        connection = Mock()
        response = Mock()
        response.status = status
        header_values = {"Content-Type": "application/ipp"}
        if headers:
            header_values.update(headers)
        response.getheader.side_effect = lambda name, default=None: header_values.get(name, default)

        def read(_limit):
            request = connection.request.call_args.kwargs["body"]
            returned_id = struct.unpack("!I", request[4:8])[0]
            return data if data is not None else ipp_response(returned_id, attributes)

        response.read.side_effect = read
        connection.getresponse.return_value = response
        return connection, response

    def test_direct_http_inspection_and_unknown_firmware(self):
        connection, _ = self.make_connection(attributes=[
            (0x42, "printer-name", b"Office"),
            (0x41, "printer-make-and-model", b"Laser 1000"),
            (0x23, "printer-state", struct.pack("!i", 3)),
        ])
        with patch.object(network.http.client, "HTTPConnection", return_value=connection) as constructor:
            result = network.inspect_printer("ipp://192.168.1.20/ipp/print", 0.5)
        constructor.assert_called_once_with("192.168.1.20", 631, timeout=0.5)
        self.assertEqual(result["name"], "Office")
        self.assertEqual(result["state"], "idle")
        self.assertEqual(result["firmware"], "unknown")
        self.assertTrue(any("nieznana" in item for item in result["findings"]))
        args = connection.request.call_args
        self.assertEqual(args.args, ("POST", "/ipp/print"))
        self.assertIn(b"ipp://192.168.1.20:631/ipp/print", args.kwargs["body"])
        connection.close.assert_called_once()

    def test_localized_name_model_and_firmware_survive_real_ipp_parsing(self):
        def localized(text):
            encoded = text.encode("utf-8")
            return struct.pack("!H", 2) + b"pl" + struct.pack("!H", len(encoded)) + encoded

        connection, _ = self.make_connection(attributes=[
            (0x36, "printer-name", localized("Biuro Łódź")),
            (0x35, "printer-make-and-model", localized("Drukarka próbna")),
            (0x35, "printer-firmware-string-version", localized("Wersja 1.2.3")),
        ])
        with patch.object(network.http.client, "HTTPConnection", return_value=connection):
            result = network.inspect_printer("ipp://192.168.1.20/ipp/print", 0.5)
        self.assertEqual(result["name"], "Biuro Łódź")
        self.assertEqual(result["model"], "Drukarka próbna")
        self.assertEqual(result["firmware"], "Wersja 1.2.3")
        self.assertEqual(result["attributes"]["printer-name"], [{"language": "pl", "text": "Biuro Łódź"}])
        self.assertFalse(any("nieznana" in item for item in result["findings"]))

    def test_display_does_not_coerce_other_dictionary_values(self):
        self.assertEqual(network._display({"language": "pl", "text": 123}), "unknown")
        self.assertEqual(network._display({"hex": "01020304"}), "unknown")

    def test_ipps_uses_certificate_verification_and_default_631(self):
        connection, _ = self.make_connection(attributes=[(0x41, "printer-firmware-string-version", b"1.2.3")])
        with patch.object(network.http.client, "HTTPSConnection", return_value=connection) as constructor:
            result = network.inspect_printer("ipps://192.168.1.20/ipp/print", 0.5)
        self.assertEqual(constructor.call_args.args, ("192.168.1.20", 631))
        self.assertEqual(constructor.call_args.kwargs["context"].verify_mode, 2)
        self.assertTrue(constructor.call_args.kwargs["context"].check_hostname)
        self.assertEqual(result["firmware"], "1.2.3")

    def test_no_network_for_external_hostname_credentials_or_port(self):
        with patch.object(network.http.client, "HTTPConnection") as constructor:
            for uri in ("ipp://8.8.8.8/ipp/print", "ipp://printer.local/ipp/print",
                        "ipp://user:password@192.168.1.2/ipp/print", "ipp://192.168.1.2:9100/ipp/print",
                        "http://192.168.1.2/ipp/print"):
                with self.subTest(uri=uri), self.assertRaises(ValueError):
                    network.inspect_printer(uri)
        constructor.assert_not_called()

    def test_redirect_content_type_and_oversized_headers_are_rejected(self):
        cases = ({"status": 302}, {"headers": {"Content-Type": "text/html"}},
                 {"headers": {"Content-Length": str(network.MAX_IPP_RESPONSE + 1)}},
                 {"headers": {"Content-Length": "-1"}},
                 {"headers": {"Content-Length": "3", "Transfer-Encoding": "chunked"}},
                 {"headers": {"Transfer-Encoding": "gzip"}})
        for options in cases:
            connection, response = self.make_connection(**options)
            with self.subTest(options=options), patch.object(network.http.client, "HTTPConnection", return_value=connection):
                with self.assertRaises(ValueError):
                    network.inspect_printer("ipp://192.168.1.20/ipp/print", 0.5)
            response.read.assert_not_called()
            connection.close.assert_called_once()

    def test_oversized_body_and_length_mismatch_are_rejected(self):
        cases = ({"data": b"x" * (network.MAX_IPP_RESPONSE + 1)},
                 {"headers": {"Content-Length": "1"}})
        for options in cases:
            connection, _ = self.make_connection(**options)
            with patch.object(network.http.client, "HTTPConnection", return_value=connection), self.assertRaises(ValueError):
                network.inspect_printer("ipp://192.168.1.20/ipp/print", 0.5)

    def test_header_line_and_total_size_limits(self):
        stream = network._HeaderLimitedFile(io.BytesIO(b"x" * 8193 + b"\n"))
        with self.assertRaises(ValueError):
            stream.readline(65537)
        stream = network._HeaderLimitedFile(io.BytesIO((b"x" * 4095 + b"\n") * 17))
        for _ in range(16):
            stream.readline()
        with self.assertRaises(ValueError):
            stream.readline()

    def test_firmware_octets_are_not_misrepresented_as_readable_version(self):
        connection, _ = self.make_connection(attributes=[(0x30, "printer-firmware-version", b"\x01\x02\x03\x04")])
        with patch.object(network.http.client, "HTTPConnection", return_value=connection):
            result = network.inspect_printer("ipp://192.168.1.20/ipp/print", 0.5)
        self.assertEqual(result["firmware"], "unknown")
        self.assertEqual(result["attributes"]["printer-firmware-version"], [{"hex": "01020304"}])

    def test_wrong_type_state_remains_unknown(self):
        connection, _ = self.make_connection(attributes=[(0x30, "printer-state", b"\x01\x02")])
        with patch.object(network.http.client, "HTTPConnection", return_value=connection):
            result = network.inspect_printer("ipp://192.168.1.20/ipp/print", 0.5)
        self.assertEqual(result["state"], "unknown")

    def test_connection_failure_is_reported_without_credentials(self):
        connection, _ = self.make_connection()
        connection.connect.side_effect = socket.timeout("private details")
        with patch.object(network.http.client, "HTTPConnection", return_value=connection), self.assertRaisesRegex(ValueError, "TimeoutError"):
            network.inspect_printer("ipp://192.168.1.20/ipp/print", 0.5)
        connection.close.assert_called_once()


class SubnetTests(unittest.TestCase):
    def test_scoped_scan_only_inspects_hosts_and_ignores_failures(self):
        def inspect(uri, timeout):
            if ".2:" in uri:
                raise ValueError("not a printer")
            return {"name": "Office", "model": "Laser"}

        with patch.object(network, "inspect_printer", side_effect=inspect) as inspect_mock:
            entries = network.scan_subnet("192.168.1.0/30", 0.5)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["uri"], "ipp://192.168.1.1:631/ipp/print")
        self.assertEqual(inspect_mock.call_count, 2)

    def test_scope_validation_precedes_all_inspection(self):
        with patch.object(network, "inspect_printer") as inspect:
            for subnet in ("8.8.8.0/24", "10.0.0.0/16", "127.0.0.0/24", "192.168.1.1/24"):
                with self.assertRaises(ValueError):
                    network.scan_subnet(subnet)
        inspect.assert_not_called()

    def test_defensive_host_limit_survives_overbroad_validator(self):
        with patch.object(network, "validate_subnet", return_value=ipaddress.ip_network("10.0.0.0/16")), patch.object(network, "inspect_printer") as inspect:
            with self.assertRaises(ValueError):
                network.scan_subnet("10.0.0.0/16")
        inspect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
