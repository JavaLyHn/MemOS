# Tasks07–09 identity implementation plan

**Goal:** Implement the approved account/session, member and invitation design inline in the existing backend.
**Spec:** ../specs/2026-10-26-issue3-dashboard-backend-design.md, identity section and steps7–9.
**Architecture:** Same SQLite control database, transactional account and membership invariants; scrypt password hashes and opaque hashed sessions; request-bound project permissions. Backend HTML login/logout/invitation routes use existing Vite proxy prefixes. Explicit authenticated deployment is enabled after bootstrap; legacy local operator mode remains explicitly available for earlier isolated tests.
**Constraints:** Main agent implements; preserve src/shared/mock/env/upstream; no commits or pushes; no paid models or mutations of existing memories. User directly authorized all three tasks; report each then continue without further approval.

## Review focus
- Concurrent demotion/removal/disable/delete must preserve an effective admin and active project owner.
- Account disable/delete invalidates existing sessions; role revocation takes effect next request, including explicit projectId and all-project usage.
- Anonymous and cross-origin callers cannot mutate authenticated state; login and invitation forms use bounded bodies and CSRF tokens, safe redirects and escaped HTML.
- Invite digest only, expiration/revocation/single use enforced transactionally; existing members never get silently downgraded.
- Migration preserves Task06 data; authenticated selections are session-bound and cannot inherit arbitrary anonymous project cookies.

## Task07
- [x] RED: login, logout, expiry/restart, anonymous/non-admin denial, strict account updates, immediate disable, effective last-admin and owner safeguards, deletion relationships.
- [x] Implement identity_store.py, auth.py, bootstrap.py; wire settings/meta/middleware and request-bound project store. Keep schema/password/session internals out of API projection.
- [x] GREEN tests and genuine HTTP restart/login evidence; report Task07 before continuing.

## Task08
- [x] RED: owner/editor/viewer matrix, scoped reads/writes/all-project usage, candidates, add/change/remove/leave, last effective owner and concurrent transitions.
- [x] Implement members.py and membership operations; project creator becomes owner in the same transaction, no personal-space membership editing.
- [x] GREEN and HTTP/browser project-member evidence; report Task08.

## Task09
- [x] RED: create/list/role/revoke/expiry/reuse/concurrent accept, disabled project, existing member protection, signup and logged-in accept CSRF.
- [x] Implement invites.py and backend invitation landing/acceptance through /__login/invite/{token}; CLI account initialization and invitation signup supply real account creation without modifying React.
- [x] GREEN all backend tests, Ruff, pnpm verify, Redocly, protected diff and genuine browser/HTTP flows; update Task07–09 reports/design/matrix and stop before Task10.

Evidence: TASK07/08/09-RESULT.md;229 backend tests, genuine HTTP/OS restart and browser flows. One inherited-model read-only security review found no concrete unresolved issue. No Task10.
