"""Bounded, read-only discovery and IPP inspection for explicitly owned printers.

No print jobs, vendor control languages, authentication or firmware writes are
implemented here. Discovery data and printer responses are always untrusted.
"""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import math
import re
import secrets
import socket
import ssl
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from .safety import validate_printer_uri, validate_subnet


MAX_DNS_PACKET = 9000
MAX_DNS_RECORDS = 256
MAX_DISCOVERY_PACKETS = 128
MAX_DISCOVERY_QUERIES = 32
MAX_DISCOVERY_RECORDS = 1024
MAX_DISCOVERED_PRINTERS = 128
MAX_IPP_RESPONSE = 1024 * 1024
MAX_IPP_ATTRIBUTES = 256
MAX_IPP_VALUES = 512
MAX_IPP_VALUE_BYTES = 4096
MDNS_ADDRESS = ("224.0.0.251", 5353)
SERVICES = ("_ipp._tcp.local", "_ipps._tcp.local")
_PRIVATE_NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"
))
_ATTR_NAME = re.compile(r"[a-z][a-z0-9-]{0,254}\Z")
_REQUESTED_ATTRIBUTES = (
    "printer-name", "printer-make-and-model", "printer-state",
    "printer-state-reasons", "ipp-versions-supported", "operations-supported",
    "document-format-supported", "uri-authentication-supported",
    "uri-security-supported", "printer-firmware-name",
    "printer-firmware-version", "printer-firmware-string-version",
)


def _timeout(value: float) -> float:
    value = float(value)
    if not math.isfinite(value) or not 0 < value <= 10:
        raise ValueError("timeout must be finite and between 0 and 10 seconds")
    return value


def _is_private_ipv4(value: str) -> bool:
    try:
        address = ipaddress.IPv4Address(value)
    except (ipaddress.AddressValueError, TypeError):
        return False
    return any(address in network for network in _PRIVATE_NETWORKS)


def _display(value: object, fallback: str = "unknown") -> str:
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        value = value["text"]
    if not isinstance(value, str):
        return fallback
    clean = "".join(c for c in value if c.isprintable()).strip()[:256]
    return clean or fallback


def _entry(uri: str, name: str, source: str, model: str = "unknown") -> dict:
    return {
        "id": hashlib.sha256(uri.encode("utf-8")).hexdigest()[:16],
        "name": _display(name), "uri": uri, "source": source,
        "model": _display(model),
    }


def _dns_name(packet: bytes, start: int) -> tuple[str, int]:
    """Read a compressed DNS name with cycle, label and total-length limits."""
    labels: list[str] = []
    position = start
    end = None
    visited: set[int] = set()
    expanded_size = 1
    for _ in range(128):
        if position >= len(packet) or position in visited:
            raise ValueError("truncated or cyclic DNS name")
        visited.add(position)
        length = packet[position]
        if length & 0xC0 == 0xC0:
            if position + 1 >= len(packet):
                raise ValueError("truncated DNS pointer")
            target = ((length & 0x3F) << 8) | packet[position + 1]
            if target >= len(packet):
                raise ValueError("DNS pointer outside packet")
            if end is None:
                end = position + 2
            position = target
            continue
        if length & 0xC0:
            raise ValueError("unsupported DNS label encoding")
        position += 1
        if length == 0:
            return ".".join(labels), end if end is not None else position
        if length > 63 or position + length > len(packet):
            raise ValueError("invalid DNS label")
        expanded_size += length + 1
        if expanded_size > 255:
            raise ValueError("DNS name exceeds 255 bytes")
        label = packet[position:position + length].decode("utf-8", "strict")
        if any(ord(c) < 32 or ord(c) == 127 for c in label):
            raise ValueError("unsafe DNS label")
        # Preserve label boundaries in presentation form (DNS-SD instance
        # labels may contain literal dots and backslashes).
        labels.append(label.replace("\\", "\\\\").replace(".", "\\."))
        position += length
    raise ValueError("DNS pointer depth exceeded")


def _parse_dns_packet(packet: bytes) -> list[dict]:
    if not 12 <= len(packet) <= MAX_DNS_PACKET:
        raise ValueError("invalid DNS packet size")
    _, flags, questions, answers, authorities, additional = struct.unpack("!6H", packet[:12])
    if not flags & 0x8000 or flags & 0x780F:
        raise ValueError("not a successful DNS response")
    count = answers + authorities + additional
    if questions > 32 or count > MAX_DNS_RECORDS:
        raise ValueError("too many DNS records")
    position = 12
    for _ in range(questions):
        _, position = _dns_name(packet, position)
        if position + 4 > len(packet):
            raise ValueError("truncated DNS question")
        position += 4
    records = []
    for _ in range(count):
        name, position = _dns_name(packet, position)
        if position + 10 > len(packet):
            raise ValueError("truncated DNS record")
        kind, klass, ttl, size = struct.unpack("!HHIH", packet[position:position + 10])
        position += 10
        end = position + size
        if end > len(packet):
            raise ValueError("truncated DNS record data")
        value = None
        if klass & 0x7FFF == 1 and ttl:
            if kind == 1:
                if size != 4:
                    raise ValueError("invalid DNS A record")
                value = socket.inet_ntoa(packet[position:end])
            elif kind == 12:
                value, consumed = _dns_name(packet, position)
                if consumed != end:
                    raise ValueError("invalid DNS PTR record length")
            elif kind == 33:
                if size < 7:
                    raise ValueError("invalid DNS SRV record")
                _, _, port = struct.unpack("!HHH", packet[position:position + 6])
                target, consumed = _dns_name(packet, position + 6)
                if consumed != end:
                    raise ValueError("invalid DNS SRV record length")
                value = {"port": port, "target": target}
            elif kind == 16:
                value = {}
                cursor = position
                while cursor < end:
                    length = packet[cursor]
                    cursor += 1
                    if cursor + length > end:
                        raise ValueError("truncated DNS TXT entry")
                    part = packet[cursor:cursor + length].decode("utf-8", "strict")
                    cursor += length
                    key, separator, text = part.partition("=")
                    key = key.lower()
                    if key in value:
                        raise ValueError("duplicate DNS TXT key")
                    if key and len(key) <= 64:
                        value[key] = text if separator else ""
            if value is not None:
                records.append({"name": name.lower(), "type": kind, "value": value})
        position = end
    if position != len(packet):
        raise ValueError("trailing DNS data")
    return records


def _encode_dns_name(name: str) -> bytes:
    labels, current, escaped = [], [], False
    for character in name:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ".":
            labels.append("".join(current).encode("utf-8"))
            current = []
        else:
            current.append(character)
    if escaped:
        raise ValueError("incomplete DNS name escape")
    labels.append("".join(current).encode("utf-8"))
    if any(not 0 < len(label) <= 63 for label in labels) or sum(len(label) + 1 for label in labels) + 1 > 255:
        raise ValueError("invalid DNS name for query")
    return b"".join(bytes((len(label),)) + label for label in labels) + b"\x00"


def _local_name(name: str) -> bool:
    # An escaped literal dot is part of a label, not a .local suffix.
    if not name.endswith(".local"):
        return False
    index = len(name) - len(".local") - 1
    backslashes = 0
    while index >= 0 and name[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 0


def _followup_questions(records: list[dict]) -> set[tuple[str, int]]:
    known = {(r["name"], r["type"]) for r in records}
    instances = {r["value"].lower() for r in records if r["type"] == 12
                 and r["name"] in SERVICES and r["value"].lower().endswith("." + r["name"])}
    questions = {(instance, kind) for instance in instances for kind in (33, 16)
                 if (instance, kind) not in known}
    for record in records:
        if record["type"] == 33 and record["name"] in instances:
            target = record["value"]["target"].lower()
            if _local_name(target) and (target, 1) not in known:
                questions.add((target, 1))
    return questions


def _mdns_entries(records: list[dict]) -> list[dict]:
    """Only join service PTR -> instance SRV -> literal private A records."""
    addresses: dict[str, set[str]] = {}
    servers: dict[str, list[dict]] = {}
    texts: dict[str, dict] = {}
    instances: set[tuple[str, str]] = set()
    for record in records[:MAX_DISCOVERY_RECORDS]:
        name, kind, value = record["name"], record["type"], record["value"]
        if kind == 1 and _local_name(name) and _is_private_ipv4(value):
            addresses.setdefault(name, set()).add(value)
        elif kind == 33 and _local_name(name) and _local_name(value["target"].lower()):
            servers.setdefault(name, []).append(value)
        elif kind == 16:
            texts[name] = value
        elif kind == 12 and name in SERVICES:
            instance = value.lower()
            if instance.endswith("." + name):
                instances.add((name, instance))
    results: dict[str, dict] = {}
    for service, instance in sorted(instances):
        text = texts.get(instance, {})
        path = text.get("rp", "ipp/print")
        if not path or len(path) > 1024 or any(not c.isprintable() for c in path):
            continue
        path = "/" + path.lstrip("/")
        scheme = "ipps" if service == SERVICES[1] else "ipp"
        for server in servers.get(instance, []):
            if server["port"] not in (631, 443):
                continue
            for address in sorted(addresses.get(server["target"].lower(), set())):
                uri = f"{scheme}://{address}:{server['port']}{quote(path, safe='/-._~')}"
                try:
                    validate_printer_uri(uri)
                except ValueError:
                    continue
                name = text.get("ty") or instance[:-(len(service) + 1)].replace("\\.", ".").replace("\\\\", "\\")
                results[uri] = _entry(uri, name, "mdns", text.get("product", "unknown").strip("()"))
                if len(results) >= MAX_DISCOVERED_PRINTERS:
                    return sorted(results.values(), key=lambda e: e["uri"])
    return sorted(results.values(), key=lambda e: e["uri"])


def discover_mdns(timeout: float = 3.0) -> list[dict]:
    """Browse local IPP/IPPS DNS-SD with finite packet/time/device limits.

    An ephemeral source port requests legacy unicast mDNS replies, avoiding
    taking over the operating system's mDNS listener on port 5353.
    """
    timeout = _timeout(timeout)
    query = struct.pack("!6H", 0, 0, 2, 0, 0, 0)
    query += b"".join(_encode_dns_name(name) + struct.pack("!HH", 12, 0x8001) for name in SERVICES)
    records: list[dict] = []
    sent_questions: set[tuple[str, int]] = set()
    deadline = time.monotonic() + timeout
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as transport:
        transport.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        transport.bind(("", 0))
        transport.sendto(query, MDNS_ADDRESS)
        for _ in range(MAX_DISCOVERY_PACKETS):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or len(records) >= MAX_DISCOVERY_RECORDS:
                break
            transport.settimeout(remaining)
            try:
                packet, source = transport.recvfrom(MAX_DNS_PACKET + 1)
            except socket.timeout:
                break
            if not _is_private_ipv4(source[0]) or source[1] != 5353:
                continue
            try:
                parsed = _parse_dns_packet(packet)
            except (ValueError, UnicodeError, struct.error):
                continue
            records.extend(parsed[:MAX_DISCOVERY_RECORDS - len(records)])
            # Some devices return only PTR initially. Request missing service
            # metadata/address records, while retaining a strict query budget.
            for name, kind in sorted(_followup_questions(records) - sent_questions):
                remaining = deadline - time.monotonic()
                if len(sent_questions) >= MAX_DISCOVERY_QUERIES or remaining <= 0:
                    break
                question = struct.pack("!6H", 0, 0, 1, 0, 0, 0)
                question += _encode_dns_name(name) + struct.pack("!HH", kind, 0x8001)
                transport.settimeout(remaining)
                try:
                    transport.sendto(question, MDNS_ADDRESS)
                except socket.timeout:
                    break
                sent_questions.add((name, kind))
    return _mdns_entries(records)


def _ipp_attribute(tag: int, name: str, value: bytes) -> bytes:
    encoded_name = name.encode("ascii")
    return bytes((tag,)) + struct.pack("!H", len(encoded_name)) + encoded_name + struct.pack("!H", len(value)) + value


def _build_ipp_request(uri: str, request_id: int) -> bytes:
    message = struct.pack("!BBHI", 1, 1, 0x000B, request_id) + b"\x01"
    message += _ipp_attribute(0x47, "attributes-charset", b"utf-8")
    message += _ipp_attribute(0x48, "attributes-natural-language", b"en")
    message += _ipp_attribute(0x45, "printer-uri", uri.encode("ascii"))
    for index, attribute in enumerate(_REQUESTED_ATTRIBUTES):
        message += _ipp_attribute(0x44, "requested-attributes" if index == 0 else "", attribute.encode("ascii"))
    return message + b"\x03"


def _ipp_value(tag: int, data: bytes) -> object:
    if tag in (0x10, 0x12, 0x13, 0x15, 0x16, 0x17):
        if data:
            raise ValueError("IPP out-of-band value must be empty")
        return None
    if tag in (0x21, 0x23):
        if len(data) != 4:
            raise ValueError("invalid IPP integer length")
        return struct.unpack("!i", data)[0]
    if tag == 0x22:
        if data not in (b"\x00", b"\x01"):
            raise ValueError("invalid IPP boolean")
        return data == b"\x01"
    if tag in (0x41, 0x42, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49):
        return data.decode("utf-8", "strict")
    if tag in (0x35, 0x36):
        if len(data) < 4:
            raise ValueError("truncated IPP language value")
        language_length = struct.unpack("!H", data[:2])[0]
        split = 2 + language_length
        if split + 2 > len(data):
            raise ValueError("truncated IPP language value")
        language = data[2:split].decode("ascii", "strict")
        text_length = struct.unpack("!H", data[split:split + 2])[0]
        if split + 2 + text_length != len(data):
            raise ValueError("invalid IPP language value length")
        return {"language": language, "text": data[split + 2:].decode("utf-8", "strict")}
    if tag == 0x33:
        if len(data) != 8:
            raise ValueError("invalid IPP range length")
        return list(struct.unpack("!ii", data))
    if tag == 0x32:
        if len(data) != 9 or data[8] not in (3, 4):
            raise ValueError("invalid IPP resolution")
        x, y, unit = struct.unpack("!iiB", data)
        return {"x": x, "y": y, "unit": "dpi" if unit == 3 else "dpcm"}
    if tag in (0x30, 0x31):
        if tag == 0x31 and len(data) != 11:
            raise ValueError("invalid IPP date length")
        return {"hex": data.hex()}
    raise ValueError(f"unsupported IPP value tag 0x{tag:02x}")


def _parse_ipp_response(data: bytes, request_id: int) -> tuple[dict, int]:
    if not 9 <= len(data) <= MAX_IPP_RESPONSE:
        raise ValueError("invalid IPP response size")
    major, minor, status, returned_id = struct.unpack("!BBHI", data[:8])
    if (major, minor) not in ((1, 0), (1, 1), (2, 0), (2, 1), (2, 2)):
        raise ValueError("unsupported IPP response version")
    if returned_id != request_id:
        raise ValueError("IPP request-id mismatch")
    if status > 0x00FF:
        raise ValueError(f"printer returned IPP error 0x{status:04x}")
    if status not in (0x0000, 0x0001, 0x0002):
        raise ValueError(f"unsupported IPP success status 0x{status:04x}")
    position, group, previous_name, values = 8, None, None, 0
    attributes: dict[str, list] = {}
    while position < len(data):
        tag = data[position]
        position += 1
        if tag == 0x03:
            if position != len(data):
                raise ValueError("unexpected IPP document payload")
            if attributes.get("attributes-charset") not in (["utf-8"], ["us-ascii"]):
                raise ValueError("missing or unsupported IPP response charset")
            return attributes, status
        if tag < 0x10:
            if tag not in (0x01, 0x02, 0x04, 0x05, 0x06, 0x07, 0x09):
                raise ValueError("unsupported IPP attribute group")
            group, previous_name = tag, None
            continue
        if group is None or position + 2 > len(data):
            raise ValueError("IPP attribute outside a group or truncated")
        name_length = struct.unpack("!H", data[position:position + 2])[0]
        position += 2
        if name_length > 255 or position + name_length + 2 > len(data):
            raise ValueError("invalid IPP attribute name length")
        if name_length:
            name = data[position:position + name_length].decode("ascii", "strict")
            if not _ATTR_NAME.fullmatch(name):
                raise ValueError("invalid IPP attribute name")
            previous_name = name
        elif previous_name is None:
            raise ValueError("IPP repeated value has no preceding name")
        name = previous_name
        position += name_length
        value_length = struct.unpack("!H", data[position:position + 2])[0]
        position += 2
        if value_length > MAX_IPP_VALUE_BYTES or position + value_length > len(data):
            raise ValueError("invalid IPP attribute value length")
        values += 1
        if values > MAX_IPP_VALUES or (name not in attributes and len(attributes) >= MAX_IPP_ATTRIBUTES):
            raise ValueError("too many IPP attributes or values")
        value = _ipp_value(tag, data[position:position + value_length])
        attributes.setdefault(name, []).append(value)
        position += value_length
    raise ValueError("IPP response has no end-of-attributes marker")


class _HeaderLimitedFile:
    """Limit line-oriented response headers in addition to stdlib limits."""

    def __init__(self, stream):
        self.stream = stream
        self.line_bytes = 0

    def readline(self, limit=-1):
        result = self.stream.readline(min(limit, 8193) if limit >= 0 else 8193)
        self.line_bytes += len(result)
        if len(result) > 8192 or self.line_bytes > 65536:
            raise ValueError("HTTP response headers exceed limits")
        return result

    def __getattr__(self, name):
        return getattr(self.stream, name)


class _BoundedHTTPResponse(http.client.HTTPResponse):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fp = _HeaderLimitedFile(self.fp)


def _read_ipp_http(parsed, payload: bytes, timeout: float) -> bytes:
    """Direct HTTP client: literal host, no proxy, redirect or auth handling."""
    host = parsed.hostname
    port = parsed.port or 631
    if parsed.scheme == "ipps":
        connection = http.client.HTTPSConnection(host, port, timeout=timeout, context=ssl.create_default_context())
    else:
        connection = http.client.HTTPConnection(host, port, timeout=timeout)
    connection.response_class = _BoundedHTTPResponse
    deadline = time.monotonic() + timeout
    timer = None

    def abort_transport(transport):
        try:
            transport.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    try:
        connection.connect()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("printer inspection timed out")
        connection.sock.settimeout(remaining)
        timer = threading.Timer(remaining, abort_transport, (connection.sock,))
        timer.daemon = True
        timer.start()
        connection.request("POST", parsed.path or "/ipp/print", body=payload, headers={
            "Content-Type": "application/ipp", "Accept": "application/ipp",
            "User-Agent": "HP-Regen-Toolkit/0.1", "Connection": "close",
        })
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"printer returned HTTP {response.status}; redirects are not followed")
        if response.getheader("Content-Type", "").split(";", 1)[0].strip().lower() != "application/ipp":
            raise ValueError("printer did not return application/ipp")
        length = response.getheader("Content-Length")
        encoding = response.getheader("Transfer-Encoding")
        if encoding is not None and (encoding.strip().lower() != "chunked" or length is not None):
            raise ValueError("unsupported or ambiguous HTTP response framing")
        if length is not None and (not length.isdecimal() or int(length) > MAX_IPP_RESPONSE):
            raise ValueError("invalid or excessive HTTP Content-Length")
        result = response.read(MAX_IPP_RESPONSE + 1)
        if len(result) > MAX_IPP_RESPONSE:
            raise ValueError("IPP response exceeds size limit")
        if length is not None and len(result) != int(length):
            raise ValueError("HTTP response body length mismatch")
        if time.monotonic() >= deadline:
            raise TimeoutError("printer inspection timed out")
        return result
    finally:
        if timer is not None:
            timer.cancel()
        connection.close()


def inspect_printer(uri: str, timeout: float = 2.0) -> dict:
    parsed = validate_printer_uri(uri)  # Scope validation precedes all networking.
    timeout = _timeout(timeout)
    request_id = secrets.randbelow(0x7FFFFFFF) + 1
    payload = _build_ipp_request(parsed.geturl(), request_id)
    try:
        raw = _read_ipp_http(parsed, payload, timeout)
        attributes, status = _parse_ipp_response(raw, request_id)
    except (OSError, http.client.HTTPException) as exc:
        raise ValueError(f"IPP connection failed: {type(exc).__name__}") from exc
    findings = []
    if parsed.scheme == "ipp":
        findings.append("To połączenie jest nieszyfrowane; IPPS z zaufanym certyfikatem chroni transmisję.")
    if status:
        findings.append(f"Drukarka zgłosiła pomyślny status IPP 0x{status:04x}; część żądanych atrybutów może być nieobsługiwana.")

    def first(name, default="unknown"):
        entries = attributes.get(name, [])
        return entries[0] if entries else default

    firmware = _display(first("printer-firmware-string-version"))
    if firmware == "unknown":
        findings.append("Wersja firmware jest nieznana: drukarka nie podała czytelnego atrybutu wersji firmware.")
    state = first("printer-state")
    return {
        "uri": uri, "name": _display(first("printer-name"), parsed.hostname),
        "model": _display(first("printer-make-and-model")),
        "state": {3: "idle", 4: "processing", 5: "stopped"}.get(state, "unknown") if isinstance(state, int) else "unknown",
        "reasons": [_display(v) for v in attributes.get("printer-state-reasons", []) if isinstance(v, str)],
        "firmware": firmware,
        "capabilities": {
            "document_formats": attributes.get("document-format-supported", []),
            "ipp_versions": attributes.get("ipp-versions-supported", []),
            "operations": attributes.get("operations-supported", []),
        },
        "attributes": attributes, "findings": findings,
    }


def scan_subnet(cidr: str, timeout: float = 1.0) -> list[dict]:
    """Explicit RFC1918 scan, capped by safety at /24 and eight workers.

    Ownership acknowledgement is enforced by the UI/CLI before calling this
    API. Each host receives only Get-Printer-Attributes on port 631; no jobs.
    """
    network = validate_subnet(cidr)  # Scope validation precedes all networking.
    timeout = _timeout(timeout)
    if network.num_addresses > 256:
        raise ValueError("subnet scan is limited to 256 addresses")
    hosts = [str(address) for address in network.hosts()]

    def inspect_host(address):
        uri = f"ipp://{address}:631/ipp/print"
        try:
            device = inspect_printer(uri, timeout)
        except (ValueError, OSError, UnicodeError, struct.error):
            return None
        return _entry(uri, device["name"], "subnet", device["model"])

    with ThreadPoolExecutor(max_workers=8) as pool:
        entries = list(pool.map(inspect_host, hosts))
    return sorted((entry for entry in entries if entry is not None), key=lambda e: e["uri"])
