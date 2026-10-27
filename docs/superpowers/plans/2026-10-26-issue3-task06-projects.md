# Task06 Projects Implementation Plan

**Goal:** Deliver persisted real workspace lifecycle and independent selected-project contexts, without implementing Task07 account authentication.

**Spec:** ../specs/2026-10-26-issue3-dashboard-backend-design.md; Task06 user instruction.

**Execution:** Main agent inline. Existing feature workspace and uncommitted Task01–05 changes retained. No src/shared/mock/env edits, upstream changes, commits or destructive memory operations.

## Decisions / interfaces

- SQLite projects are the authoritative workspaces, each with immutable upstream_cube_id (new project defaults to its generated ID). Native product memory endpoints use that namespace without requiring the separate owner-based /create_cube registry; verify an actual new namespace through all six read views.
- Migrate existing projects transactionally, preserve stored mappings, disabled/archive state and names on restart. Seed visibility remains configuration-controlled; API-created projects have a persisted local-operator ownership marker and survive configuration-only restart.
- Selection is a persisted opaque HttpOnly/SameSite cookie context, not a global status update and not an authenticated account. Task07 will attach/replace this preference context with real account sessions. No fake /api/auth/me implementation.
- Project projection: status ENABLED only for selected active workspace; disabled and archived independent. Dictionary excludes inaccessible/inactive projects; list includes disabled/archived for recovery. Local trusted operator has management role owner, explicitly not complete account authorization.
- update ENABLED on an active project selects it; on a disabled project it re-enables without switching. DISABLED stops it. Archive is reversible, revoke is an archive compatibility alias; never delete memory/cube data. Invalidate/fallback only contexts selecting an inactive target.
- Existing memory/detail and log/detail must use selected context; resolve_cube and usage authorized_cubes exclude inactive projects. Use existing Origin checks on writes. Same transaction for lifecycle state, context fallback, uniqueness and persistence.

## Steps

- [x] RED tests: migration/restart, creation/update/pagination/validation/duplicates, two context selections, stopped/archive gates and restore, immutable mapping, Origin, concurrent writes.
- [x] Implement project models/control persistence/routes/context; wire delivered APIs and root OpenAPI; retarget obsolete Task01 negative route to /api/auth/me.
- [x] GREEN full backend tests + Ruff. Verify actual isolated project lifecycle, browser selection, restart persistence, existing memory data preserved and Mock unchanged.
- [x] Main-agent review against contract/fault cases; use additional agent only if necessary. pnpm verify/Redocly/protected diff; Task06 result and progress matrix. Stop Task07.

Evidence and remaining frontend/auth/key boundaries: server/backend/TASK06-RESULT.md. Full backend 204 passed; live three OS-process restarts; pnpm verify, Ruff, Redocly passed. Task07 not started.
