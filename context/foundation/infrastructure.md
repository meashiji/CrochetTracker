---
project: crochet-tracker
researched_at: 2026-05-28
recommended_platform: Fly.io
runner_up: Railway
context_type: mvp
tech_stack:
  language: Python 3.14
  framework: FastAPI + Jinja2 + HTMX + Tailwind CSS
  runtime: uvicorn (ASGI)
  package_manager: uv
  database: Fly Postgres (SQLModel / SQLAlchemy)
---

## Recommendation

**Deploy on Fly.io.**

Fly.io is the only candidate in the shortlist that runs always-on Python ASGI containers natively, co-locates managed Postgres in the same region without handing ownership to a third party, and exposes a comprehensive CLI (`flyctl`) that covers the full operational loop — deploy, rollback, log tailing — without a browser. The choice is reinforced by the developer's own `deployment_target: fly` preference already recorded in `tech-stack.md`, which breaks the otherwise close tie with Railway. The three anti-bias lenses identified real but preventable risks (uv Dockerfile, volume data-loss, Postgres ownership); all are addressed explicitly in the Getting Started section and risk register below.

## Platform Comparison

| Platform | CLI-first | Managed/Serverless | Agent-readable docs | Stable deploy API | MCP / Integration | Total |
|---|---|---|---|---|---|---|
| **Fly.io** | Pass | Pass | Partial | Pass | Fail | 3.5 / 5 |
| **Railway** | Pass | Pass | Partial | Pass | Fail | 3 / 5 |
| **Render** | Partial | Pass | Partial | Partial | Fail | 2 / 5 |
| **Vercel** | Pass | Pass | Pass | Pass | Partial (beta) | 4 / 5 |
| Cloudflare Workers | — | — | — | — | — | **DROPPED** — Python/ASGI not supported |
| Netlify | — | — | — | — | — | **DROPPED** — Python not supported in Functions |

Soft-weight adjustments applied:
- **Co-location preferred** → lifts Fly.io and Railway over Render and Vercel (which use external Postgres)
- **DX over cost** → no penalty for Fly.io's slightly more complex config
- **Existing familiarity with Fly.io** → breaks the Fly/Railway tie in favour of Fly.io

### Shortlisted Platforms

#### 1. Fly.io (Recommended)

Always-on ASGI containers (not serverless functions), Fly Postgres co-located in the same region, and `flyctl` as a comprehensive CLI for deploy/rollback/logs. The developer already designated Fly as the deployment target. Risks from the anti-bias check (uv Dockerfile authoring, volume data-loss, Postgres ownership) are all explicit and preventable with upfront config decisions. Free tier covers a solo personal project; a single shared-cpu-1x VM + small Fly Postgres runs well under $5/month.

#### 2. Railway

Excellent DX (Nixpacks detects Python automatically), managed Postgres provisioned in one click, fast path from zero to deployed. Falls below Fly.io on two counts: the $5 Starter credit exhausts in 5–6 weeks of always-on use (requiring a $20/month Pro upgrade), and buildpack auto-updates can silently change the Python version or miss `uv.lock` — opaque failure modes for a uv-managed project.

#### 3. Render

Python is supported and Render Disks + Render Postgres provide co-located storage. Dropped to third place because the free tier spins down services after 15 minutes of inactivity — directly violating the PRD's 100ms row-state latency requirement on the first request after a crochet break. The paid always-on tier starts at $7/month, making it more expensive than Fly.io for comparable capability.

## Anti-Bias Cross-Check: Fly.io

### Devil's Advocate — Weaknesses

1. **Fly.io requires a credit card even for "free" resources.** Since 2024 the free tier is pay-as-you-go with a small starting allowance — a runaway process or accidental second machine generates unexpected charges.
2. **`flyctl launch` does not detect `uv`.** The auto-generated Dockerfile uses `pip`. A `uv`-managed project (`pyproject.toml` + `uv.lock`) will be silently mishandled without a hand-authored Dockerfile using `FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim`.
3. **Fly Postgres is not a managed service in the RDS/Neon sense.** It runs as a Fly app the developer owns: major version upgrades, WAL backups, and recovery are their responsibility.
4. **SQLite on Fly Volumes is single-machine only.** Volumes are not shared across machines. `fly scale count 2` would break SQLite silently. Use Fly Postgres from day one.
5. **Mid-migration between Apps v2 and Machines API.** `flyctl launch` generates different `fly.toml` shapes across CLI versions; documentation and community answers often contradict each other.

### Pre-Mortem — How This Could Fail

The developer deployed CrochetTracker on Fly.io with a Fly Volume for SQLite — cheap and it worked. Three months later, a Python version bump in the Dockerfile caused `flyctl deploy` to provision a new machine. The `fly.toml` `[mounts]` config had a subtle path mismatch between the declared `destination` and the app's actual working directory. The new machine booted with an empty SQLite file while the old volume sat detached with all the data. No backup existed. All crochet project progress — every marked row, every pattern — was gone. The developer switched to Fly Postgres to prevent recurrence, but the SQLAlchemy models had been written with SQLite assumptions (a `RETURNING`-incompatible query). A week of debugging followed. By month 6, more time had been spent on infra than on crochet features.

### Unknown Unknowns

1. **`flyctl launch` ignores `uv.lock`** — author the Dockerfile manually from day one; don't trust auto-generation for a uv-managed project.
2. **Set a Fly.io spending limit immediately after signup** — the free allowance is thin and there's no default cap on charges.
3. **`fly.toml` `[mounts]` `destination` must match the app's exact working directory path** — a mismatch causes the new machine to boot with an empty volume file (pre-mortem scenario).
4. **Fly Postgres connection string has two ports**: 5432 (PgBouncer pooler) and 5433 (direct). Use 5432 in `DATABASE_URL`; using 5433 under load exhausts connection slots.
5. **Region choice at `fly volumes create` time is permanent** — you cannot migrate a volume to another region without a manual dump-and-restore. Pick the region closest to you at volume creation.

## Operational Story

- **Preview deploys**: Fly.io does not create preview URLs automatically per PR. Set up a separate Fly app (e.g., `crochet-tracker-staging`) and deploy to it from a CI step on PRs. No automatic branch isolation without manual config.
- **Secrets**: `fly secrets set KEY=VALUE` stores env vars encrypted in Fly's vault. Set them once; they persist across deploys. Rotation: `fly secrets set KEY=NEW_VALUE` — the app restarts with the new value. `fly secrets list` shows key names (not values). GitHub Actions uses `FLY_API_TOKEN` (set in repo secrets).
- **Rollback**: `fly releases list` → `fly deploy --image <image-id>` to roll back to a specific release. Typical time-to-revert: 30–60 seconds. Data caveat: DB schema migrations do not roll back automatically — always write reversible migrations.
- **Approval**: Creating or destroying Fly apps, volumes, and Postgres clusters requires human action (sensitive; irreversible). Routine deploys, secret rotation, and log reads are safe for automated/agent execution.
- **Logs**: `fly logs --follow` (real-time tail) or `fly logs --no-tail` (recent). Machine-specific: `fly logs -i <machine-id>`. No structured JSON log export by default — forward to a log sink (Papertrail, Logtail) if log querying is needed.

## Risk Register

| Risk | Source | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| uv Dockerfile not auto-generated by flyctl | Research finding | High | Medium | Author Dockerfile manually using `FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim`; commit it on day one |
| SQLite volume data loss on redeploy | Pre-mortem | Medium | High | Use Fly Postgres from day one; never use SQLite on Fly Volumes for production data |
| Fly.io unexpected charges (no spending cap) | Devil's advocate | Medium | Low | Set a spending limit in Fly.io dashboard immediately after signup |
| Fly Postgres version upgrade breaks app | Pre-mortem | Low | High | Pin Postgres major version in `fly postgres create --initial-cluster-size`; test upgrades in staging before applying to production |
| `[mounts]` path mismatch causes empty volume on deploy | Unknown unknowns | Medium | High | Mitigated by using Fly Postgres instead of Fly Volumes; if Volumes are used, validate mount destination in `fly.toml` matches app working directory |
| Fly Postgres connection pool exhaustion | Unknown unknowns | Low | Medium | Use DATABASE_URL pointing to PgBouncer port (5432); configure SQLAlchemy pool size ≤ 5 for a shared-cpu-1x VM |
| Apps v2 / Machines API config inconsistency | Devil's advocate | Medium | Low | Pin flyctl version in CI; commit `fly.toml` to source control and never auto-generate it mid-project |
| Railway credit exhaustion (if user reconsiders) | Research finding | High | Medium | N/A — Fly.io chosen; document for record |

## Getting Started

1. **Install flyctl and authenticate:**
   ```bash
   curl -L https://fly.io/install.sh | sh
   fly auth login
   fly auth signup   # first time
   ```
   Set a spending limit at https://fly.io/dashboard → Billing → Spending Limits before deploying.

2. **Author the Dockerfile** (do not use `flyctl launch` auto-generation — it won't handle `uv`):
   ```dockerfile
   FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim
   WORKDIR /app
   COPY pyproject.toml uv.lock ./
   RUN uv sync --frozen --no-dev
   COPY app/ ./app/
   EXPOSE 8080
   CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
   ```

3. **Create the Fly app and Postgres cluster:**
   ```bash
   fly apps create crochet-tracker
   fly postgres create --name crochet-tracker-db --region waw   # pick your nearest region
   fly postgres attach crochet-tracker-db --app crochet-tracker
   # This sets DATABASE_URL secret automatically
   ```

4. **Write `fly.toml`** (commit this; never regenerate mid-project):
   ```toml
   app = "crochet-tracker"
   primary_region = "waw"

   [build]

   [http_service]
     internal_port = 8080
     force_https = true
     auto_stop_machines = "stop"
     auto_start_machines = true
     min_machines_running = 0

   [[vm]]
     size = "shared-cpu-1x"
     memory = "256mb"
   ```
   Note: `auto_stop_machines = "stop"` and `min_machines_running = 0` keeps the free tier; set `min_machines_running = 1` on paid plan to eliminate cold starts.

5. **Deploy:**
   ```bash
   fly deploy
   fly status          # confirm running
   fly logs --follow   # watch startup
   ```

6. **Wire up GitHub Actions** (`.github/workflows/deploy.yml`):
   ```yaml
   - uses: superfly/flyctl-actions/setup-flyctl@master
   - run: fly deploy --remote-only
     env:
       FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
   ```
   Add `FLY_API_TOKEN` to GitHub repo secrets (`fly tokens create deploy -x 999999h`).

## Out of Scope

The following were not evaluated in this research:
- Docker image optimisation (multi-stage builds, layer caching)
- CI/CD pipeline configuration beyond basic GitHub Actions deploy step
- Production-scale architecture (multi-region, HA, Fly Postgres replicas)
- LiteFS for distributed SQLite (preview — explicitly out of scope for MVP)
