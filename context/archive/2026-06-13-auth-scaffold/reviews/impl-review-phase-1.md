<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Auth Scaffold (F-02)

- **Plan**: context/changes/auth-scaffold/plan.md
- **Scope**: Phase 1 of 5
- **Date**: 2026-06-13
- **Verdict**: APPROVED
- **Findings**: 0 critical, 1 warning, 0 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | PASS |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | PASS |

## Findings

### F1 — Fly secrets for SECRET_KEY/MAIL_* not yet set; next deploy's release_command will crash

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: app/config.py:17-21, fly.toml (release_command), alembic/env.py:8
- **Detail**: `app/config.py` now does `os.environ["SECRET_KEY"]`, `os.environ["MAIL_USERNAME"]`, `os.environ["MAIL_PASSWORD"]`, `os.environ["MAIL_FROM"]` at module level (fail-fast, matching the existing `DATABASE_URL` pattern). `alembic/env.py:8` does `from app.config import DATABASE_URL`, which executes the whole module on import — so any missing env var raises `KeyError` during import, before `DATABASE_URL` is even used. `fly.toml`'s `release_command = "uv run alembic upgrade head"` runs on every deploy. `fly secrets list` currently shows only `DATABASE_URL` is set on the Fly app. The next `fly deploy` will fail at the release step until `SECRET_KEY`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM` are set as Fly secrets.
- **Fix**: Before the next `fly deploy`, run `fly secrets set SECRET_KEY=... MAIL_USERNAME=... MAIL_PASSWORD=... MAIL_FROM=...` (these can be placeholder/real Gmail SMTP creds for now; Phase 4 is when mail sending actually gets exercised).
- **Decision**: FIXED — all 4 secrets (`SECRET_KEY`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`) confirmed deployed via `fly secrets list`.
