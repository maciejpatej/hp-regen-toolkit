"""Loopback-only local workbench. Not an Internet-facing service."""
from __future__ import annotations

import base64
import binascii
import copy
import json
import secrets
import socket
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import __version__
from .catalog import COMPATIBILITY, DEMO_DEVICES
from .firmware import MAX_FIRMWARE_SIZE, preflight
from .safety import validate_printer_uri, validate_subnet

MAX_BODY = 8 * 1024 * 1024
WEB_ROOT = Path(__file__).parent / "web"
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8"), "/logo.png": ("logo.png", "image/png")}


class Workbench:
    def __init__(self, demo: bool = False):
        self.demo = demo
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.operation = threading.Lock()
        self.last_discovery = -float("inf")
        self.devices = copy.deepcopy(DEMO_DEVICES) if demo else []
        self.events: deque = deque(maxlen=200)

    def record(self, action: str, result: str):
        with self.lock:
            self.events.append({"time": datetime.now(timezone.utc).isoformat(), "action": action, "result": result})

    def report(self) -> dict:
        with self.lock:
            return {"version": __version__, "demo": self.demo, "generated_at": datetime.now(timezone.utc).isoformat(), "devices": copy.deepcopy(self.devices), "events": list(self.events), "limits": ["Brak certyfikowanego adaptera firmware i brak fizycznej walidacji modeli.", "Raport może zawierać lokalne adresy IP i dane drukarki. Sprawdź go przed udostępnieniem."]}

    def action(self, path: str, data: dict) -> dict:
        from . import bridge, network
        if path in ("/api/discover", "/api/inspect", "/api/bridge/install") and data.get("acknowledged") is not True:
            raise ValueError("Potwierdź, że masz prawo obsługiwać tę drukarkę lub sieć.")
        if path == "/api/discover":
            method = data.get("method", "mdns")
            if method not in ("mdns", "subnet"):
                raise ValueError("Nieznana metoda wykrywania.")
            if method == "subnet":
                validate_subnet(data.get("cidr"))
            now = time.monotonic()
            if now - self.last_discovery < 10 and not self.demo:
                raise ValueError("Poczekaj 10 sekund przed kolejnym wykrywaniem.")
            self.last_discovery = now
            devices = copy.deepcopy(DEMO_DEVICES) if self.demo else (network.discover_mdns() if method == "mdns" else network.scan_subnet(data["cidr"]))
            with self.lock:
                inventory = {device["uri"]: device for device in self.devices}
                for device in devices:
                    previous = inventory.get(device["uri"], {})
                    inventory[device["uri"]] = {**previous, **device}
                self.devices = list(inventory.values())[-256:]
            self.record("discovery", f"{method}: {len(devices)} urządzeń" + (" (demo)" if self.demo else ""))
            return {"devices": devices, "warnings": ["Dane demonstracyjne; sieć nie została odpytana."] if self.demo else (["Brak wyników nie oznacza braku drukarek. Spróbuj dokładnego URI IPP lub sprawdź izolację Wi-Fi."] if not devices else [])}
        if path == "/api/inspect":
            target = validate_printer_uri(data.get("uri")).geturl()
            if self.demo:
                device = next((copy.deepcopy(d) for d in DEMO_DEVICES if d["uri"] == target), None)
                if device is None:
                    raise ValueError("W trybie demo dostępne są wyłącznie przykładowe urządzenia.")
            else:
                device = network.inspect_printer(target)
            with self.lock:
                old = next((d for d in self.devices if d["uri"] == target), None)
                if old is None:
                    self.devices.append(device)
                    self.devices = self.devices[-256:]
                else:
                    old.update(device)
            self.record("inspect", target + (" (demo)" if self.demo else ""))
            return {"device": device}
        if path == "/api/firmware/preflight":
            encoded = data.get("data_base64")
            if not isinstance(encoded, str) or len(encoded) > (MAX_FIRMWARE_SIZE + 2) // 3 * 4:
                raise ValueError("Nieprawidłowy lub zbyt duży plik firmware (limit 4 MiB).")
            try:
                image = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError):
                raise ValueError("Nieprawidłowe kodowanie pliku.") from None
            result = preflight(data.get("manifest"), image, data.get("model"))
            self.record("firmware_preflight", "offline; zapis zablokowany")
            return {"preflight": result}
        if path == "/api/bridge/plan":
            return bridge.bridge_plan(data.get("uri"), data.get("queue_name"))
        if path == "/api/bridge/install":
            if self.demo:
                raise ValueError("Tryb demo nie zmienia kolejek systemowych. Uruchom aplikację bez --demo.")
            result = bridge.install_queue(data.get("uri"), data.get("queue_name"), acknowledged=True)
            self.record("cups_install", "utworzono" if result["installed"] else "nie utworzono")
            return result
        raise ValueError("Nieznana operacja.")


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8
    allow_reuse_address = True

    def __init__(self, address: tuple, workbench: Workbench):
        if address[0] != "127.0.0.1":
            raise ValueError("Panel można uruchomić wyłącznie na 127.0.0.1.")
        self.workbench = workbench
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(address, Handler)
        port = self.server_address[1]
        self.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.allowed_origins = {f"http://{host}" for host in self.allowed_hosts}

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "HPRegenLocal"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format, *args):
        # No URI, tokens, printer strings or file content in terminal logs.
        pass

    def send_payload(self, payload, status: int = 200, mime: str = "application/json; charset=utf-8"):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass

    def guarded(self, post: bool = False) -> bool:
        if len(self.headers.get_all("Host", [])) != 1 or self.headers.get("Host") not in self.server.allowed_hosts:
            self.send_payload({"error": "Nieprawidłowy Host."}, 403)
            return False
        origins = self.headers.get_all("Origin", [])
        if len(origins) > 1 or (origins and origins[0] not in self.server.allowed_origins):
            self.send_payload({"error": "Obca strona nie ma dostępu do lokalnego panelu."}, 403)
            return False
        if self.headers.get("Sec-Fetch-Site") in ("cross-site", "same-site"):
            self.send_payload({"error": "Otwórz panel bezpośrednio w lokalnej karcie."}, 403)
            return False
        if post:
            tokens = self.headers.get_all("X-Regen-Token", [])
            if len(tokens) != 1 or not tokens[0].isascii() or not secrets.compare_digest(tokens[0], self.server.workbench.token):
                self.send_payload({"error": "Nieprawidłowy token sesji. Odśwież panel."}, 403)
                return False
        return True

    def route_path(self):
        if not self.path.startswith("/") or self.path.startswith("//"):
            self.send_payload({"error": "Wymagana lokalna ścieżka żądania."}, 400)
            return None
        try:
            return urlsplit(self.path).path
        except ValueError:
            self.send_payload({"error": "Nieprawidłowa ścieżka żądania."}, 400)
            return None

    def do_GET(self):
        if not self.guarded():
            return
        path = self.route_path()
        if path is None:
            return
        app = self.server.workbench
        if path in STATIC:
            filename, mime = STATIC[path]
            asset = WEB_ROOT / filename
            if not asset.is_file():
                self.send_payload({"error": "Brak zasobu aplikacji."}, 404)
            else:
                self.send_payload(asset.read_bytes(), mime=mime)
        elif path == "/api/session":
            self.send_payload({"csrf_token": app.token, "demo": app.demo, "version": __version__})
        elif path == "/api/devices":
            self.send_payload({"devices": app.report()["devices"]})
        elif path == "/api/report":
            self.send_payload(app.report())
        elif path == "/api/compatibility":
            self.send_payload({"entries": COMPATIBILITY})
        elif path == "/api/queues":
            from .bridge import list_queues
            self.send_payload({"available": False, "queues": [], "warnings": ["Tryb demo nie odpytuje systemu."]} if app.demo else list_queues())
        else:
            self.send_payload({"error": "Nie znaleziono."}, 404)

    def do_POST(self):
        if not self.guarded(post=True):
            return
        path = self.route_path()
        if path is None:
            return
        if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1:
            self.send_payload({"error": "Wymagany jednoznaczny Content-Length."}, 400)
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            self.send_payload({"error": "Wymagany JSON."}, 415)
            return
        try:
            length = int(self.headers["Content-Length"])
        except ValueError:
            self.send_payload({"error": "Nieprawidłowa długość."}, 400)
            return
        if not 0 < length <= MAX_BODY:
            self.send_payload({"error": "Limit żądania: 8 MiB."}, 413)
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Niepełne żądanie.")
            data = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nieprawidłowy JSON.")))
            if not isinstance(data, dict):
                raise ValueError("Oczekiwany obiekt JSON.")
        except (ValueError, UnicodeError, RecursionError, socket.timeout):
            self.send_payload({"error": "Nieprawidłowy, niepełny lub zbyt złożony JSON."}, 400)
            return
        app = self.server.workbench
        if not app.operation.acquire(blocking=False):
            self.send_payload({"error": "Operacja już trwa. Poczekaj na jej zakończenie."}, 409)
            return
        try:
            result = app.action(path, data)
            self.send_payload(result)
        except ValueError as error:
            self.send_payload({"error": str(error)[:1000]}, 400)
        except (OSError, TimeoutError) as error:
            self.send_payload({"error": f"Brak odpowiedzi lub dostępu: {str(error)[:500]}"}, 502)
        except Exception:
            app.record("error", "błąd operacji; brak zmiany firmware")
            self.send_payload({"error": "Operacja nie powiodła się. Sprawdź URI, protokół i uprawnienia."}, 500)
        finally:
            app.operation.release()


def serve(port: int = 8765, demo: bool = False):
    with LocalServer(("127.0.0.1", port), Workbench(demo)) as server:
        print(f"HP regen toolkit {__version__}: http://127.0.0.1:{server.server_address[1]}" + (" [DEMO]" if demo else " [LIVE; brak skanu przy starcie]"), flush=True)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass
