# Dashboard v2 backend delivery

Related to hugegraph/MemOS#3. Target branch: dashboard-v2. The React frontend, shared TypeScript contracts and Mock sources remain unchanged.

## Scope

Implemented: live metadata, six memory tabs and detail, soft-delete/restore with receipts and retry, JSONL call logs and daily usage, persistent projects/accounts/members/invitations, project extraction Prompt configuration, graph/fulltext, model inventory, project API keys and profile-template APIs. Quota/subscription and skillMD use the fixed responses allowed by the issue.

Authorization is layered: platform administrators manage global accounts; project owners manage their own members/invitations/keys; members can read their project's member list and leave themselves. Cross-project access and last-effective-admin/owner invariants are enforced. See AUTHORIZATION.md. This interpretation is explicit for maintainer review.

Knowledge-base development was stopped at the requester's direction. Existing entity CRUD, project links and file upload/list/download/delete are retained, with prior tests and real-service evidence. POST /api/dashboard/knowledgebase/memory/list is not implemented. This PR therefore uses “Related to #3”, not an automatic closing keyword; it does not assert full delivery of the original knowledge-base scope.

## Deploy the upstream support

The adapter depends on additional APIs/behavior in deployment-v2. Use a separate checkout at commit 8d6e231d7d95ea29b6a2716c9c34837644d3e7f6, then apply the complete support patch from this PR:

```sh
git checkout 8d6e231d7d95ea29b6a2716c9c34837644d3e7f6
git apply --check /path/to/dashboard/server/backend/patches/deployment-v2-dashboard-support.patch
git apply /path/to/dashboard/server/backend/patches/deployment-v2-dashboard-support.patch
```

The patch includes graph/vector lifecycle confirmation, profile-field reads/lifecycle, event filtering, Prompt runtime fixes, the API schema and regression tests, embedding-provider compatibility, and gateway key publication/automatic reload. Start/rebuild the upstream service and gateway using deployment-v2's existing deployment instructions; configure its model providers there. The adapter does not need or load model API keys.

The older Task12/14 patches are retained as historical/component artifacts. Do not apply them in addition to the complete patch: their changes overlap. Apply the complete patch once on the stated clean baseline. Necessary support is packaged here instead of requiring unpublished changes in another local checkout.

## Start the adapter

Python 3.11+ is required. Run from the dashboard repository root:

```sh
python -m venv .venv
# Activate .venv using the command appropriate for your shell.
python -m pip install -r server/backend/requirements-dev.txt
```

Export process environment variables using server/backend/.env.example as reference. The program does not automatically load that file. Both bootstrap and the server must use the same configuration:

```sh
export DASHBOARD_DATA_DIR="$PWD/.data"
export DASHBOARD_UPSTREAM_URL=http://127.0.0.1:8000/
export DASHBOARD_PROJECTS='demo:demo'
export DASHBOARD_DEFAULT_PROJECT_ID=demo
export DASHBOARD_AUDIT_GATEWAY_DIR=/absolute/path/to/gateway/audit
export DASHBOARD_GATEWAY_KEYS_FILE=/absolute/path/to/mcp-gateway/tenants.conf
python -m server.backend.bootstrap admin --bootstrap
python -m server.backend --host 127.0.0.1 --port 5281
```

PowerShell equivalents use `$env:NAME = 'value'`; the commands otherwise remain Python module commands. Bootstrap prompts for a password without putting it in command-line arguments. Authentication is enabled by default. Keep the adapter and unauthenticated upstream on a trusted network; do not expose the upstream directly to untrusted clients.

Set the gateway's MEMOS_TENANTS_FILE to the same absolute configuration path. Dashboard and gateway need access to the shared publication directory and lock. Deploy/restart the upgraded gateway once; later key creation/revocation takes effect on its next authenticated request without restart. Environment-variable changes still require restart. Invalid/unconfirmed file publications temporarily deny file credentials, then recover automatically; existing in-flight operations are not cancelled.

In another terminal, install the existing frontend dependencies and start its existing proxy against the adapter:

```sh
pnpm install --frozen-lockfile
MOCK_ORIGIN=http://127.0.0.1:5281 pnpm dev
```

For PowerShell: set `$env:MOCK_ORIGIN = 'http://127.0.0.1:5281'`, then run `pnpm dev`. Do not run `pnpm mock`. Open http://127.0.0.1:5274/__login, log in, and select the seeded project. No frontend source edit is required. For another origin configure DASHBOARD_ALLOWED_ORIGINS explicitly. No absolute Windows paths or private setup directory are needed for these steps.

## Verify

```sh
python -m pytest server/backend/tests -q
python -m ruff check server/backend
pnpm verify
pnpm --package=@redocly/cli dlx redocly lint openapi.json
git diff origin/dashboard-v2 -- src/ shared/ server/mock/
python -m server.backend.acceptance.smoke --base http://127.0.0.1:5281 --project demo
```

The portable smoke command prompts for credentials (or reads DASHBOARD_TEST_USERNAME/DASHBOARD_TEST_PASSWORD), checks real read endpoints and emits counts/check names only. It creates no project, key or memory. Use --native and --cube to additionally compare returned memory IDs/content with the native REST API. Do not commit credential files, .data evidence, JSONL, databases or model settings.

The earlier task14/15/16 acceptance drivers and start_live.ps1 reproduce the original Windows lab using private fixtures under D:/MemOS. They are historical lab tools, not prerequisites for deployment. Their old results document real writes/restores, process restarts and outage experiments; the portable smoke command does not claim to reperform those destructive or paid operations.

## Recorded validation and limitations

- Latest complete adapter suite before final packaging: 318 passed. Later authorization regression: 23 passed. Automatic-reload gateway suites: 56 passed; adapter key regressions: 27 passed. These are separate runs, not a fabricated sum or a claim that the entire upstream test suite passes.
- pnpm verify passed; schema validation passed. Real Mock-off browser inspection, same-ID REST reads, reversible deletion, JSONL correlation and upstream outage recovery were performed.
- 10,000-line JSONL cold first-page timings: 805.350 / 779.142 / 795.091 ms on the local fixture. This is not a general multi-user performance SLA.
- Memory list output is projected and bounded; active-state counts exclude archived/deleted records. Graph node/byte limits set truncated instead of implying a complete export.
- Profile fields are real graph nodes with original IDs; no invented relation edges. The unchanged frontend lacks the ProfileMemory translation and uses a different type-label grouping than the list tabs. The profile-template page remains ComingSoon despite working APIs. Recovery/retry receipts use APIs because the frontend has no controls for them.
- Archived-current-project table state may require refresh. Knowledge-base navigation remains disabled. These UI limitations are preserved under the issue's src/ zero-change requirement.
- State and audit indexing use local SQLite and filesystem coordination; this is not a distributed database/HA deployment. Historical upstream-wide testing had 18 reproduced baseline failures; no claim is made that this PR fixes them.

Task reports retain detailed historical measurements. Private local evidence is intentionally not committed; the committed tests, patch and commands allow independent review.

Final packaging checks: the complete support patch passed a clean-baseline temporary-index apply check and current-worktree reverse check. The portable smoke command passed against real services (six tabs, 14 graph nodes, two same-ID native REST comparisons); its new tests and affected contract/authorization checks passed 12 tests. OpenAPI license and same-origin server metadata were completed; Redocly now reports zero errors and four warnings, all for the four HTML form operations whose actual success is a 303 redirect. No fake 200 response was added.
