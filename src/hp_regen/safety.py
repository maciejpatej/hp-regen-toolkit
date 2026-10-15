"""Small, explicit scope policy shared by every network entrypoint."""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import SplitResult, unquote, urlsplit

PRIVATE_RANGES = tuple(ipaddress.IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def private_ipv4(address: str) -> bool:
    try:
        ip = ipaddress.IPv4Address(address)
    except (ValueError, TypeError):
        return False
    return any(ip in network for network in PRIVATE_RANGES)


def validate_printer_uri(uri: str) -> SplitResult:
    if not isinstance(uri, str) or not uri or len(uri) > 1024:
        raise ValueError("Podaj URI IPP o długości do 1024 znaków.")
    if any(ord(char) < 33 or ord(char) > 126 for char in uri) or "\\" in uri:
        raise ValueError("URI musi zawierać wyłącznie widoczne znaki ASCII bez spacji.")
    try:
        parsed = urlsplit(uri)
        host = parsed.hostname
        port = 631 if parsed.port is None else parsed.port
        if parsed.scheme not in ("ipp", "ipps") or not host:
            raise ValueError("Obsługiwane są URI ipp:// lub ipps:// z adresem IPv4.")
        if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
            raise ValueError("URI nie może zawierać hasła, użytkownika, parametrów ani fragmentu.")
        address = ipaddress.IPv4Address(host)
        if not private_ipv4(str(address)) and str(address) != "127.0.0.1":
            raise ValueError("Dozwolony jest adres RFC1918 lub lokalny CUPS 127.0.0.1.")
        if port not in (631, 443):
            raise ValueError("Dozwolone porty IPP: 631 i 443.")
        # Reject encoded controls as well as literal controls before passing to HTTP.
        path = parsed.path or "/ipp/print"
        if not path.startswith("/") or path.startswith("//") or re.search(r"[\x00-\x20\x7f]", unquote(path)):
            raise ValueError("Nieprawidłowa ścieżka drukarki.")
        return SplitResult(parsed.scheme, f"{address}:{port}", path, "", "")
    except (ValueError, TypeError) as error:
        raise ValueError(str(error)) from None


def validate_subnet(cidr: str) -> ipaddress.IPv4Network:
    if not isinstance(cidr, str) or len(cidr) > 32:
        raise ValueError("Podaj prywatną podsieć IPv4, np. 192.168.1.0/24.")
    try:
        network = ipaddress.IPv4Network(cidr, strict=True)
    except ValueError:
        raise ValueError("Podaj adres sieci z maską, np. 192.168.1.0/24.") from None
    if network.num_addresses > 256 or not any(network.subnet_of(parent) for parent in PRIVATE_RANGES):
        raise ValueError("Skan obejmuje wyłącznie RFC1918, maksymalnie 256 adresów (/24).")
    return network
