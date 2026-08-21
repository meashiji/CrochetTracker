# Test Plan

> Phased test rollout for this project. Strategy is frozen at the top
> (§1–§5); cookbook patterns at the bottom (§6) fill in as phases ship.
> Read before writing any new test.
>
> Refresh: re-run `/10x-test-plan --refresh` when stale (see §8).
>
> Last updated: 2026-08-21 (Phase 2 complete — risks #3, #6 covered; risk #1 since covered by `tests/test_row_state_routes.py` shipped with S-02/S-03 — POST + DB-verify incl. persistence-across-reload; Phase 3 not started)

---

## 1. Strategy

Tests follow three non-negotiable principles for this project:

1. **Cost × signal.** The cheapest test that gives a real signal for the
   risk wins. Do not promote to e2e because e2e "feels safer." Do not put a
   vision model on top of a deterministic visual diff that already catches
   the regression.
2. **User concerns are first-class evidence.** Risks anchored in "the
   team is worried about X, and the failure would surface somewhere in
   <area>" carry the same weight as PRD lines or hot-spot data.
3. **Risks are scenarios, not code locations.** This plan documents *what
   could fail* and *why we believe it's likely* — drawn from documents,
   interview, and codebase *signal* (churn, structure, test base). It does
   NOT claim to know which line owns the failure. That knowledge is
   produced by `/10x-research` during each rollout phase. If the plan and
   research disagree about where the failure lives, research is the
   ground truth.

Hot-spot scope used for likelihood weighting: `app/` (excluding `__pycache__`, build output). Top directories by 30-day churn: `app/models` (15), `app/auth` (9), `app/routes` (8), `app/templates/auth` (7).

---

## 2. Risk Map

The top failure scenarios this project must protect against, ordered by
risk = impact × likelihood. Risks are failure scenarios in user / business
terms, not test names. The Source column cites the *evidence that surfaced
this risk* — never a specific file as "where the failure lives" (that is
research's job, see §1 principle #3).

| # | Risk (failure scenario) | Impact | Likelihood | Source (evidence — not anchor) |
|---|------------------------|--------|------------|--------------------------------|
| 1 | Row-mark write silently fails — HTMX POST returns an error, UI updates, DB doesn't; user re-opens to find stale state | High | High | PRD NFR "no silent data loss"; PRD Open Question 1; interview Q1 ("data loss after action"); interview Q2 (habit of checking dev DB to verify writes); roadmap S-02 |
| 2 | Auth middleware regression — a code change to the auth area accidentally unprotects a project route; unauthenticated request gets 200 with data | High | Medium | PRD Access Control; interview Q3 ("auth middleware changes without confidence"); hot-spot `app/auth` (9 changes/30d) |
| 3 | Cross-user IDOR — authenticated user A accesses user B's project/element/row via direct URL; receives 200 instead of 404 | High | Medium | PRD Access Control; interview Q4 ("cross-user data access"); roadmap S-01 (project routes currently being built) |
| 4 | Expired or tampered session accepted by middleware — a crafted or expired session token grants access to protected routes | High | Medium | PRD Access Control; interview Q4 ("auth session"); hot-spot `app/auth` (9 changes/30d) |
| 5 | Alembic/SQLModel schema drift — a model field added or changed without a corresponding migration; prod DB diverges from ORM; app crashes on deploy or silently miscategorizes data | High | Medium | Interview Q3 ("Alembic migrations change without confidence"); hot-spot `app/models` (15 changes/30d); tech-stack (Alembic + SQLModel) |
| 6 | Pattern paste DB records don't match parsed rows — `parse_pattern()` returns correct output but the Row/RowState DB records have wrong count or content; user tracks wrong rows | Medium | Low | PRD FR-004/FR-005; roadmap S-01 Phase 2 (upcoming); existing test gap — `tests/test_pattern.py` covers the parser only, not the DB write |

**Impact × Likelihood rubric:**

| Rating | Impact | Likelihood |
|--------|--------|------------|
| High | user loses access, data, or the core product promise fails | area changes weekly, or we have been burned here |
| Medium | feature degrades, workaround exists, some users affected | touched occasionally, has been a source of bugs |
| Low | cosmetic, easily reverted, no data effect | stable code, rarely touched |

### Risk Response Guidance

| Risk | What would prove protection | Must challenge | Context `/10x-research` must ground | Likely cheapest layer | Anti-pattern to avoid |
|------|-----------------------------|----------------|--------------------------------------|-----------------------|-----------------------|
| #1 | POST to row-mark that returns 5xx/4xx does NOT silently update UI — DB state matches what the user sees; either the row stays unchanged or a clear retry signal is shown | "HTTP 200 means the write succeeded" — HTMX can return 200 with an error fragment that the UI silently swaps | How does the row-mark endpoint signal failure to HTMX? What does the client do on a non-200 response? | Integration test: TestClient POST → simulate server failure → verify DB record and HTMX response fragment | Asserting UI shows correct state without also verifying the DB record directly |
| #2 | GET/POST to a project route with no valid session → 302 redirect to login (or 401), not 200 with project data | "A new route missing Depends() would be unprotected" — research confirmed the middleware is global ASGI; any new route is automatically protected; the real attack surface is `_PUBLIC_PATHS` at `app/auth/middleware.py` and the `is_public` condition logic | How does `_PUBLIC_PATHS` get expanded? What is the exact `is_public` condition in `AuthRedirectMiddleware.dispatch`? | Integration test: TestClient request with no session cookie → expect redirect/401 | Testing only the happy path (valid session → 200); never testing the missing-session case |
| #3 | Authenticated user A GETs `/projects/{id_owned_by_B}` → 404, not 200 | "Being authenticated means the route is protected" — authentication ≠ resource ownership | How does each project/element/row route verify ownership? Is there a shared helper or is it per-route? | Integration test: two test users; cross-user URL access → expect 404 | Testing with a single test user and never crossing the ownership boundary |
| #4 | Tampered session cookie or valid user_id in session with deleted user → 302 redirect to login (or 401), not 200 | "Sessions expire" — research confirmed `SessionMiddleware` is configured without `max_age`; sessions never expire; drop the expired-session scenario; testable cases are: (a) tampered cookie → HMAC fails → Starlette clears session → middleware returns 303; (b) valid `user_id` in session but user deleted from DB → `get_current_user` returns None → HTTP 401 | Session cookie name (`"session"`, Starlette default); `https_only=True` requires `base_url="https://testserver"` for httpx — otherwise `Secure` cookie not sent | Integration test: send tampered `session` cookie value → expect 303; separately test session with orphaned user_id → expect 401 | Testing only "no session at all"; never testing tampered payload or orphaned user_id as distinct failure paths |
| #5 | After any model change, `alembic check` returns no pending migrations; drift is caught before deploy | "The autogenerated migration is correct" — autogenerate misses `server_default`, some FK constraint details, and column-type nuances | How are SQLModel models registered in Alembic's env.py? Which model changes has autogenerate historically missed? | CI gate: `alembic check` as a pre-merge required step | Discovering migration drift only on deploy to the production database |
| #6 | After a pattern POST, the count and content of Row/RowState DB records exactly matches what `parse_pattern()` returns for the same input | "parse_pattern() is tested, so the paste is correct" — the parser tests verify the parsing logic, not the DB write | What DB records does the pattern-paste route create? How many tables are written (Element, Row, RowState)? In what order? | Integration test: POST pattern → query DB → assert record count and content match `parse_pattern()` output | Asserting the UI row-list count without also querying the DB directly |

---

## 3. Phased Rollout

Each row is a discrete rollout phase that will open its own change folder
via `/10x-new`. Status moves left-to-right; the orchestrator updates Status
as artifacts appear on disk.

| # | Phase name | Goal | Risks covered | Test types | Status | Change folder |
|---|-----------|------|---------------|-----------|--------|---------------|
| 1 | Auth-boundary integration tests | Prove route protection and session validation work; bootstrap test infrastructure (httpx TestClient, pytest fixtures, test DB) | #2, #4 | Integration (TestClient, pytest fixtures, separate test DB) | complete | context/changes/testing-auth-boundary/ |
| 2 | Write-path + ownership integration tests | Prove cross-user IDOR protection and DB write correctness for core user flows | #3, #6 (#1 deferred — no implementing route exists) | Integration (multi-user fixtures, TestClient POST + DB verify) | complete | context/changes/testing-write-path-ownership/ |
| 3 | Migration drift quality gate | Name `alembic check` as a required CI gate and verify it catches real drift | #5 | CI gate naming (wiring deferred to Module 2 Lesson 5) | not started | — |

**Status vocabulary** (parser literals — do not rename):

| Value | Meaning |
|-------|---------|
| `not started` | No change folder for this rollout phase yet |
| `change opened` | `context/changes/<id>/` exists with `change.md`; research not done |
| `researched` | `research.md` exists in the change folder |
| `planned` | `plan.md` exists with a `## Progress` section |
| `implementing` | Progress section has at least one `[x]` and at least one `[ ]` |
| `complete` | Progress section is fully `[x]` |

**No AI-native phase:** all six risks are deterministic (data integrity, auth logic, DB write correctness). The product contains no AI-generated content and no NL outputs. Classic integration tests give full signal at minimal cost; an AI-native layer would add cost without signal.

---

## 4. Stack

| Layer | Tool | Version | Notes |
|-------|------|---------|-------|
| Unit + integration | pytest | 9.1.1 | Configured in `pyproject.toml`; run with `uv run pytest` |
| HTTP test client | httpx + pytest-asyncio | none yet — see §3 Phase 1 | Required for FastAPI async route testing; not yet in dev deps |
| DB fixtures | pytest fixtures + separate test DB | none yet — see §3 Phase 1 | Need a test-scoped Postgres DB; local dev DB is on 127.0.0.1:5433 |
| Lint / typecheck | none yet | — | Not configured; add if deadlines allow |
| E2e | none planned | — | Jinja2 templates excluded from test budget (§7); classic integration covers the critical paths |

**Stack grounding tools (current session):**
- Docs: none — no Context7 or framework docs MCP available in current session; checked: 2026-06-27
- Search: none — no Exa.ai or web search MCP available in current session; checked: 2026-06-27
- Runtime/browser: none — no Playwright MCP available; not needed given §7 excludes template rendering; checked: 2026-06-27
- Provider/platform: none — no GitHub, Fly, or Postgres MCP available in current session; checked: 2026-06-27

---

## 5. Quality Gates

| Gate | Where | Required? | Catches |
|------|-------|-----------|---------|
| Unit + integration (pytest) | local + CI | required after §3 Phase 1 | Logic regressions, auth bypass, IDOR, write-path failures |
| `alembic check` | local + CI | required after §3 Phase 3 | Migration drift between SQLModel models and DB schema |
| Lint | local + CI | planned | Syntactic drift (no tool configured yet) |
| Typecheck | local + CI | planned | Type drift (no tool configured yet) |
| Pre-prod smoke | between merge + prod | optional | Environment-specific failures on Fly |

---

## 6. Cookbook Patterns

How to add new tests in this project. Each sub-section fills in once the
relevant rollout phase ships; before that it reads "TBD — see §3 Phase N."

### 6.1 Adding a unit test

TBD — see §3 Phase 1. (Reference: `tests/test_pattern.py` exists for the pattern parser utility; this entry will canonicalize the pattern for route and service tests.)

### 6.2 Adding an integration test for a route

Reference implementation: `tests/test_auth_boundary.py`

**Run command**: `uv run pytest tests/ -v`

**Fixture dependencies**:
- All tests: `async_client` — httpx `AsyncClient` with `ASGITransport(app=app)` and
  `base_url="https://testserver"`. Set `follow_redirects=False` when testing redirects.
- DB-backed tests: `db_session` — `AsyncSession` against the test DB; for teardown/setup only.
- Tests needing a logged-in user: `test_user` — calls `POST /auth/signup`, sets the session
  cookie on `async_client`, and yields the `User` row. Tears down by deleting the user row.

**Test DB prerequisite** (one-time setup):
```bash
PGPASSWORD=dupa123 createdb -h 127.0.0.1 -p 5433 -U crochet_tracker crochet_tracker_test
```

**Key constraint**: `base_url` must be `"https://testserver"` (not `http://`) because
`SessionMiddleware` uses `https_only=True` — the `Secure` cookie flag causes httpx to silently
drop cookies on plain-http requests, making session tests fail without an obvious error.

**Pattern for a new no-DB route test** (middleware-layer, no user needed):
```python
async def test_my_route_requires_auth(async_client):
    response = await async_client.get("/my-route/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/auth/login")
```

**Pattern for a DB-backed route test** (route handler runs, user in DB):
```python
async def test_my_route_returns_200(test_user, async_client):
    response = await async_client.get("/my-route/", follow_redirects=False)
    assert response.status_code == 200
```

### 6.3 Adding a cross-user ownership test

Reference implementation: `tests/test_project_routes.py::test_element_detail_other_user_sees_404`,
`test_element_save_pattern_other_user_sees_404`, `test_element_detail_wrong_project_sees_404`

**Fixture**: `second_user` (`tests/conftest.py`) — creates a second, independently authenticated user with
its own `AsyncClient`/session and yields `(user, client)`. Unlike `test_user`, it manages its own client
internally because the shared `async_client` fixture can only hold one session cookie at a time; a real
cross-user IDOR test needs the "attacker" request to carry a genuinely distinct authenticated session, not
just a directly inserted `User` row.

**Pattern**:
```python
async def test_my_route_other_user_sees_404(test_user, second_user, db_session):
    _second_user, second_client = second_user

    # create the resource owned by test_user via db_session directly
    resource = MyResource(user_id=test_user.id, ...)
    db_session.add(resource)
    await db_session.commit()

    response = await second_client.get(f"/my-route/{resource.id}", follow_redirects=False)
    assert response.status_code == 404
```

**Don't forget the "same owner, wrong parent" case** — e.g. an `element_id` that is valid but belongs to a
different `project_id` than the one in the URL. A single cross-user test only proves the `user_id` check;
resources nested under another resource (Project → Element → Row) need a second case proving the *parent*
match, not just the *owner* match (see `test_element_detail_wrong_project_sees_404`).

**Teardown**: delete child rows before parent rows (no cascade is defined on any FK in this schema) — e.g.
delete `Element` rows before `test_user`'s own teardown deletes `Project` rows.

### 6.4 Adding a write-path DB-verify test

Reference implementation: `tests/test_pattern_paste.py` (whole file; start with
`test_pattern_paste_creates_matching_db_records`)

**Pattern**: POST → query DB directly (not the rendered HTML) → assert record count *and* content match
the expected transform. Do not stop at "the parser/service function returns the right value" — the DB write
is a separate step from the pure function and can drift from it (wrong FK, wrong count, stale rows left
behind). For a multi-table write, query every table the route is documented to touch and assert each one.

```python
async def test_my_write_creates_matching_db_records(test_user, async_client, db_session):
    # 1. Arrange: create parent resource(s) via db_session directly.
    # 2. Act: POST through async_client (real route, real ownership checks).
    assert response.status_code == 303  # or whatever the route's success status is
    # 3. Assert: query every table the route writes, compare count + content
    #    against the pure-function output (e.g. parse_pattern()), not just row count.
```

**All-or-nothing is a distinct assertion from "the happy path is correct".** For any write path that can be
rejected (validation failure, ownership failure), add a test that the rejection leaves the DB unchanged —
zero new rows on a fresh resource, or the original rows untouched on a re-write rejection
(`test_pattern_paste_rejected_repaste_leaves_existing_rows_intact` is the reference for the latter). This is
the cheapest available proxy for "no silent partial write" when the target risk's own endpoint (e.g. a
row-mark feature) doesn't exist yet.

**Teardown for multi-table writes**: delete in FK-safe order — RowState → Row + ElementRepetition → Element
→ (Project is handled by the owning fixture's teardown). See `_teardown()` helper in `test_pattern_paste.py`.

### 6.5 Checking migration drift

TBD — see §3 Phase 3. (Phase 3 wires `alembic check`. This entry will document the exact command and what to do when it fails.)

---

## 7. What We Deliberately Don't Test

- **Jinja2 template rendering** — broken templates are immediately visible after deploy; the cost of maintaining template snapshot or rendering tests exceeds the signal. Re-evaluate if server-side rendering logic (not just markup) moves into templates. (Source: interview Q5.)
- **`parse_pattern()` unit tests** — already covered by `tests/test_pattern.py`; no additional coverage budget needed here unless the parser gains new branching logic.
- **Auth library internals (pwdlib, itsdangerous)** — these are upstream libraries with their own test suites. We test that our code calls them correctly (auth integration tests), not their internal algorithms.
- **Stitch reference panel content** — static glossary data, no data model, roadmap S-04 is blocked pending content decision. Test when the feature ships and only if it gains dynamic behavior.
- **Admin tooling** — no admin surface exists; excluded proactively.

---

## 8. Freshness Ledger

- Strategy (§1–§5) last reviewed: 2026-06-27
- Stack versions last verified: 2026-06-27
- AI-native tool references last verified: 2026-06-27 (no AI-native phase; re-evaluate at --refresh if product gains AI output surfaces)

Refresh (`/10x-test-plan --refresh`) when:

- a new top-3 risk surfaces from the roadmap or archive,
- a recommended tool's `checked:` date is older than three months,
- the project's tech stack changes (new test runner, new framework layer),
- §7 negative-space no longer matches what the team believes.
