# Agent Instructions & Project Policies: Data Designer

This document defines non-negotiable guidelines for all AI agents working on this repository.

---

## 1. Versioning & Release Lifecycle Policy (STRICT)

> [!CRITICAL]
> **DO NOT HOP TO MAJOR RELEASES (e.g. 1.0.0).**
> Data Designer is actively undergoing early exploratory testing, developer dogfooding, and real-use validation. The system is NOT in shape for a full production / 1.0.0 release.

### Progression Rules
1. **Forbidden Major Bumps**: Never bump to `1.0.0` or suggest a general production release unless the human user explicitly and unambiguously requests it.
2. **Current Phase — Alpha (`0.y.z-alpha`)**:
   - Current release: `0.1.0-alpha`.
   - Bug fixes & testing refinements: increment patch pre-release (e.g. `0.1.1-alpha`, `0.1.2-alpha`).
   - Significant feature additions while still in active iteration: increment minor pre-release (e.g. `0.2.0-alpha`, `0.3.0-alpha`).
3. **Subsequent Phase — Beta (`0.y.z-beta`)**:
   - Transition to `beta` will occur only after core feature stability is confirmed and the human user approves transitioning from alpha.
   - Format: `0.x.0-beta` or `0.x.0-beta.N`.
4. **All GitHub Releases MUST be Pre-releases**:
   - Any GitHub release created must have the **pre-release** flag set (`--prerelease` or checked in GitHub UI).
5. **Strict Multi-File Version Synchronization**:
   Whenever a version increment is made, the agent MUST update all of the following in the exact same commit:
   - `web/package.json` (`"version"`)
   - `api/app/main.py` (`FastAPI(..., version="...")`)
   - `api/pyproject.toml` (`[project]` -> `version = "..."`)
   - `CHANGELOG.md` (new version header following Keep a Changelog)
   - Git annotated tag: `git tag -a v<version> -m "Release v<version>"`

---

## 2. Repository Hygiene & Secret Protection

- **Never commit database dumps or backups**: Files in `backups/`, `*.dump`, and `*.sql` must NEVER be committed. They contain live database state and credentials.
- **Never commit `.env`**: Always use `.env.example` for environment variable templates.
- **Verify tests before commits**:
  - Backend: `api/.venv/bin/pytest api/tests`
  - Frontend: `cd web && npm test && npm run check`

---

## 3. Specifications & Architecture References

- Authoritative specification: `MASTER-SPEC.md`
- Implemented capabilities: `SYSTEM_CAPABILITIES.md`
- User guide: `docs/user-guide.md`

