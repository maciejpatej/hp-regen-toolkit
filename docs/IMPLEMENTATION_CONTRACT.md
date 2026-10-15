# v0.1 frozen implementation gate

Python 3.11+ standard library; local UI + CLI. No telemetry, cloud service, credentials, exploit execution or firmware writes. MIT license.

- Discovery: bounded IPv4 mDNS browse for IPP/IPPS; explicit RFC1918 subnet scan, at most /24, only after ownership acknowledgement. No automatic network activity on launch.
- Inspect: IPP Get-Printer-Attributes only; literal RFC1918/loopback IPv4, ports 631/443, no redirects/proxies/credentials. Strict request/response bounds. Printer output is untrusted.
- Local host: 127.0.0.1 only; Host allowlist, same-origin check, per-session CSRF token on POST; no CORS; bounded bodies/concurrency.
- Firmware workbench: offline SHA-256/size/exact-model preflight from explicitly untrusted manifest; authenticity and recovery remain unverified; no enabled write/jailbreak adapter without physical hardware validation.
- CUPS: read local queues; explicit approved creation of a new driverless queue only, validated URI/name, no shell/sudo, local server pinned, refuse existing names. Demo never installs.
- Browser: Polish UI, honest live/demo status, functional discovery, inspect, report export, offline preflight and compatibility roadmap; no mock actions presented as real repairs.
- Gate: unittest suite (valid and malformed IPP/DNS, scope refusal, web origin/token guards, firmware mismatch); packaging and CLI smoke; local demo UI screenshot.

Network module API:
`discover_mdns(timeout=3.0) -> list[dict]`, `scan_subnet(cidr, timeout=1.0) -> list[dict]`, `inspect_printer(uri, timeout=2.0) -> dict`.
Entries: id, name, uri, source, model (optional). Inspection: uri, name, model, state, reasons, firmware, capabilities, attributes, findings; omit unknown or mark unknown explicitly.
Safety module: `validate_printer_uri(uri) -> urllib.parse.SplitResult`, `validate_subnet(cidr) -> ipaddress.IPv4Network`; raise ValueError.
REST GET /api/session => csrf_token,demo,version; GET /api/devices => devices; POST /api/discover {method:"mdns"|"subnet",cidr?,acknowledged:true} => devices,warnings; POST /api/inspect {uri,acknowledged:true} => device; POST /api/firmware/preflight {manifest:object,data_base64:string,model:string} => preflight; GET /api/report => report; GET /api/compatibility => entries.
POST sends X-Regen-Token. All failures JSON {error: string}. Max uploaded JSON 8 MiB (firmware 4 MiB). GET static /, /app.js, /style.css, /logo.png. No inline JS/styles.
