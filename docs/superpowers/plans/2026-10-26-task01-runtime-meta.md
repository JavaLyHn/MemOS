# Task 01 Runtime Metadata Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for this task only. User explicitly authorized Task 01 and requires stopping after its delivery.

**Goal:** Start a standalone Dashboard backend exposing a contract-compatible `/api/meta`, with real MemOS health validation and uniform errors.

**Architecture:** Independent FastAPI application factory; one lifespan-owned httpx client probes the configured MemOS `/health`. Only safe health fields are projected. No memory, log, account, SQLite, or frontend integration is implemented in this task.

**Tech Stack:** Python >=3.11, FastAPI 0.115.14, httpx 0.28.1, Pydantic 2.12.4, uvicorn 0.38.0; pytest 9.0.2 and JSON Schema tests.

**Spec:** `docs/superpowers/specs/2026-10-26-issue3-dashboard-backend-design.md`, implementation sequence item 1; root `openapi.json`.

## Global Constraints

- Work in the user-selected `D:/MemOS/dashboard` checkout on `feat/dashboard-backend`; do not move the existing running project or switch branches.
- Keep `src/`, `shared/`, and `server/mock/` unchanged; do not modify `.env.local` or the running frontend proxy.
- Backend binds to `127.0.0.1:5281`; current frontend remains on Mock through port 5274.
- Response envelope is `{code, data, message}`; success code 0, errors nonzero with suitable HTTP status.
- No real model requests, memory writes, secret reads/exports, or unrelated upstream modifications.
- User authorized implementing this item directly; no additional design/plan approval loop. No automatic progression to Task 02, Git commit, push, or PR.

## Review Focus

- Healthy-looking non-MemOS JSON or incompatible contract version must not produce live success.
- Connection failures, timeouts, redirects, HTTP errors, malformed JSON, and unhealthy payloads must produce bounded, uniform failures.
- Health extras and exception messages must not leak API keys, credentials, internal URLs, or debug stacks.
- Unknown paths, wrong methods, request validation, controlled errors, and unexpected errors must use the same envelope.
- Frontend continues reporting sample while backend independently reports live; service restart preserves this separation.

## Task 1: Runtime foundation and metadata

**Files:**
- Create: `server/backend/{__init__,__main__,app,settings,upstream,errors,models}.py`.
- Create: `server/backend/tests/{test_meta,test_errors,test_settings,test_entrypoint}.py`.
- Create: `server/backend/{README.md,requirements.txt,requirements-dev.txt,.env.example,ruff.toml}`.
- Modify: `package.json` for optional backend commands; `.gitignore` for Python artifacts.
- Modify: `openapi.json` only to document actual metadata failure responses/error codes.
- Local environment: add `D:/MemOS/setup/Start-Backend.ps1` and `Stop-Backend.ps1` with owned-process checks, without changing frontend configuration.

**Interfaces:**
- `Settings.from_env() -> Settings`, with `upstream_url` and finite `upstream_timeout_seconds` configuration.
- `UpstreamClient.health() -> UpstreamHealth`, translating transport/protocol problems to `ApiError`.
- `create_app(settings: Settings | None = None, *, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI` for production and network-isolated tests.
- `GET /health`: local process liveness, wrapped JSON, independent of upstream.
- `GET /api/meta`: real upstream health, mode live, service name, keyPrefix and five configured gateway tool descriptors; no auth claimed.

- [x] Write tests for healthy response/schema, health projection, all upstream failures, settings validation, standard error envelopes, and `python -m server.backend --help`.
- [x] Run pytest and record expected RED before implementation (backend module absent).
- [x] Document metadata 502/503/504 response contracts before implementing them.
- [x] Implement the focused modules and CLI; close the HTTP client during lifespan shutdown, disable implicit HTTP retries/proxy inheritance and redirects for the internal upstream.
- [x] Run backend tests until GREEN; use real tests for error handlers without adding production test routes.
- [x] Add minimal dependencies, README, example configuration, and cross-platform pnpm commands; add local PowerShell launch/stop scripts with process ownership and readiness checks.
- [x] Verify backend start, same-ID process idempotence, stop/restart, genuine `/api/meta`, and frontend `/api/meta` still sample. Persist a credential-free report outside the repository in `.local/`.
- [x] Run scoped Ruff, backend pytest, `pnpm verify`, Redocly lint, `git diff --check`, and baseline frontend-zero-diff check.
- [x] Perform an independent review of Task 01 only and fix material findings with RED/GREEN evidence.
- [x] Record completion evidence and report to the user. Stop before Task 02.

Expected backend failure mapping: timeout 504/50400; unavailable or unhealthy 503/50300; HTTP/protocol/identity/contract mismatch 502/50200. Generic validation 400/40000; unknown route 404/40001; unsupported method 405/40000; unexpected failure 500/50000. Messages must be safe fixed descriptions, not raw upstream error bodies.
