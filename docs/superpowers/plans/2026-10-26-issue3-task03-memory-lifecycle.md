# Task03 Memory Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Execute inline with TDD and one fresh final review.

**Goal:** Deliver recoverable soft deletion of ordinary memories and individual profile fields, verified graph/vector convergence, durable retries and fault tests.

**Architecture:** The upstream owns durable lifecycle intents in MetadataStore; a per-resource database/file lock serializes transitions across service instances. Persist intent before graph mutation, strictly synchronize and read back existing vector points, and reconcile unfinished intents on startup and periodically. Dashboard persists operation receipts and adapts strict upstream outcomes without hiding partial failures. Profile transitions update one field and retain its value; all profile writers share a store lock.

**Tech Stack:** Existing Python/FastAPI/httpx, SQLite, Neo4j CloudEntity documents and Qdrant; no new dependency.

**Spec:** docs/superpowers/specs/2026-10-26-issue3-dashboard-backend-design.md, lifecycle and task03 sections. Already approved implementation sequence; user now requests task03.

## Global Constraints

- Work only in D:/MemOS/dashboard and authorized upstream implementation modules; preserve Task01/02 changes. No commit, push, PR or destructive cleanup.
- src/, shared/, server/mock/ and main frontend5274 remain unchanged. Optional isolated5276 frontend is for testing.
- Deletion verification targets only new disposable task03 records. Restore each real record after testing; never delete existing task01/02 data.
- Ordinary control-plane delete accepts only activated records. Restore uses upstream previous_status, not client-supplied arbitrary states. Frozen records cannot be deleted.
- Response code0 only when every requested operation is confirmed successful. Partial failures include durable operation IDs and per-item outcomes with nonzero code.
- Scope remains local configured operator projects; no claim of P1 authentication. Mutation checks trusted localhost Origin when present.

## Review Focus

- Crash after graph write leaves a recoverable intent and cannot leak a stale vector hit.
- Same operation ID with different arguments conflicts; replay after a later opposite operation cannot reapply the older effect.
- Vector unavailable, missing indexed point or failed verification never counts as success.
- Opposite concurrent operations serialize and drain prior unfinished work before progressing.
- Template sync, manual edit and extraction cannot resurrect or overwrite a deleted profile field; other fields remain unchanged.

### Task 1: Upstream durable lifecycle engine

- [x] Add failing tests for delete/restore, pre-intent failure, vector failure/readback mismatch/missing point, graph-write crash, startup replay, idempotency conflicts and concurrent opposite transitions.
- [x] Add lifecycle.py (separate from existing API lifecycle shutdown), control locking, models/routes and bounded background reconciliation.
- [x] Run new lifecycle tests and existing storage tests; verify confirmed success only after graph and vector agree.

### Task 2: Profile lifecycle and ordinary visibility

- [x] Add failing tests for single-field deletion, all read surfaces, retained original value, template/edit/extract updates, restore, tenant isolation and restart.
- [x] Implement profile field transitions using the same intents and serialized document writes. Filter deleted fields in instance views/recall.
- [x] Add final graph-state validation to search output; ensure REST single/batch/list reads and graph exposure omit deleted rows; unavailable graph fails closed.
- [x] Run relevant API/read/search/profile regressions and expand as required by AGENTS.md.

### Task 3: Dashboard contract and operation receipts

- [x] Add failing backend tests for validated batch delete, restore, operation query/retry, preflight-all scope/type checks, partial failures, idempotency, timeout recovery and Origin checking.
- [x] Extend control SQLite with operation receipts. Add lifecycle client/router; supplement OpenAPI projectId/memType/operation IDs and restore/status/retry routes while preserving deleted count.
- [x] Run entire backend suite, Ruff and task01/02 regression.

### Task 4: Real acceptance and delivery

- [x] Restart upstream/backend after code changes, export actual upstream OpenAPI.
- [x] Seed one independent fact and a two-field profile. Delete -> list/detail/batch/search absence -> raw graph/vector agreement -> restore -> same IDs and original values.
- [x] Exercise real local fault harness with process restart, vector outage, replay and opposite operations without disrupting user records.
- [x] Run API tests, backend tests, pnpm verify, Redocly, Ruff and protected frontend diff checks. Perform one fresh read-only final review, fix findings with RED/GREEN.
- [x] Write TASK03-RESULT.md with exact evidence and limitations, update design progress, then stop before Task04.

## Completion evidence and rulings

See server/backend/TASK03-RESULT.md. Backend119passed; upstream537passed/18deselected (same18failures independently reproduced against unmodified HEAD source). Full API is not claimed all green. pnpm verify/Ruff/Redocly(0errors,2existingwarnings)/diff checks pass; Task01/02 real regressions pass. Real crash/vector connection outage and lost HTTP acknowledgement/restarted Dashboard retry all passed; every disposable memory restored. One fresh review P1 legacy subgraph leak fixed with RED/GREEN. Community parser tenant loss fixed using scoped native state reads. No commits/push/PR, stop before Task04.
