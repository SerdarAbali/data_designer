# Host environment

Inspected for Phase 0 on 2026-10-03; package state updated after bootstrap.

| Property | Observed |
|---|---|
| OS | Debian GNU/Linux 13 (trixie), 13.7 |
| Architecture | `aarch64` |
| CPU | 4 × ARM Cortex-A76, up to 2.4 GHz |
| Memory | 7.9 GiB total; approximately 6.0 GiB available at inspection |
| Disk (`/`) | 939 GiB total; approximately 893 GiB available |
| Git | 2.47.3 |
| Python | 3.13.5 |
| Node.js | 20.19.2 |
| npm | 9.2.0 (system); lockfile also verified with npm 10.8.2 |
| Docker Engine | 26.1.5+dfsg1-9+deb13u1 (ARM64) |
| Docker Compose | 2.26.1-4 (v2 plugin) |
| Docker daemon | Active |

The available OS metadata identifies Debian 13, not Raspberry Pi OS. Do not
assume a Raspberry Pi OS image or change SSH, boot, Tailscale, or OS setup.

The verified toolchain is ARM64-compatible. Compose image pulls/builds and
container platform checks are performed as part of the Phase 1 startup
verification.
