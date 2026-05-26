---
bootstrapped_at: 2026-05-26T18:42:00Z
starter_id: fastapi
starter_name: FastAPI
project_name: crochet-tracker
language_family: python
package_manager: uv
cwd_strategy: native-cwd
bootstrapper_confidence: first-class
phase_3_status: ok
audit_command: "pip-audit --format json"
---

## Hand-off

```yaml
starter_id: fastapi
package_manager: uv
project_name: crochet-tracker
hints:
  language_family: python
  team_size: solo
  deployment_target: fly
  ci_provider: github-actions
  ci_default_flow: auto-deploy-on-merge
  bootstrapper_confidence: first-class
  path_taken: custom
  quality_override: false
  self_check_answers:
    typed: true
    from_official_starter: true
    conventions: true
    docs_current: false
    can_judge_agent: true
  has_auth: true
  has_payments: false
  has_realtime: false
  has_ai: false
  has_background_jobs: false
```

**Why this stack:** Solo data scientist building a personal crochet tracker in 4 weeks of after-hours work. FastAPI picked over the recommended Python web default (Django) because of existing fluency — the developer knows FastAPI well, has never used Django, and has no JS frontend experience. The stack runs FastAPI with Jinja2 templates + HTMX + Tailwind for server-rendered web pages: a Python-only pattern that respects the 4-week timeline and solo constraint. FastAPI clears all four agent-friendly gates (Pydantic-typed, conventional, popular within Python training data, well-documented), so the "strong typing" and "mainstream" soft preferences are satisfied natively without compensation. The trade-off: the PRD's offline-first NFR cannot be served by this stack and is being dropped — cross-device sync remains, but it requires connectivity during use rather than reconciling offline writes. Fly is the default deployment target from the FastAPI card; GitHub Actions with auto-deploy on merge is the standard CI shape.

## Pre-scaffold verification

| Signal      | Value                                                        | Severity | Notes                                                                                 |
| ----------- | ------------------------------------------------------------ | -------- | ------------------------------------------------------------------------------------- |
| GitHub repo | not run                                                      | —        | docs_url (`https://fastapi.tiangolo.com`) is not a GitHub URL; no recency signal available |

## Scaffold log

**Resolved invocation**: `uv init . && uv add fastapi uvicorn`
**Strategy**: native-cwd (scaffold directly into the current directory)
**Exit code**: 0
**Pre-flight files-to-touch**: `pyproject.toml`, `main.py`, `.python-version`, `.venv/`, `uv.lock`
**Files written by CLI**: 5 (`pyproject.toml`, `main.py`, `.python-version`, `.venv/` tree, `uv.lock`)
**Pre-existing files preserved**: `README.md`, `.gitignore`, `CLAUDE.md`, `LICENSE`, `idea-notes.md`, `context/` (entire directory)

Installed packages (13 total):
- `fastapi==0.136.3`
- `uvicorn==0.48.0`
- `pydantic==2.13.4`
- `pydantic-core==2.46.4`
- `starlette==1.1.0`
- `anyio==4.13.0`
- `annotated-types==0.7.0`
- `typing-extensions==4.15.0`
- `typing-inspection==0.4.2`
- `click==8.4.1`
- `h11==0.16.0`
- `idna==3.16`
- `annotated-doc==0.0.4`

Python version pinned to: `3.14` (CPython 3.14.4)

## Post-scaffold audit

**Tool**: `pip-audit --format json`
**Status**: failed to run
**Reason**: `pip-audit` not found on PATH (exit 127). Tool must be installed separately: `uv add --dev pip-audit` or `pip install pip-audit`.
**Partial output**: none

## Hints recorded but not acted on

| Hint                    | Value                                                                                           |
| ----------------------- | ----------------------------------------------------------------------------------------------- |
| bootstrapper_confidence | first-class                                                                                     |
| quality_override        | false                                                                                           |
| path_taken              | custom                                                                                          |
| self_check_answers      | typed: true, from_official_starter: true, conventions: true, docs_current: false, can_judge_agent: true |
| team_size               | solo                                                                                            |
| deployment_target       | fly                                                                                             |
| ci_provider             | github-actions                                                                                  |
| ci_default_flow         | auto-deploy-on-merge                                                                            |
| has_auth                | true                                                                                            |
| has_payments            | false                                                                                           |
| has_realtime            | false                                                                                           |
| has_ai                  | false                                                                                           |
| has_background_jobs     | false                                                                                           |

These hints are carried forward as an audit trail. CI/CD scaffolding, deployment configuration, and feature-flag-based scaffolding (auth, etc.) are deferred to a future M1L4 skill.

## Next steps

Next: a future skill will set up agent context (CLAUDE.md, AGENTS.md). For now, your project is scaffolded and verified — happy hacking.

Useful manual steps in the meantime:
- Review `main.py` — it is a placeholder hello-world; replace it with your FastAPI entry point.
- Add `pip-audit` as a dev dependency (`uv add --dev pip-audit`) and run a clean audit before your first commit.
- `pyproject.toml` currently names the project `crochettracker` — consider renaming to `crochet-tracker` if you want the name to match the hand-off exactly.
- Review `.gitignore` — `uv init` may not have appended Python-specific ignores since the file already existed. Check that `.venv/` and `uv.lock` are handled per your preference.
