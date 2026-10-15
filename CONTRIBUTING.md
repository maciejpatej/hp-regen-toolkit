# Contributing

Start with a scoped issue: exact device model/revision, problem and observable acceptance test. Never upload print jobs, serials, credentials or proprietary firmware to an issue or commit. Use synthetic test fixtures.

Python 3.11+, standard library runtime. Frontend is local vanilla JavaScript/CSS. Keep protocol, scope policy, firmware metadata and UI separate. No automatic network activity on app startup. No arbitrary executable plugin system.

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
node --check src/hp_regen/web/app.js
PYTHONPATH=src python3 -m hp_regen serve --demo
```

All printer/network/CUPS side effects must be mocked in CI. Local HTTP tests bind only loopback. Use a feature branch, small scoped commits and independent review for network, auth, firmware or hardware adapter changes.

Model-specific writes require the release gate in docs/MODEL_ADAPTERS.md and a reproducible physical-device record. Passing packet/unit tests cannot certify hardware. Add supported devices only when exact variants and tested functions are documented.
