# Task05 P1 Usage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Serve real daily usage from the existing logical audit index with explicit scope and UTC+8 boundaries.

**Architecture:** A strict request model resolves date bounds; ControlStore supplies authorized cube IDs; AuditIndex aggregates its existing gateway audit_calls. The route reuses AuditService incremental ingestion. No second JSONL importer or frontend changes.

**Tech Stack:** FastAPI, Pydantic, SQLite, Python 3.11, pytest.

**Spec:** docs/superpowers/specs/2026-10-26-issue3-dashboard-backend-design.md

## Global Constraints

Preserve src/, shared/, server/mock/, current main frontend Mock and previous tasks. Stop after Task05. No commits, upstream edits or real memory mutations. Current authorization is the configured local operator allowlist, not completed account authentication.

## Review Focus

- Persisted projects removed from configuration must not enter all-project totals.
- UTC timestamps at 16:00Z belong to the next Beijing date; end date is inclusive through next midnight exclusive.
- Missing timestamps remain visible in logs but cannot enter a dated aggregate.
- Async terminal updates replace one logical call and never add another usage call.
- Nonempty unsupported apiKeyId must fail explicitly; includeDailyDetails=false must still return a documented summary.

### Task 1: Daily usage behavior

- [x] Write failing API tests for date ranges/defaults/zero days, source/event/status rules, tokens, async updates, authorization and errors; run RED.
- [x] Add usage_models.py and usage_routes.py, ControlStore.authorized_cubes and AuditIndex.usage using only existing audit_calls; integrate app router.
- [x] Run targeted tests GREEN and fix regressions.

### Task 2: Contract and acceptance

- [x] Supplement root OpenAPI request ambiguity and additive summary/metadata; validate actual envelopes.
- [x] Retarget the obsolete Task01 unimplemented usage check to the next unimplemented module.
- [x] Add and run setup/verify_task05.py using isolated HTTP fixtures and read-only real index comparison.
- [x] Run full backend pytest and Ruff, record actual results and precise limitations in TASK05-RESULT.md/README/design progress.
