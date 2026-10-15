"""CLI entry points for the same local workbench modules."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .firmware import MAX_FIRMWARE_SIZE, preflight


def emit(value):
    print(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hp-regen", description="Lokalny warsztat odzyskiwania drukarek; firmware wyłącznie offline.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    web = commands.add_parser("serve", help="Lokalny panel; start nie wykonuje skanu")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--demo", action="store_true", help="Symulowane dane bez operacji na sieci/systemie")
    discover = commands.add_parser("discover", help="mDNS albo jawnie wskazana prywatna podsieć")
    discover.add_argument("--cidr")
    discover.add_argument("--acknowledged", action="store_true", help="Potwierdzenie uprawnienia do sieci")
    inspect = commands.add_parser("inspect", help="Odczyt IPP Get-Printer-Attributes")
    inspect.add_argument("uri")
    inspect.add_argument("--acknowledged", action="store_true")
    commands.add_parser("queues", help="Odczyt lokalnych kolejek CUPS")
    bridge = commands.add_parser("bridge", help="Plan lub utworzenie kolejki CUPS driverless")
    bridge.add_argument("uri")
    bridge.add_argument("--name", required=True)
    bridge.add_argument("--apply", action="store_true")
    bridge.add_argument("--acknowledged", action="store_true")
    fw = commands.add_parser("preflight", help="Lokalne sprawdzenie pliku; bez flashowania")
    fw.add_argument("--manifest", type=Path, required=True)
    fw.add_argument("--file", type=Path, required=True)
    fw.add_argument("--model", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            if not 1 <= args.port <= 65535:
                raise ValueError("Port musi mieć wartość od 1 do 65535.")
            from .server import serve
            serve(args.port, args.demo)
        elif args.command == "discover":
            if not args.acknowledged:
                raise ValueError("Wykrywanie wymaga --acknowledged dla Twojej sieci.")
            from .network import discover_mdns, scan_subnet
            emit({"devices": scan_subnet(args.cidr) if args.cidr else discover_mdns()})
        elif args.command == "inspect":
            if not args.acknowledged:
                raise ValueError("Odczyt wymaga --acknowledged dla Twojej drukarki.")
            from .network import inspect_printer
            emit(inspect_printer(args.uri))
        elif args.command == "queues":
            from .bridge import list_queues
            emit(list_queues())
        elif args.command == "bridge":
            from .bridge import bridge_plan, install_queue
            if args.apply:
                if not args.acknowledged:
                    raise ValueError("Zmiana kolejki wymaga --apply --acknowledged.")
                result = install_queue(args.uri, args.name, acknowledged=True)
                emit(result)
                return 0 if result["installed"] else 1
            emit(bridge_plan(args.uri, args.name))
        elif args.command == "preflight":
            if args.manifest.stat().st_size > 65536:
                raise ValueError("Manifest może mieć do 64 KiB.")
            manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
            with args.file.open("rb") as image:
                data = image.read(MAX_FIRMWARE_SIZE + 1)
            result = preflight(manifest, data, args.model)
            emit(result)
            return 0 if all(result[field] for field in ("integrity_matches", "size_matches", "model_matches")) else 1
    except (ValueError, OSError, RecursionError) as error:
        print(f"Błąd: {str(error)[:1000]}", file=sys.stderr)
        return 2
    return 0
