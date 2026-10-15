# HP regen toolkit agent instructions

This is a standalone Python/vanilla-JavaScript printer workbench, unrelated to the Unity spacebase repository.

- Read README.md, SECURITY.md and docs/IMPLEMENTATION_CONTRACT.md first.
- Python >=3.11 standard-library runtime; no new runtime dependencies without justification.
- No live scans, printer jobs, CUPS writes or firmware writes during automated tests. Mock transports/subprocesses; loopback-only test servers are allowed.
- Never claim printer support from packet tests or an advertised model name. Exact model/revision/functions require physical evidence.
- Scope validation precedes every network request. Printer payloads and imported manifests are untrusted.
- Do not bundle proprietary firmware, secrets or user documents. Firmware SHA-256 alone is not authenticity.
- Write adapters need docs/MODEL_ADAPTERS.md gates; no universal or unverified flash action.
- Use feature branches and scoped commits. Network/security/firmware changes require an independent adversarial review and all tests green.
- Gate: PYTHONPATH=src python3 -m unittest discover -s tests -v; node --check src/hp_regen/web/app.js; local demo UI check after relevant UI changes.
