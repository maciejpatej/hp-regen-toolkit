# Validation evidence — v0.1

Local evidence is recorded separately from real-printer support.

- Offline automated suite: **83/83 PASS** on the final full run (0.579 s); tests include malformed/compressed DNS, bounded IPP parsing and mocked HTTP, private-network scope rejection, SHA/model/size mismatch, local Host/Origin/CSRF checks and mocked CUPS collision/timeout behavior.
- Browser checks: demo discovery and selected-device inspection observed in the local in-app browser. Synthetic firmware upload/preflight completed through the real UI: digest, size and model match; authenticity unverified, write adapter unavailable and ready_to_flash false. Desktop and narrow layouts observed; no browser warnings/errors captured. Screenshots: assets/dashboard.jpg and assets/firmware-preflight.jpg.
- Package: wheel built and installed in an isolated virtual environment; installed hp-regen --version returned 0.1.0. Runtime has zero external dependencies.
- Physical printers: **not tested**. No claim that a specific HP/Xerox model is working, restored or safe to flash.
- CUPS writes: **not executed on the operator system**; command semantics and failure paths tested with mocks. Requires compatible IPP Everywhere device and local administrative permission.
- Platform: local macOS/Python 3.14; Linux/Windows CI configured, results pending publication. Network/IPPS compatibility still requires hardware tests.
- Independent review: **PASS** after fixing localized IPP summary values, retained report inventory, malformed HTTP targets, canonical URI handling and queue-name validation. The verifier independently ran the earlier full suite, then confirmed the final targeted regressions; root ran the final 83-case suite. Cross-model Claude was unavailable (not logged in). A further Gemini attempt was rejected by automatic approval review because directory access could disclose code to an external service; it was not retried or bypassed. No cross-model approval is claimed.

Known v0.1 limits: IPv4 only; RFC1918 or localhost target; ports 631/443; standard /ipp/print scan path; no authentication; no USB adapter/spooler; firmware upload 4 MiB and offline only. See SECURITY.md and MODEL_ADAPTERS.md.
