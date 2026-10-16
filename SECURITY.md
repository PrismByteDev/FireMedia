# Reporting security issues

Please use the repository's **Security → Report a vulnerability** option for
issues involving executable plugins, playback input, update verification, or
private data. Repository administrators must enable private vulnerability
reporting before that option is available. If it is unavailable, open an issue
asking for a private reporting channel without including exploit details or
private files. There is no published response-time guarantee.

Only the latest maintained version receives fixes; no older release branch has
a support commitment yet. Windows mod execution is disabled. Linux workers fail
closed if their OS restrictions cannot be applied.

The automatic update system is currently a design, not an enabled feature.
`release-info.json` and `SHA256SUMS` alone do not authorize unattended installation.
See [the planned update trust model](docs/UPDATES.md).
