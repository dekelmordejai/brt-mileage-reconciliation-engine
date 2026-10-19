# Security and data boundaries

This is a local portfolio demonstration, not a production payment system. Do not submit operational data, personal information, credentials, recordings, databases or institutional reports in issues, pull requests or attachments.

Report vulnerabilities privately using this repository's Security → Advisories → Report a vulnerability option when available; do not disclose exploitation details or sensitive data in a public issue. If private reporting is unavailable, contact the maintainer through an already established private channel.

The synthetic demo password is deliberately public and only belongs to an isolated localhost demo database. Never reuse demo accounts with real data. Importing a real source stores its original bytes and rows, which may contain sensitive fields even when they are absent from the dashboard.

Runtime controls: hashed passwords, expiring server-side sessions, role checks, CSRF tokens, host allowlist, login throttling, escaped UI/export values, separate proposal and reviewer identities, immutable source/run/decision tables, and a hash-linked audit log. These controls have automated tests; they are not a security certification. A database administrator can bypass file-level controls; this is not WORM storage.

Keep the service bound to 127.0.0.1. Do not publish a running instance without a separate deployment/security review. Production use would require validated domain rules, organizational identity, TLS, secure cookies, managed keys/access, encrypted storage, backups/restores and operational acceptance. No external app deployment is included.

Only synthetic files may be committed. `private_data/`, databases, uploads, credentials, exports, screenshots of real data and local logs are excluded. The demo screenshot in `docs/assets/` is generated exclusively from the committed synthetic fixture.
