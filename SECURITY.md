# Security policy and threat boundaries

HP regen toolkit is a local, owner-operated printer workbench. Use only on devices/networks you own or are authorized to administer. This is an engineering prototype; it has not been audited for deployment on a shared workstation or as a LAN/Internet service.

## Implemented boundaries

- Panel binds only `127.0.0.1`; Host allowlist prevents ordinary DNS rebinding. POST requires a random session token; foreign Origin and cross-site Fetch Metadata are refused. No permissive CORS, no telemetry, no external frontend resources. CSP restricts executable content.
- No scan on startup. UI/CLI require explicit ownership acknowledgement for printer queries, discovery and CUPS creation. CIDR must be RFC1918 IPv4, at most 256 addresses. mDNS has finite time, record, query and packet budgets.
- Targets use literal private IPv4/127.0.0.1 and port 631/443; no DNS target resolution, proxies, redirects, authentication credentials or unrestricted URL fetches.
- Printer reads use only IPP Get-Printer-Attributes. DNS and IPP are treated as untrusted binary input, with framing/length/count/type limits and finite HTTP deadlines. TLS certificate checks remain enabled for IPPS.
- Browser renders printer/manifests strings as text, not HTML. Reports remain local until the user exports/shares them.
- CUPS creation requires a separate explicit instruction, strict queue-name/URI validation, a local server target and existing-name checks. No shell or privilege elevation. A local administrator race between the final check and CUPS invocation remains possible; serialize administration on the same host. A timeout can leave an uncertain queue-creation outcome.
- Firmware preflight only compares file/model/size/hash with a user-supplied manifest. It never establishes authenticity, never enables flashing and never executes an image or downloads firmware. No vendor firmware redistribution.

## Residual limits

The local session token does not protect against malware, another process running as the same user, browser extensions with local-page privileges or a compromised OS. Discovery cannot authenticate mDNS records. Plain IPP has no transport confidentiality; IPPS may fail for self-signed certificates or an IP/name mismatch. Proprietary authentication, nonstandard ports and IPv6 are not supported yet.

Protocol bounds trade compatibility for predictable behavior: unsupported encodings/collections, excessive attributes or malformed responses are refused. A failed probe does not establish that a printer is absent or vulnerable. No CVE assessment is inferred from missing/unknown firmware.

The application does not inspect print-job content, extract passwords/documents, run exploit payloads, disable hardware interlocks or write device firmware. Future owner-authorized repair adapters need the model-specific gate in [docs/MODEL_ADAPTERS.md](docs/MODEL_ADAPTERS.md), rather than enabling arbitrary third-party executable plugins.

## Reporting

Until a private vulnerability-reporting channel is enabled on the repository, do not publish exploit details, credentials, device serials or live network addresses in a public issue. Public issues can request a private contact channel. Reproduce using the offline test suite and synthetic devices where possible.
