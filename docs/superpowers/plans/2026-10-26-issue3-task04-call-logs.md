# Task04 Call Logs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans, inline TDD, one fresh final read-only review.

**Goal:** Index real audit JSONL incrementally; deliver scoped log list/detail, legacy compatibility, async folding, and measured 10,000-line first-page latency below one second.

**Architecture:** A local SQLite audit index stores physical-line identities/checkpoints plus logical calls. File identity and content anchors detect rotation/replacement/truncation; line imports and cursor updates commit together. Explicit callId folds asynchronous request/terminal rows inside source+tenant scope. Console memory operations emit separate sanitized JSONL. Querying logs never emits another log.

**Tech Stack:** Existing Python/FastAPI/Pydantic/SQLite; no dependency, frontend or model changes.

**Spec:** docs/superpowers/specs/2026-10-26-issue3-dashboard-backend-design.md, audit/usage section and task04. Approved implementation sequence; current user instruction starts task04.

## Global Constraints

- Work in D:/MemOS/dashboard; retain all prior Task01/02/03 changes and unrelated .memos data. No commit/push/PR; no frontend src/shared/server/mock edits; main5274 remains Mock.
- Only gateway calls-*.jsonl and console console-*.jsonl are business call sources. requests/searches JSONL are protocol/retrieval diagnostics and must not be double-counted.
- Tenant comes from explicit trusted source fields and configured project mapping, never inferred from subject ID or assigned to the default project.
- Success envelope code0; list key logs; detail requestBody/responseBody JSON strings without double encoding. Detail without projectId uses the fixed instance default project.
- Missing historical durations stay null; missing tokens are0; missing unknown status is UNKNOWN; no invented timestamps/subjects. Preserve unknown event labels; invalid event filters return400.
- Current real gateway uses synchronous add and has no callId. Test and disclose async folding with isolated request/terminal fixtures rather than claiming production async history exists.
- Source directories are explicit process config, not request-controlled filesystem paths. Missing/unreadable configured source fails clearly; valid empty directories can return empty lists.
- Cold 10k benchmark includes import+SQL+HTTP first page, not just a preloaded in-memory query. Also measure persisted-index restart and incremental append. Target <1s, record fixture bytes and real timings.

## Review Focus

- Same filename replaced or truncated/regrown past old offset must not lose new rows; renamed same physical file must not duplicate rows.
- Half lines, invalid JSON, oversized lines and malformed nested fields cannot corrupt cursor progress or hide later valid records.
- Async terminal-first/repeated terminal/request-late ordering cannot duplicate calls or downgrade terminal state; equal callIds across tenants/sources never merge.
- Log detail is tenant-scoped even when its ID is copied from a different project; unscoped legacy records are quarantined, not leaked.
- JSON body handling preserves already encoded strings, redacts credentials, never invents successful business status from HTTP200.

### Task 1: Contracts and normalization

- [x] Add failing normalization/filter tests, including legacy missing fields, aliases, status precedence, JSON-string bodies, unknown events, source/callId and timezone boundaries.
- [x] Implement audit_models.py and audit_normalize.py. Supplement OpenAPI scope/project detail semantics/validation and unknown output event labels.
- [x] Run focused tests then preserve decisions in execution ledger.

### Task 2: Incremental SQLite index

- [x] Add failing tests for initial/repeated/restarted import, append, half lines, rename/rotation, same-name replacement, truncate/regrow, bad/oversized JSON, cursor transaction rollback and source failure.
- [x] Implement audit_index.py: raw line identity, durable checkpoints, async logical-call folding, indexed scoped filters/pagination and detail projection.
- [x] Add async race/order/tenant/source collision tests and measure a 10k corpus early; optimize only from evidence.

### Task 3: HTTP and console audit integration

- [x] Add failing API tests for list/detail/default scope, combined filters, validation, errors, JSON strings and no log-read feedback loop.
- [x] Implement audit_routes.py/audit_writer.py, Settings/env controls and lifespan wiring. Console writes include only delivered memory operations; missing identity never defaults to another tenant.
- [x] Retarget obsolete Task01 unimplemented-route check to usage/query (Task05); preserve its no-fake-success meaning.
- [x] Run full backend suite, Ruff and existing task regressions.

### Task 4: Real acceptance, performance and delivery

- [x] Configure real gateway audit directory, restart owned backend only. Verify actual gateway read invocation -> JSONL -> list -> same source record/detail; generate actual console memory read -> console JSONL -> source filter.
- [x] Verify isolated async fixture association and file faults through HTTP, clearly labelled synthetic.
- [x] Measure 10k new-index first page, persisted-index restart, warm p50/p95 and incremental append, with HTTP wall time and bytes. Require <1s first page.
- [x] Fresh final review, fix important findings using RED/GREEN, then final suite/format/Redocly/protected source diff checks.
- [x] Write TASK04-RESULT.md, update plan/design/matrix, stop before Task05 usage aggregation. Keep inherited upstream18 baseline failures disclosed, do not claim they were repaired.
