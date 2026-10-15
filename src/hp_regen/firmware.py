"""Offline integrity checks. A local manifest is never a root of trust."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit

MAX_FIRMWARE_SIZE = 4 * 1024 * 1024


def preflight(manifest: dict, data: bytes, model: str) -> dict:
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != 1:
        raise ValueError("Manifest wymaga schema_version: 1.")
    for field in ("model", "firmware_version", "sha256", "source_url"):
        if not isinstance(manifest.get(field), str) or not 1 <= len(manifest[field]) <= 1024:
            raise ValueError(f"Nieprawidłowe pole manifestu: {field}.")
    if not isinstance(model, str) or not 1 <= len(model) <= 256:
        raise ValueError("Podaj dokładną nazwę modelu z etykiety drukarki.")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", manifest["sha256"]):
        raise ValueError("sha256 musi mieć 64 znaki szesnastkowe.")
    size = manifest.get("size")
    if type(size) is not int or not 1 <= size <= MAX_FIRMWARE_SIZE:
        raise ValueError("size musi być dodatnią liczbą bajtów, maksymalnie 4 MiB.")
    source = urlsplit(manifest["source_url"])
    if source.scheme != "https" or not source.hostname or source.username or source.password:
        raise ValueError("source_url musi być adresem HTTPS bez danych logowania.")
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_FIRMWARE_SIZE:
        raise ValueError("Plik musi mieć od 1 bajta do 4 MiB. Większe obrazy wymagają przyszłego adaptera.")
    digest = hashlib.sha256(data).hexdigest()
    integrity = digest == manifest["sha256"].lower()
    size_match = len(data) == size
    model_match = model == manifest["model"]
    return {
        "integrity_matches": integrity,
        "size_matches": size_match,
        "model_matches": model_match,
        "computed_sha256": digest,
        "ready_to_flash": False,
        "authenticity": "unverified",
        "write_adapter": "unavailable",
        "checks": [
            {"name": "SHA-256", "ok": integrity, "detail": "Porównanie z dostarczonym manifestem."},
            {"name": "Rozmiar pliku", "ok": size_match, "detail": f"{len(data)} / {size} bajtów"},
            {"name": "Dokładny model", "ok": model_match, "detail": "Porównanie nazwy; nie potwierdza rewizji sprzętowej."},
            {"name": "Adapter zapisu", "ok": False, "detail": "Brak zweryfikowanego adaptera dla konkretnego sprzętu."},
        ],
        "warnings": [
            "Zgodny SHA-256 potwierdza zgodność pliku z manifestem, nie autentyczność firmware.",
            "Nie sprawdzono podpisu producenta, rewizji płyty, zgodności bootloadera ani skuteczności odzyskiwania.",
            "Program nie wysyła tego pliku do drukarki. Aktualizacja lub downgrade może blokować materiały eksploatacyjne albo urządzenie.",
        ],
    }
