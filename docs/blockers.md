# Bootstrap blockers

Initial inspection found the following blockers; they have been resolved:

- Docker Engine and Docker Compose were installed from the Debian ARM64
  packages.
- Node.js/npm were installed from the Debian ARM64 packages.
- Docker daemon is active. The developer account is not in the `docker` group;
  Makefile Docker commands use `sudo` rather than granting root-equivalent
  socket access through group membership.

Do not place passwords or other credentials in this document. No application
runtime blocker remains once the Phase 1 Compose build and health checks pass.
