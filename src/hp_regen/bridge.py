"""Reversible driverless CUPS queue setup for an explicitly selected printer.

Only IPP Everywhere compatible printers (or a compatible external IPP bridge)
can use this setup. No proprietary driver, firmware, or printer-side setting is
changed. The local user needs permission to administer CUPS; this module never
elevates privileges.

Existing queue names are checked twice to avoid replacing settings. CUPS does
not offer atomic "create only" through lpadmin, so another local administrator
could still create the same queue between the final check and invocation. Queue
administration on the same host should be serialized.
"""

from __future__ import annotations

import re
import shutil
import subprocess

from .safety import validate_printer_uri

_QUEUE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,62}", re.ASCII)
_OUTPUT_LIMIT = 4000
_MAX_QUEUES = 256
_CUPS_ENV = {"LC_ALL": "C", "LANG": "C", "CUPS_SERVER": "localhost"}


def _bounded(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    text = (value or "").strip()
    if len(text) > _OUTPUT_LIMIT:
        suffix = "\n[wynik skrócony]"
        return text[:_OUTPUT_LIMIT - len(suffix)] + suffix
    return text


def _validate(uri: str, queue_name: str) -> tuple[str, str]:
    if not isinstance(queue_name, str) or not _QUEUE_NAME.fullmatch(queue_name):
        raise ValueError(
            "Nazwa kolejki: 1–63 znaków ASCII; pierwsza litera, dalej litery, "
            "cyfry, podkreślenie lub myślnik."
        )
    return validate_printer_uri(uri).geturl(), queue_name


def list_queues() -> dict:
    """List local queues without changing CUPS or contacting their printers."""
    lpstat = shutil.which("lpstat")
    if not lpstat:
        return {
            "available": False,
            "queues": [],
            "warnings": [
                "Brak narzędzia lpstat/CUPS. W Windows dodaj drukarkę IPP "
                "w ustawieniach systemu; ta funkcja obsługuje lokalny CUPS."
            ],
        }
    try:
        result = subprocess.run(
            [lpstat, "-v"], capture_output=True, text=True, timeout=5, check=False,
            env=_CUPS_ENV.copy(),
        )
    except subprocess.TimeoutExpired:
        return {"available": False, "queues": [], "warnings": ["CUPS nie odpowiedział w ciągu 5 sekund."]}
    except OSError as exc:
        return {"available": False, "queues": [], "warnings": [_bounded(f"Nie można odczytać kolejek CUPS: {exc}")]}
    # CUPS reports a server with no queues as a nonzero exit and this message.
    # Treat that precise state as an empty inventory, not as a daemon failure.
    no_destinations = "No destinations added." in (result.stderr or "")
    if result.returncode != 0 and not no_destinations:
        return {
            "available": False,
            "queues": [],
            "warnings": [_bounded(result.stderr or result.stdout or "Nie można odczytać kolejek CUPS.")],
        }
    queues = []
    # Parse the entire inventory for collisions rather than truncating text
    # before parsing, but cap the exported inventory and fail closed on overflow.
    for line in (result.stdout or "").splitlines():
        if not line.startswith("device for "):
            continue
        name, separator, uri = line[len("device for "):].partition(": ")
        if separator:
            queues.append({"name": name[:127], "uri": _bounded(uri)})
        if len(queues) > _MAX_QUEUES:
            return {"available": False, "queues": queues[:_MAX_QUEUES], "warnings": ["Za dużo kolejek do bezpiecznego sprawdzenia nazw (limit 256)."]}
    return {"available": True, "queues": queues, "warnings": []}


def bridge_plan(uri: str, queue_name: str) -> dict:
    """Prepare a command; this function never installs a queue."""
    normalized_uri, name = _validate(uri, queue_name)
    lpadmin = shutil.which("lpadmin")
    instructions = [
        "Wymagana drukarka zgodna z IPP Everywhere lub zgodny zewnętrzny most IPP.",
        "Polecenie utworzy lokalną kolejkę CUPS; nie zmienia firmware drukarki.",
        "Potrzebne uprawnienia administratora CUPS. Aplikacja nie uruchamia sudo.",
        "Wybierz nową nazwę kolejki; istniejące kolejki są chronione przed zastąpieniem.",
        "Kolejkę można później usunąć w ustawieniach drukarek systemu.",
    ]
    if not lpadmin:
        instructions.append(
            "Brak lpadmin/CUPS. W Windows: Ustawienia → Bluetooth i urządzenia "
            "→ Drukarki i skanery → Dodaj urządzenie, używając adresu IPP. "
            "W macOS/Linux sprawdź instalację i dostępność CUPS."
        )
    return {
        "supported": bool(lpadmin),
        "command": [lpadmin, "-p", name, "-E", "-v", normalized_uri, "-m", "everywhere"] if lpadmin else [],
        "instructions": instructions,
    }


def install_queue(uri: str, queue_name: str, acknowledged: bool = False) -> dict:
    """Install only after explicit acknowledgement and two collision checks."""
    plan = bridge_plan(uri, queue_name)
    failed = {"installed": False, "queue_name": queue_name}
    if acknowledged is not True:
        return {**failed, "output": "Wymagane jawne potwierdzenie utworzenia lokalnej kolejki CUPS."}
    if not plan["supported"]:
        return {**failed, "output": plan["instructions"][-1]}
    for _ in range(2):
        inventory = list_queues()
        if not inventory["available"]:
            return {**failed, "output": _bounded("Nie można bezpiecznie sprawdzić istniejących kolejek. " + " ".join(inventory["warnings"]))}
        if any(queue["name"].lower() == queue_name.lower() for queue in inventory["queues"]):
            return {**failed, "output": "Kolejka o tej nazwie już istnieje. Wybierz inną nazwę; ustawienia nie zostały zmienione."}
    try:
        result = subprocess.run(
            plan["command"], capture_output=True, text=True, timeout=15, check=False,
            env=_CUPS_ENV.copy(),
        )
    except subprocess.TimeoutExpired as exc:
        details = _bounded(exc.stderr or exc.stdout)
        return {**failed, "output": _bounded("Przekroczono czas oczekiwania (15 sekund). Polecenie mogło utworzyć kolejkę; sprawdź ustawienia drukarek przed ponowną próbą. " + details)}
    except OSError as exc:
        return {**failed, "output": _bounded(f"Nie można uruchomić lpadmin: {exc}")}
    output = _bounded("\n".join(part for part in (result.stdout, result.stderr) if part))
    if result.returncode != 0:
        return {**failed, "output": _bounded(f"lpadmin zakończył się kodem {result.returncode}. " + (output or "Sprawdź uprawnienia CUPS i zgodność drukarki z IPP Everywhere."))}
    return {
        "installed": True,
        "queue_name": queue_name,
        "output": output or "Utworzono lokalną kolejkę CUPS. Wydruk próbny potwierdzi zgodność urządzenia.",
    }
